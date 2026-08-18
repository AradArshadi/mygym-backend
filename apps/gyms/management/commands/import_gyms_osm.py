import json
import random
import socket
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

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


OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.openstreetmap.ru/api/interpreter',
]
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
DEFAULT_FACILITIES = ['Strength Area', 'Cardio', 'Personal Training', 'Locker Room']
DEFAULT_PLAN_TEMPLATES = [
    ('Day Pass', 'Imported demo day access plan.', Decimal('7.00'), 1, True),
    ('Monthly Access', 'Imported demo monthly plan.', Decimal('39.00'), 30, False),
]
CITY_CENTER_FALLBACKS = {
    ('tabriz', 'iran'): (Decimal('38.0962'), Decimal('46.2738')),
}


class Command(BaseCommand):
    help = 'Import gym-like places from OpenStreetMap/Overpass into myGym with batch tracking and safe wipe support.'

    def add_arguments(self, parser):
        parser.add_argument('--city', required=True, help='City name, e.g. Tabriz')
        parser.add_argument('--country', default='', help='Country name, e.g. Iran')
        parser.add_argument('--approve', action='store_true', help='Import as APPROVED instead of PENDING.')
        parser.add_argument('--limit', type=int, default=0, help='Limit number of imported records. 0 = no limit.')
        parser.add_argument('--input-json', default='', help='Optional Overpass JSON file. If provided, no network call is made.')
        parser.add_argument('--dry-run', action='store_true', help='Fetch/parse data but do not write to database.')
        parser.add_argument('--timeout', type=int, default=35, help='Overpass timeout in seconds.')
        parser.add_argument('--radius-km', type=float, default=15, help='Radius fallback around city center. Default: 15km.')
        parser.add_argument('--lat', type=str, default='', help='Manual latitude for radius search.')
        parser.add_argument('--lon', type=str, default='', help='Manual longitude for radius search.')
        parser.add_argument('--debug', action='store_true', help='Print raw/usable/skipped importer diagnostics.')
        parser.add_argument('--raw-output', default='', help='Save raw Overpass JSON response to this file.')

    def handle(self, *args, **options):
        city = options['city'].strip()
        country = options['country'].strip()
        approve = options['approve']
        limit = options['limit']
        input_json = options['input_json']
        dry_run = options['dry_run']
        timeout = options['timeout']
        debug = options['debug']
        raw_output = options['raw_output']

        if not city:
            raise CommandError('--city cannot be empty')

        if input_json:
            with open(input_json, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            query = f'local file: {input_json}'
        else:
            lat, lon = self._resolve_center(city, country, options)
            query = self._build_radius_query(city, country, lat, lon, options['radius_km'], timeout)
            payload = self._fetch_overpass(query, timeout + 20)
            if raw_output:
                Path(raw_output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
                self.stdout.write(self.style.NOTICE(f'Raw Overpass response saved to {raw_output}'))

        records, stats = self._parse_overpass(payload, city, country)
        if limit and limit > 0:
            records = records[:limit]

        if debug:
            self.stdout.write(self.style.NOTICE('Importer debug:'))
            self.stdout.write(f"  raw elements: {stats['raw']}")
            self.stdout.write(f"  usable records: {len(records)}")
            self.stdout.write(f"  skipped missing name: {stats['missing_name']}")
            self.stdout.write(f"  skipped missing coordinates: {stats['missing_coordinates']}")
            self.stdout.write(f"  skipped duplicates: {stats['duplicates']}")
            self.stdout.write(f"  query:\n{query}")

        self.stdout.write(self.style.NOTICE(f'Found {len(records)} usable gym-like OSM records for {city}'))
        if dry_run:
            for record in records[:20]:
                self.stdout.write(f"DRY: {record['name']} | {record['lat']}, {record['lon']} | {record['external_id']}")
            self.stdout.write(self.style.SUCCESS('Dry run complete. No database changes made.'))
            return

        created = 0
        updated = 0
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                source='openstreetmap', city=city, country=country, query=query,
                total_found=len(records), notes='Imported via import_gyms_osm management command.'
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
            log_event(category='GYM', event='osm_import_completed', message=f'Imported OSM gyms for {city}: created={created}, updated={updated}', related_model='ImportBatch', related_id=batch.id, metadata={'city': city, 'country': country, 'created': created, 'updated': updated})
        self.stdout.write(self.style.SUCCESS(f'Import batch #{batch.id} complete: {created} created, {updated} updated.'))
        self.stdout.write('Wipe later with: python manage.py wipe_import_batch %s' % batch.id)

    def _resolve_center(self, city, country, options):
        if options.get('lat') and options.get('lon'):
            return Decimal(options['lat']), Decimal(options['lon'])

        query_text = f'{city}, {country}' if country else city
        params = urllib.parse.urlencode({'q': query_text, 'format': 'json', 'limit': 1})
        req = urllib.request.Request(f'{NOMINATIM_URL}?{params}', headers={'User-Agent': 'myGym-importer/0.9.2.2-hotfix'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                results = json.loads(response.read().decode('utf-8'))
            if results:
                return Decimal(str(results[0]['lat'])), Decimal(str(results[0]['lon']))
        except Exception:
            pass

        fallback = CITY_CENTER_FALLBACKS.get((city.lower(), country.lower()))
        if fallback:
            return fallback
        raise CommandError('Could not resolve city center. Pass --lat and --lon manually.')

    def _build_radius_query(self, city, country, lat, lon, radius_km, timeout):
        radius_m = max(1000, int(radius_km * 1000))
        # Radius query is more reliable than administrative area lookup for cities with multilingual OSM names.
        return f'''
[out:json][timeout:{timeout}];
(
  nwr["leisure"="fitness_centre"](around:{radius_m},{lat},{lon});
  nwr["leisure"="sports_centre"](around:{radius_m},{lat},{lon});
  nwr["sport"="fitness"](around:{radius_m},{lat},{lon});
  nwr["sport"="bodybuilding"](around:{radius_m},{lat},{lon});
  nwr["amenity"="gym"](around:{radius_m},{lat},{lon});
  nwr["name"~"gym|fitness|fit|باشگاه|ورزش|بدنسازی|فیتنس",i](around:{radius_m},{lat},{lon});
);
out center tags;
'''.strip()

    def _fetch_overpass(self, query, timeout):
        data = urllib.parse.urlencode({'data': query}).encode('utf-8')
        last_error = None
        for endpoint in OVERPASS_ENDPOINTS:
            req = urllib.request.Request(endpoint, data=data, headers={'User-Agent': 'myGym-importer/0.9.2.2-hotfix'})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return json.loads(response.read().decode('utf-8'))
            except Exception as exc:
                last_error = exc
                self.stderr.write(f'Overpass endpoint failed: {endpoint} | {exc}')
        raise CommandError(f'Overpass import failed on all endpoints: {last_error}')

    def _parse_overpass(self, payload, city, country):
        elements = payload.get('elements', [])
        stats = {'raw': len(elements), 'missing_name': 0, 'missing_coordinates': 0, 'duplicates': 0}
        records = []
        seen = set()
        for element in elements:
            tags = element.get('tags') or {}
            name = (tags.get('name') or tags.get('name:en') or tags.get('name:fa') or '').strip()
            if not name:
                stats['missing_name'] += 1
                continue
            lat = element.get('lat') or (element.get('center') or {}).get('lat')
            lon = element.get('lon') or (element.get('center') or {}).get('lon')
            if lat is None or lon is None:
                stats['missing_coordinates'] += 1
                continue
            external_id = f"osm_{element.get('type')}_{element.get('id')}"
            if external_id in seen:
                stats['duplicates'] += 1
                continue
            seen.add(external_id)
            address = self._address_from_tags(tags, city, country)
            records.append({
                'external_id': external_id,
                'name': name[:160],
                'description': self._description_from_tags(name, city, tags),
                'city': city,
                'address': address[:255],
                'phone': (tags.get('phone') or tags.get('contact:phone') or '')[:40],
                'website': (tags.get('website') or tags.get('contact:website') or '')[:200],
                'email': (tags.get('email') or tags.get('contact:email') or '')[:254],
                'lat': Decimal(str(round(float(lat), 6))),
                'lon': Decimal(str(round(float(lon), 6))),
            })
        return records, stats

    def _address_from_tags(self, tags, city, country):
        parts = []
        street = tags.get('addr:street') or tags.get('addr:place')
        housenumber = tags.get('addr:housenumber')
        if street:
            parts.append(street)
        if housenumber:
            parts.append(housenumber)
        if not parts:
            parts.append(city)
        if country:
            parts.append(country)
        return ', '.join(parts)

    def _description_from_tags(self, name, city, tags):
        services = []
        if tags.get('leisure'):
            services.append(str(tags.get('leisure')).replace('_', ' '))
        if tags.get('sport'):
            services.append(str(tags.get('sport')).replace('_', ' '))
        services_text = ', '.join(services) if services else 'fitness and training services'
        return f'{name} is an imported gym listing in {city} based on public OpenStreetMap data. Services may include {services_text}. Owners can later claim this listing and complete the profile.'

    def _get_import_owner(self):
        User = get_user_model()
        owner, created = User.objects.get_or_create(
            username='system_import_owner',
            defaults={'email': 'imports@mygym.local', 'role': User.Role.OWNER, 'is_active': False}
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
        gym = Gym.objects.filter(source='openstreetmap', external_id=record['external_id']).first()
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
        gym.source = 'openstreetmap'
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
                defaults={'description': description, 'price': price, 'duration_days': days, 'is_trial': is_trial}
            )
