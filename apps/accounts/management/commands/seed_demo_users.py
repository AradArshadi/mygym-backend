from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create a controlled small set of demo customers and owners. Never creates admin users."

    def add_arguments(self, parser):
        parser.add_argument("--customers", type=int, default=15, help="Number of demo customer users to create. Default: 15")
        parser.add_argument("--owners", type=int, default=3, help="Number of demo owner users to create. Default: 3")
        parser.add_argument("--password", default="demo12345", help="Password for all generated demo users. Default: demo12345")
        parser.add_argument("--reset", action="store_true", help="Delete existing demo users with usernames starting demo_customer_ or demo_owner_ before creating new ones.")

    def handle(self, *args, **options):
        customers = options["customers"]
        owners = options["owners"]
        password = options["password"]
        reset = options["reset"]

        if customers < 0 or owners < 0:
            raise CommandError("--customers and --owners must be zero or positive.")
        if customers > 100 or owners > 50:
            raise CommandError("Refusing to create too many demo users. Use <=100 customers and <=50 owners.")

        created = 0
        updated = 0
        deleted = 0

        with transaction.atomic():
            if reset:
                qs = User.objects.filter(username__startswith="demo_customer_") | User.objects.filter(username__startswith="demo_owner_")
                deleted, _ = qs.filter(is_superuser=False).delete()

            for i in range(1, customers + 1):
                username = f"demo_customer_{i:02d}"
                user, was_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"demo_customer_{i:02d}@mygym.local",
                        "first_name": f"Demo Customer {i:02d}",
                        "role": User.Role.CUSTOMER,
                    },
                )
                user.email = f"demo_customer_{i:02d}@mygym.local"
                user.first_name = f"Demo Customer {i:02d}"
                user.role = User.Role.CUSTOMER
                user.is_staff = False
                user.is_superuser = False
                user.set_password(password)
                user.save()
                created += int(was_created)
                updated += int(not was_created)

            for i in range(1, owners + 1):
                username = f"demo_owner_{i:02d}"
                user, was_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"demo_owner_{i:02d}@mygym.local",
                        "first_name": f"Demo Owner {i:02d}",
                        "role": User.Role.OWNER,
                    },
                )
                user.email = f"demo_owner_{i:02d}@mygym.local"
                user.first_name = f"Demo Owner {i:02d}"
                user.role = User.Role.OWNER
                user.is_staff = False
                user.is_superuser = False
                user.set_password(password)
                user.save()
                created += int(was_created)
                updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Demo users ready: {created} created, {updated} updated, {deleted} deleted. Password: {password}"
        ))
