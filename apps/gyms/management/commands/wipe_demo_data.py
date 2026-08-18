from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.gyms.models import Gym, GymImage, ImportBatch, Facility


class Command(BaseCommand):
    help = "Wipe demo/test gyms and optional non-admin demo users. Keeps superusers/admins safe by default."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
        parser.add_argument("--users", action="store_true", help="Also delete non-superuser users.")
        parser.add_argument("--all-gyms", action="store_true", help="Delete all gyms, not only imported/demo gyms.")
        parser.add_argument("--keep-admins", action="store_true", default=True, help="Keep superusers and staff/admin users. Default: true.")
        parser.add_argument("--delete-empty-batches", action="store_true", help="Delete import batches after wiping gyms.")
        parser.add_argument("--delete-facilities", action="store_true", help="Delete facilities after wiping gyms.")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Refusing to delete data without --yes.")

        with transaction.atomic():
            if options["all_gyms"]:
                gym_qs = Gym.objects.all()
            else:
                gym_qs = Gym.objects.filter(is_imported=True) | Gym.objects.filter(source__in=["geoapify", "openstreetmap", "demo"])

            gym_count = gym_qs.distinct().count()
            image_count = GymImage.objects.filter(gym__in=gym_qs).count()
            gym_qs.distinct().delete()

            batch_count = 0
            if options["delete_empty_batches"]:
                empty_batches = ImportBatch.objects.filter(gyms__isnull=True)
                batch_count = empty_batches.count()
                empty_batches.delete()

            facility_count = 0
            if options["delete_facilities"]:
                facility_count = Facility.objects.count()
                Facility.objects.all().delete()

            user_count = 0
            if options["users"]:
                users = User.objects.filter(is_superuser=False, is_staff=False).exclude(role=User.Role.ADMIN)
                user_count = users.count()
                users.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Demo wipe complete: {gym_count} gyms, {image_count} images, {batch_count} empty batches, "
            f"{facility_count} facilities, {user_count} users deleted."
        ))
