import json
import os
import random
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

from decouple import config
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.gyms.models import Facility, Gym, ImportBatch, MembershipPlan

try:
    from apps.systemlogs.services import log_event
except Exception:  # pragma: no cover
    log_event = None


GEOCODING_URL = 'https://api.geoapify.com/v1/geocode/search'
PLACES_URL = 'https://api.geoapify.com/v2/places'
SOURCE = 'geoapify'
DEFAULT_CATEGORIES = 'sport.fitness.fitness_centre,sport.fitness.gym,sport.sports_centre'
DEFAULT_FACILITIES = ['Strength Area', 'Cardio', 'Personal Training', 'Locker Room']
DEFAULT_PLAN_TEMPLATES = [
    ('Day Pass', 'Imported demo day access plan.', Decimal('7.00'), 1, True),
    ('Monthly Access', 'Imported demo monthly plan.', Decimal('39.00'), 30, False),
]
CITY_CENTER_FALLBACKS = {
    ('tabriz', 'iran'): (Decimal('38.0962'), Decimal('46.2738')),
}


class Command(BaseCommand):
    help = 'Import gym-like places from Geoapify Places API into myGym with batch tracking and safe wipe support.'

    def add_arguments(self, parser):
        parser.add_argument('--city', required=True, help='City name, e.g. Tabriz')
        parser.add_argument('--country', default='', help='Country name, e.g. Iran')
        parser.add_argument('--radius-km', type=float, default=25, help='Search radius around city center. Default: 25km.')
        parser.add_argument('--approve', action='store_true', help='Deprecated safety flag. Imported gyms stay PENDING unless --allow-auto-approve is also passed.')
        parser.add_argument('--allow-auto-approve', action='store_true', help='Unsafe: allow imported gyms to be published immediately when used together with --approve.')
        parser.add_argument('--limit', type=int, default=100, help='Maximum records to request/import. Default: 100, max supported by command: 500.')
        parser.add_argument('--dry-run', action='store_true', help='Fetch/parse data but do not write to database.')
        parser.add_argument('--timeout', type=int, default=30, help='HTTP timeout in seconds.')
        parser.add_argument('--lat', type=str, default='', help='Manual latitude. Skips geocoding when used with --lon.')
        parser.add_argument('--lon', type=str, default='', help='Manual longitude. Skips geocoding when used with --lat.')
        parser.add_argument('--categories', default=DEFAULT_CATEGORIES, help='Comma-separated Geoapify place categories.')
        parser.add_argument('--input-json', default='', help='Optional Geoapify Places JSON file. If provided, no network call is made.')
        parser.add_argument('--raw-output', default='', help='Save raw Geoapify Places JSON response to this file.')
        parser.add_argument('--debug', action='store_true', help='Print raw/usable/skipped importer diagnostics.')

    def handle(self, *args, **options):
        city = options['city'].strip()
        country = options['country'].strip()
        approve = options['approve'] and options.get('allow_auto_approve')
        if options['approve'] and not options.get('allow_auto_approve'):
            self.stdout.write(self.style.WARNING('--approve was ignored for safety. Imported gyms will be PENDING. Use --allow-auto-approve only for trusted/demo data.'))
        limit = options['limit']
        timeout = options['timeout']
        dry_run = options['dry_run']
        debug = options['debug']
        input_json = options['input_json']
        raw_output = options['raw_output']
        categories = options['categories'].strip() or DEFAULT_CATEGORIES

        if not city:
            raise CommandError('--city cannot be empty')
        if limit < 1:
            raise CommandError('--limit must be at least 1')
        limit = min(limit, 500)

        api_key = self._get_api_key()

        if input_json:
            with open(input_json, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            query_url = f'local file: {input_json}'
            center = None
        else:
            lat, lon = self._resolve_center(city, country, api_key, options, timeout)
            center = (lat, lon)
            payload, query_url = self._fetch_places(lat, lon, options['radius_km'], limit, categories, api_key, timeout)
            if raw_output:
                Path(raw_output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
                self.stdout.write(self.style.NOTICE(f'Raw Geoapify response saved to {raw_output}'))

        records, stats = self._parse_places(payload, city, country)
        records = records[:limit]

        if debug:
            self.stdout.write(self.style.NOTICE('Geoapify importer debug:'))
            if center:
                self.stdout.write(f'  center: {center[0]}, {center[1]}')
            self.stdout.write(f"  raw features: {stats['raw']}")
            self.stdout.write(f"  usable records: {len(records)}")
            self.stdout.write(f"  skipped missing name: {stats['missing_name']}")
            self.stdout.write(f"  skipped missing coordinates: {stats['missing_coordinates']}")
            self.stdout.write(f"  skipped duplicates in response: {stats['duplicates']}")
            self.stdout.write(f'  categories: {categories}')
            self.stdout.write(f'  query: {query_url}')

        self.stdout.write(self.style.NOTICE(f'Found {len(records)} usable Geoapify gym records for {city}'))
        if dry_run:
            for record in records[:20]:
                self.stdout.write(f"DRY: {record['name']} | {record['lat']}, {record['lon']} | {record['external_id']}")
            self.stdout.write(self.style.SUCCESS('Dry run complete. No database changes made.'))
            return

        created = 0
        updated = 0
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                source=SOURCE,
                city=city,
                country=country,
                query=self._redact_key(query_url, api_key),
                total_found=len(records),
                notes='Imported via import_gyms_geoapify management command.',
            )
            owner = self._get_import_owner()
            facilities = self._ensure_facilities()
            for record in records:
                gym, was_created = self._upsert_gym(record, owner, facilities, batch, approve)
                if was_created:
                    created += 1
                    self._ensure_default_plans(gym)
                else:
                    updated += 1
            batch.total_created = created
            batch.total_updated = updated
            batch.save(update_fields=['total_created', 'total_updated'])

        if log_event:
            log_event(
                category='GYM',
                event='geoapify_import_completed',
                message=f'Imported Geoapify gyms for {city}: created={created}, updated={updated}',
                related_model='ImportBatch',
                related_id=batch.id,
                metadata={'city': city, 'country': country, 'created': created, 'updated': updated, 'source': SOURCE},
            )
        self.stdout.write(self.style.SUCCESS(f'Import batch #{batch.id} complete: {created} created, {updated} updated.'))
        self.stdout.write('Wipe later with: python manage.py wipe_import_batch %s' % batch.id)

    def _get_api_key(self):
        api_key = config('GEOAPIFY_API_KEY', default='') or os.environ.get('GEOAPIFY_API_KEY', '')
        if not api_key:
            raise CommandError('Missing GEOAPIFY_API_KEY. Add it to your .env file or environment variables.')
        return api_key

    def _resolve_center(self, city, country, api_key, options, timeout):
        if options.get('lat') and options.get('lon'):
            return Decimal(options['lat']), Decimal(options['lon'])

        text = f'{city}, {country}' if country else city
        params = urllib.parse.urlencode({'text': text, 'format': 'json', 'limit': 1, 'apiKey': api_key})
        url = f'{GEOCODING_URL}?{params}'
        try:
            payload = self._get_json(url, timeout)
            results = payload.get('results') or []
            if results:
                return Decimal(str(results[0]['lat'])), Decimal(str(results[0]['lon']))
        except Exception as exc:
            self.stderr.write(f'Geoapify geocoding failed: {exc}')

        fallback = CITY_CENTER_FALLBACKS.get((city.lower(), country.lower()))
        if fallback:
            return fallback
        raise CommandError('Could not resolve city center. Pass --lat and --lon manually.')

    def _fetch_places(self, lat, lon, radius_km, limit, categories, api_key, timeout):
        radius_m = max(1000, int(radius_km * 1000))
        params = urllib.parse.urlencode({
            'categories': categories,
            'filter': f'circle:{lon},{lat},{radius_m}',
            'bias': f'proximity:{lon},{lat}',
            'limit': limit,
            'apiKey': api_key,
        })
        url = f'{PLACES_URL}?{params}'
        return self._get_json(url, timeout), self._redact_key(url, api_key)

    def _get_json(self, url, timeout):
        req = urllib.request.Request(url, headers={'User-Agent': 'myGym-importer/0.9.2.3'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')[:500]
            raise CommandError(f'Geoapify HTTP {exc.code}: {body}')
        except urllib.error.URLError as exc:
            raise CommandError(f'Geoapify request failed: {exc}')

    def _parse_places(self, payload, city, country):
        features = payload.get('features') or []
        stats = {'raw': len(features), 'missing_name': 0, 'missing_coordinates': 0, 'duplicates': 0}
        records = []
        seen = set()

        for feature in features:
            props = feature.get('properties') or {}
            geometry = feature.get('geometry') or {}
            coordinates = geometry.get('coordinates') or []

            name = (props.get('name') or props.get('address_line1') or '').strip()
            if not name:
                stats['missing_name'] += 1
                continue

            lon = props.get('lon')
            lat = props.get('lat')
            if (lat is None or lon is None) and len(coordinates) >= 2:
                lon, lat = coordinates[0], coordinates[1]
            if lat is None or lon is None:
                stats['missing_coordinates'] += 1
                continue

            external_id = (props.get('place_id') or props.get('osm_id') or f'{name}_{lat}_{lon}').strip()
            external_id = f'geoapify_{external_id}'
            if external_id in seen:
                stats['duplicates'] += 1
                continue
            seen.add(external_id)

            records.append({
                'external_id': external_id[:255],
                'name': name[:160],
                'description': self._description_from_props(name, city, props),
                'city': (props.get('city') or city)[:100],
                'address': self._address_from_props(props, city, country)[:255],
                'phone': (props.get('phone') or props.get('contact_phone') or '')[:40],
                'website': (props.get('website') or props.get('contact_website') or '')[:200],
                'email': (props.get('email') or props.get('contact_email') or '')[:254],
                'lat': Decimal(str(round(float(lat), 6))),
                'lon': Decimal(str(round(float(lon), 6))),
            })
        return records, stats

    def _address_from_props(self, props, city, country):
        formatted = (props.get('formatted') or '').strip()
        if formatted:
            return formatted
        parts = []
        street = props.get('street')
        house = props.get('housenumber')
        if street:
            parts.append(str(street))
        if house:
            parts.append(str(house))
        if not parts:
            parts.append(city)
        if country:
            parts.append(country)
        return ', '.join(parts)

    def _description_from_props(self, name, city, props):
        categories = props.get('categories') or []
        if isinstance(categories, list):
            service_text = ', '.join(str(item).replace('.', ' ').replace('_', ' ') for item in categories[:4])
        else:
            service_text = str(categories).replace('.', ' ').replace('_', ' ')
        if not service_text:
            service_text = 'fitness and training services'
        return f'{name} is an imported gym listing in {city} based on Geoapify Places data. Services may include {service_text}. Owners can later claim this listing and complete the profile.'



    def _get_import_owner(self):
        User = get_user_model()
        owner, created = User.objects.get_or_create(
            username='system_import_owner',
            defaults={'email': 'imports@mygym.local', 'role': User.Role.OWNER, 'is_active': False},
        )
        if created:
            owner.set_unusable_password()
            owner.save(update_fields=['password'])
        return owner

    def _ensure_facilities(self):
        facilities = []
        for name in DEFAULT_FACILITIES:
            facility, _ = Facility.objects.get_or_create(name=name)
            facilities.append(facility)
        return facilities

    def _unique_slug(self, name, external_id):
        base = slugify(name)[:130] or slugify(external_id)[:130] or 'imported-gym'
        slug = base
        i = 2
        while Gym.objects.filter(slug=slug).exists():
            slug = f'{base}-{i}'[:180]
            i += 1
        return slug

    def _upsert_gym(self, record, owner, facilities, batch, approve):
        gym = Gym.objects.filter(source=SOURCE, external_id=record['external_id']).first()
        was_created = gym is None
        if was_created:
            gym = Gym(owner=owner, slug=self._unique_slug(record['name'], record['external_id']))
        elif gym.is_claimed:
            return gym, False

        gym.name = record['name']
        gym.description = record['description']
        gym.city = record['city']
        gym.address = record['address']
        gym.email = record['email']
        gym.phone = record['phone']
        gym.website = record['website']
        gym.latitude = record['lat']
        gym.longitude = record['lon']
        gym.starting_price = Decimal(str(random.choice([29, 35, 39, 45, 49, 59])))
        gym.status = Gym.Status.APPROVED if approve else Gym.Status.PENDING
        gym.is_imported = True
        gym.is_claimed = False
        gym.source = SOURCE
        gym.external_id = record['external_id']
        gym.import_batch = batch
        gym.imported_at = timezone.now()
        gym.save()
        gym.facilities.set(facilities)
        return gym, was_created

    def _ensure_default_plans(self, gym):
        for title, description, price, days, is_trial in DEFAULT_PLAN_TEMPLATES:
            MembershipPlan.objects.get_or_create(
                gym=gym,
                title=title,
                defaults={'description': description, 'price': price, 'duration_days': days, 'is_trial': is_trial},
            )

    def _redact_key(self, text, api_key):
        return str(text).replace(api_key, '***')
