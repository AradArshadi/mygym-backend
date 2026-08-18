from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.accounts.models import User
from apps.gyms.models import Facility, Gym, MembershipPlan, TrainerProfile


class Command(BaseCommand):
    help = 'Seed demo users, gyms, facilities, plans, and trainers.'

    def handle(self, *args, **options):
        owner, _ = User.objects.get_or_create(username='owner_demo', defaults={'email': 'owner@mygym.local', 'role': User.Role.OWNER})
        owner.set_password('owner12345')
        owner.save()

        customer, _ = User.objects.get_or_create(username='customer_demo', defaults={'email': 'customer@mygym.local', 'role': User.Role.CUSTOMER})
        customer.set_password('customer12345')
        customer.save()

        facilities = ['Sauna', 'Parking', '24/7 Access', 'Personal Training', 'Women Only Area', 'Pool', 'Student Friendly']
        facility_objs = [Facility.objects.get_or_create(name=name)[0] for name in facilities]

        demo_gyms = [
            ('Iron Temple Bamberg', 'Premium strength gym with serious equipment and coaching.', 'Bamberg', 'Lange Straße 10', 29.90, 49.893982, 10.887417),
            ('FlexFit Studio', 'Modern fitness studio for students, beginners, and busy professionals.', 'Bamberg', 'Wunderburg 7', 19.90, 49.891890, 10.902160),
            ('Core & Cardio Club', 'Friendly local gym focused on classes, cardio, and wellness.', 'Bamberg', 'Hainstraße 22', 24.90, 49.892928, 10.877315),
        ]

        for name, description, city, address, price, latitude, longitude in demo_gyms:
            gym, _ = Gym.objects.get_or_create(
                slug=slugify(name),
                defaults={
                    'owner': owner,
                    'name': name,
                    'description': description,
                    'city': city,
                    'address': address,
                    'email': 'gym@mygym.local',
                    'starting_price': price,
                    'latitude': latitude,
                    'longitude': longitude,
                    'status': Gym.Status.APPROVED,
                },
            )
            gym.latitude = latitude
            gym.longitude = longitude
            gym.save(update_fields=['latitude', 'longitude'])
            gym.facilities.set(facility_objs[:4])
            MembershipPlan.objects.get_or_create(gym=gym, title='Day Pass', defaults={'price': 9.90, 'duration_days': 1, 'is_trial': True})
            MembershipPlan.objects.get_or_create(gym=gym, title='Monthly', defaults={'price': price, 'duration_days': 30})

        trainer_user, _ = User.objects.get_or_create(username='trainer_demo', defaults={'email': 'trainer@mygym.local', 'role': User.Role.TRAINER})
        trainer_user.set_password('trainer12345')
        trainer_user.save()
        first_gym = Gym.objects.first()
        TrainerProfile.objects.get_or_create(user=trainer_user, defaults={'gym': first_gym, 'bio': 'Strength and hypertrophy coach.', 'specialties': 'Strength, Hypertrophy, Nutrition', 'hourly_rate': 35})

        self.stdout.write(self.style.SUCCESS('Demo data created.'))
