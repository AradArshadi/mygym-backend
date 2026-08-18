from django.core.management.base import BaseCommand
from apps.gyms.models import ImportBatch


class Command(BaseCommand):
    help = 'List data import batches and their wipe status.'

    def handle(self, *args, **options):
        batches = ImportBatch.objects.all()[:100]
        if not batches:
            self.stdout.write('No import batches found.')
            return
        self.stdout.write('ID | source | city | country | gyms_now | created | updated | created_at')
        self.stdout.write('-' * 100)
        for batch in batches:
            self.stdout.write(
                f'{batch.id} | {batch.source} | {batch.city} | {batch.country or "-"} | '
                f'{batch.gyms.count()} | {batch.total_created} | {batch.total_updated} | {batch.created_at:%Y-%m-%d %H:%M}'
            )
