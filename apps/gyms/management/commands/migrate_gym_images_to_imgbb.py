from django.core.management.base import BaseCommand, CommandError

from apps.gyms.image_hosting import ImageHostingError, upload_image
from apps.gyms.models import GymImage


class Command(BaseCommand):
    help = (
        'Upload legacy local GymImage files to ImgBB and store only their remote URLs. '
        'Use --delete-local after verifying the remote migration.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--delete-local', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--include-remote', action='store_true', help='Re-upload rows that already have external_url.')

    def handle(self, *args, **options):
        qs = GymImage.objects.exclude(image='').exclude(image__isnull=True).order_by('id')
        if not options['include_remote']:
            qs = qs.filter(external_url='')
        if options['limit']:
            qs = qs[: options['limit']]

        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.SUCCESS('No local gym images need migration.'))
            return

        self.stdout.write(f'{len(rows)} local image(s) selected.')
        migrated = 0
        failed = 0

        for image in rows:
            name = image.image.name
            if options['dry_run']:
                self.stdout.write(f'DRY #{image.id}: {name}')
                continue

            storage = image.image.storage
            if not storage.exists(name):
                failed += 1
                self.stderr.write(self.style.WARNING(f'SKIP #{image.id}: local file missing: {name}'))
                continue

            try:
                with storage.open(name, 'rb') as local_file:
                    hosted = upload_image(local_file, name=name)
            except (ImageHostingError, OSError) as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'FAIL #{image.id}: {exc}'))
                continue

            image.external_url = hosted.url
            image.source = 'imgbb'
            image.remote_id = hosted.id
            image.remote_delete_url = hosted.delete_url
            image.remote_width = hosted.width
            image.remote_height = hosted.height
            image.remote_size = hosted.size

            if options['delete_local']:
                image.image = None

            image.save(update_fields=[
                'external_url', 'source', 'remote_id', 'remote_delete_url',
                'remote_width', 'remote_height', 'remote_size', 'image',
            ])

            if options['delete_local']:
                try:
                    storage.delete(name)
                except OSError as exc:
                    self.stderr.write(self.style.WARNING(f'#{image.id}: remote migration succeeded but local cleanup failed: {exc}'))

            migrated += 1
            self.stdout.write(self.style.SUCCESS(f'OK #{image.id}: {hosted.url}'))

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS('Dry run complete. No files or rows changed.'))
            return

        if failed:
            self.stdout.write(self.style.WARNING(f'Finished: {migrated} migrated, {failed} skipped/failed.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Finished: {migrated} image(s) migrated successfully.'))
