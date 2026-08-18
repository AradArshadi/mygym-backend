from django.core.management.base import BaseCommand

from apps.gyms.models import GymImage


class Command(BaseCommand):
    help = 'Report GymImage rows with no usable remote URL and missing local files.'

    def handle(self, *args, **options):
        broken = 0
        remote = 0
        local = 0
        empty = 0

        for image in GymImage.objects.select_related('gym').all().order_by('id'):
            if image.external_url:
                remote += 1
                continue
            if image.image:
                try:
                    if image.image.storage.exists(image.image.name):
                        local += 1
                        continue
                except Exception:
                    pass
                broken += 1
                self.stderr.write(self.style.WARNING(
                    f'BROKEN #{image.id} {image.gym.slug}: local file missing ({image.image.name})'
                ))
                continue
            empty += 1
            broken += 1
            self.stderr.write(self.style.WARNING(f'EMPTY #{image.id} {image.gym.slug}: no image URL or file'))

        self.stdout.write(f'Remote: {remote} | Local legacy: {local} | Empty: {empty} | Broken: {broken}')
        if broken == 0:
            self.stdout.write(self.style.SUCCESS('Gym image integrity is clean.'))
