import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.gyms.models import Gym
from apps.reviews.models import Review


POSITIVE_COMMENTS = [
    "Clean gym, friendly staff, and good atmosphere for daily training.",
    "Great equipment selection and the location is very convenient.",
    "Nice place to train. The opening hours and facilities are useful.",
    "Good value for the price and a motivating environment.",
    "Solid gym with helpful service and enough space for workouts.",
    "The gym feels professional and welcoming for beginners and regulars.",
    "Good training experience overall. I would come back again.",
    "Comfortable place with a practical setup and reliable equipment.",
]

MIXED_COMMENTS = [
    "Good gym overall, but it can get crowded at peak hours.",
    "Useful facilities, although some parts could be more modern.",
    "Nice staff and location, but the equipment variety could improve.",
    "Decent training experience for the price.",
]


class Command(BaseCommand):
    help = "Create realistic demo reviews and ratings from demo customer users for existing gyms."

    def add_arguments(self, parser):
        parser.add_argument("--reviews", type=int, default=40, help="Number of demo reviews to create. Default: 40")
        parser.add_argument("--min-rating", type=int, default=3, help="Minimum rating. Default: 3")
        parser.add_argument("--max-rating", type=int, default=5, help="Maximum rating. Default: 5")
        parser.add_argument("--reset", action="store_true", help="Delete existing reviews by demo_customer_* users before creating new ones.")
        parser.add_argument("--visible", action="store_true", default=True, help="Create visible reviews. Default: true")
        parser.add_argument("--include-all-customers", action="store_true", help="Use all non-admin customer users, not only demo_customer_* users.")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible demo data. Default: 42")

    def handle(self, *args, **options):
        review_count = options["reviews"]
        min_rating = options["min_rating"]
        max_rating = options["max_rating"]
        reset = options["reset"]
        visible = options["visible"]
        include_all_customers = options["include_all_customers"]
        seed = options["seed"]

        if review_count < 0:
            raise CommandError("--reviews must be zero or positive.")
        if review_count > 500:
            raise CommandError("Refusing to create too many demo reviews. Use --reviews <= 500.")
        if min_rating < 1 or max_rating > 5 or min_rating > max_rating:
            raise CommandError("Ratings must satisfy 1 <= --min-rating <= --max-rating <= 5.")

        if include_all_customers:
            users = list(User.objects.filter(role=User.Role.CUSTOMER, is_superuser=False, is_staff=False).order_by("id"))
        else:
            users = list(User.objects.filter(username__startswith="demo_customer_", role=User.Role.CUSTOMER).order_by("id"))

        gyms = list(Gym.objects.all().order_by("id"))

        if not users:
            raise CommandError("No customer users found. Run: python manage.py seed_demo_users --customers 15 --owners 3")
        if not gyms:
            raise CommandError("No gyms found. Run the Geoapify importer first.")

        max_possible = len(users) * len(gyms)
        if review_count > max_possible:
            raise CommandError(f"Cannot create {review_count} unique reviews with {len(users)} users and {len(gyms)} gyms. Max possible: {max_possible}.")

        random.seed(seed)
        pairs = [(user, gym) for user in users for gym in gyms]
        random.shuffle(pairs)

        created = 0
        skipped = 0
        deleted = 0

        with transaction.atomic():
            if reset:
                if include_all_customers:
                    qs = Review.objects.filter(user__in=users)
                else:
                    qs = Review.objects.filter(user__username__startswith="demo_customer_")
                deleted, _ = qs.delete()

            for user, gym in pairs:
                if created >= review_count:
                    break

                rating = random.randint(min_rating, max_rating)
                comments = POSITIVE_COMMENTS if rating >= 4 else MIXED_COMMENTS
                comment = random.choice(comments)

                review, was_created = Review.objects.get_or_create(
                    user=user,
                    gym=gym,
                    defaults={
                        "rating": rating,
                        "comment": comment,
                        "is_visible": visible,
                    },
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Demo reviews ready: {created} created, {skipped} skipped, {deleted} deleted."
        ))
