import random
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from apps.bookings.models import Booking
from apps.gyms.models import Facility, Gym, MembershipPlan, TrainerProfile
from apps.reviews.models import Favorite, Review


class Command(BaseCommand):
    help = "Seed myGym with 100 realistic synthetic gyms in Tabriz, Iran."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=100, help="Number of gyms to create. Default: 100")
        parser.add_argument("--reset", action="store_true", help="Delete previously generated Tabriz demo data before seeding")

    def handle(self, *args, **options):
        random.seed(42)
        count = options["count"]
        User = get_user_model()

        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting generated Tabriz demo data..."))
            Gym.objects.filter(slug__startswith="tabriz-").delete()
            User.objects.filter(username__startswith="tabriz_owner_").delete()
            User.objects.filter(username__startswith="tabriz_trainer_").delete()
            User.objects.filter(username__startswith="tabriz_customer_").delete()

        facilities = self._create_facilities()
        customers = self._create_customers(User)

        districts = [
            ("Valiasr", "ولیعصر", Decimal("38.065200"), Decimal("46.333100")),
            ("El Goli", "ائل‌گلی", Decimal("38.026700"), Decimal("46.365200")),
            ("Roshdiyeh", "رشدیه", Decimal("38.080600"), Decimal("46.368500")),
            ("Baghmisha", "باغمیشه", Decimal("38.084800"), Decimal("46.346400")),
            ("Abrasan", "آبرسان", Decimal("38.073900"), Decimal("46.309400")),
            ("Shariati", "شریعتی", Decimal("38.073100"), Decimal("46.287600")),
            ("Mansour", "منصور", Decimal("38.069400"), Decimal("46.294100")),
            ("Danasar", "داناسر", Decimal("38.091600"), Decimal("46.312600")),
            ("Maralan", "مارالان", Decimal("38.060700"), Decimal("46.303500")),
            ("Akhmaqaya", "آخمقیه", Decimal("38.025800"), Decimal("46.290300")),
            ("Sahand", "سهند", Decimal("37.942000"), Decimal("46.117000")),
            ("Laleh", "لاله", Decimal("38.093900"), Decimal("46.279500")),
        ]

        prefixes = ["Pulse", "Araz", "Sahand", "Atlas", "Iron", "Nova", "Hero", "Prime", "Titan", "Arena", "Peak", "Vigor", "Nexa", "Alpha", "Motion", "Power", "Fit", "Oxygen", "Phoenix", "Victory"]
        suffixes = ["Gym", "Fitness Club", "Training House", "Performance Center", "Athletic Club", "Body Lab", "Fit Studio", "Strength Club", "Wellness Club", "Cross Training"]
        plan_templates = [
            ("Day Pass", "Single-day access for testing the gym.", 1, True),
            ("Monthly Basic", "Standard access for regular training.", 30, False),
            ("Monthly Plus", "Access with trainer introduction and selected classes.", 30, False),
            ("Quarterly Pro", "Three-month plan for committed members.", 90, False),
        ]
        specialties = ["Strength", "Bodybuilding", "HIIT", "Boxing", "TRX", "CrossFit", "Yoga", "Pilates", "Weight Loss", "Powerlifting", "Functional", "Corrective Exercise"]

        created = 0
        for i in range(1, count + 1):
            district_en, district_fa, base_lat, base_lng = random.choice(districts)
            name = f"{random.choice(prefixes)} {district_en} {random.choice(suffixes)}"
            if i <= len(prefixes):
                name = f"{prefixes[i-1]} Tabriz {random.choice(suffixes)}"

            owner, _ = User.objects.get_or_create(
                username=f"tabriz_owner_{i:03d}",
                defaults={
                    "email": f"tabriz.owner{i:03d}@mygym.local",
                    "role": User.Role.OWNER,
                    "first_name": random.choice(["Arman", "Sina", "Reza", "Nima", "Saman", "Kamran", "Shayan"]),
                    "last_name": random.choice(["Azari", "Rahimi", "Tabrizi", "Karimi", "Amini", "Farhadi"]),
                },
            )
            owner.set_password("demo12345")
            owner.role = User.Role.OWNER
            owner.save()

            lat = base_lat + Decimal(str(round(random.uniform(-0.012, 0.012), 6)))
            lng = base_lng + Decimal(str(round(random.uniform(-0.012, 0.012), 6)))
            slug = slugify(f"tabriz-{name}-{i}")

            gym, was_created = Gym.objects.update_or_create(
                slug=slug,
                defaults={
                    "owner": owner,
                    "name": name,
                    "description": self._description(name, district_en),
                    "city": "Tabriz",
                    "address": f"Tabriz, {district_en} district ({district_fa}), Demo Street {random.randint(1, 40)}, Unit {random.randint(1, 20)}",
                    "email": f"contact{i:03d}@tabriz-mygym.local",
                    "phone": f"+98 914 {random.randint(1000000, 9999999)}",
                    "website": "",
                    "latitude": lat,
                    "longitude": lng,
                    "starting_price": Decimal(random.choice([350000, 450000, 550000, 650000, 750000, 950000])) / Decimal("10"),
                    "status": Gym.Status.APPROVED,
                },
            )
            gym.facilities.set(random.sample(facilities, random.randint(4, 8)))

            for title, desc, duration, is_trial in plan_templates:
                base_price = Decimal(random.choice([250000, 350000, 450000, 650000, 850000, 1200000])) / Decimal("10")
                if is_trial:
                    price = Decimal(random.choice([50000, 75000, 100000, 150000])) / Decimal("10")
                elif duration == 90:
                    price = base_price * Decimal("2.6")
                elif "Plus" in title:
                    price = base_price * Decimal("1.35")
                else:
                    price = base_price
                MembershipPlan.objects.update_or_create(
                    gym=gym,
                    title=title,
                    defaults={"description": desc, "price": price.quantize(Decimal("0.01")), "duration_days": duration, "is_trial": is_trial},
                )

            trainer_count = random.randint(1, 4)
            trainer_profiles = []
            for t in range(1, trainer_count + 1):
                trainer_user, _ = User.objects.get_or_create(
                    username=f"tabriz_trainer_{i:03d}_{t}",
                    defaults={
                        "email": f"tabriz.trainer{i:03d}.{t}@mygym.local",
                        "role": User.Role.TRAINER,
                        "first_name": random.choice(["Ali", "Armin", "Mahan", "Sahar", "Darya", "Leyla", "Negin", "Amir"]),
                        "last_name": random.choice(["Jafari", "Hosseini", "Mohammadi", "Ahmadi", "Karimi", "Azizi"]),
                    },
                )
                trainer_user.set_password("demo12345")
                trainer_user.role = User.Role.TRAINER
                trainer_user.save()
                chosen_specs = ", ".join(random.sample(specialties, random.randint(2, 4)))
                profile, _ = TrainerProfile.objects.update_or_create(
                    user=trainer_user,
                    defaults={
                        "gym": gym,
                        "bio": f"Certified coach focused on {chosen_specs.lower()} with a practical and motivational training style.",
                        "specialties": chosen_specs,
                        "hourly_rate": Decimal(random.choice([150000, 200000, 250000, 300000, 400000])) / Decimal("10"),
                        "is_available": random.choice([True, True, True, False]),
                    },
                )
                trainer_profiles.append(profile)

            for customer in random.sample(customers, random.randint(3, 8)):
                Review.objects.update_or_create(
                    user=customer,
                    gym=gym,
                    defaults={
                        "rating": random.choice([4, 4, 4, 5, 5, 3]),
                        "comment": random.choice([
                            "Clean environment and friendly staff.",
                            "Good equipment and strong training vibe.",
                            "Nice location and helpful trainers.",
                            "Great place for regular workouts in Tabriz.",
                            "The booking process was smooth and simple.",
                        ]),
                        "is_visible": True,
                    },
                )

            for customer in random.sample(customers, random.randint(2, 6)):
                Favorite.objects.get_or_create(user=customer, gym=gym)

            plans = list(gym.plans.all())
            for b in range(random.randint(1, 5)):
                customer = random.choice(customers)
                booking_dt = timezone.now() + timedelta(days=random.randint(1, 30), hours=random.randint(8, 21))
                Booking.objects.get_or_create(
                    customer=customer,
                    gym=gym,
                    booking_datetime=booking_dt,
                    defaults={
                        "trainer": random.choice(trainer_profiles) if trainer_profiles and random.choice([True, False]) else None,
                        "plan": random.choice(plans) if plans else None,
                        "status": random.choice([Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.CONFIRMED, Booking.Status.REJECTED]),
                        "customer_note": random.choice(["Trial session request", "Interested in monthly plan", "I want to visit after work", ""]),
                    },
                )

            created += 1 if was_created else 0

        self.stdout.write(self.style.SUCCESS(f"Tabriz seed complete. Created/updated {count} gyms; new gyms this run: {created}."))
        self.stdout.write("Demo passwords for generated owners/trainers/customers: demo12345")

    def _create_facilities(self):
        names = [
            "Free weights", "Cardio zone", "Personal trainer", "Women-only hours", "Men-only hours", "Showers", "Lockers", "Sauna", "Spa", "Parking", "Protein bar", "Nutrition coaching", "TRX", "Boxing", "CrossFit", "Yoga", "Pilates", "Physiotherapy", "Cafe", "WiFi", "24/7 access", "Student friendly",
        ]
        facilities = []
        for name in names:
            facility, _ = Facility.objects.get_or_create(name=name)
            facilities.append(facility)
        return facilities

    def _create_customers(self, User):
        customers = []
        first_names = ["Arad", "Sina", "Ali", "Reza", "Nima", "Sara", "Darya", "Negin", "Mina", "Parsa", "Arman", "Leyla", "Shayan", "Sahar", "Pouya", "Setareh", "Kian", "Tara", "Mahan", "Yasmin"]
        last_names = ["Azari", "Tabrizi", "Rahimi", "Karimi", "Hosseini", "Jafari", "Amini", "Farhadi", "Ahmadi", "Mohammadi"]
        for i in range(1, 151):
            user, _ = User.objects.get_or_create(
                username=f"tabriz_customer_{i:03d}",
                defaults={
                    "email": f"tabriz.customer{i:03d}@mygym.local",
                    "role": User.Role.CUSTOMER,
                    "first_name": random.choice(first_names),
                    "last_name": random.choice(last_names),
                },
            )
            user.set_password("demo12345")
            user.role = User.Role.CUSTOMER
            user.save()
            customers.append(user)
        return customers

    def _description(self, name, district):
        return (
            f"{name} is a demo fitness venue in {district}, Tabriz. "
            "It is designed for the myGym marketplace demo with realistic facilities, trainers, plans, reviews, and booking activity. "
            "The data is synthetic and intended for product testing, analytics, and investor demos."
        )
