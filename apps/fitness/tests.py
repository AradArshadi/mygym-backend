from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import WorkoutGoal, WorkoutLog
from .services import current_weekly_streak, fitness_summary, week_start_for, weekly_workout_count


class FitnessHomeTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.customer = self.User.objects.create_user(
            username='fitness_customer',
            email='customer@example.com',
            password='pass12345',
            role='CUSTOMER',
        )
        self.owner = self.User.objects.create_user(
            username='fitness_owner',
            email='owner@example.com',
            password='pass12345',
            role='OWNER',
        )

    def test_goal_is_created_with_default_weekly_target(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('fitness_home'))
        self.assertEqual(response.status_code, 200)
        goal = WorkoutGoal.objects.get(user=self.customer)
        self.assertEqual(goal.weekly_target, 3)

    def test_log_workout_creates_entry(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('log_workout'), {
            'title': 'Upper A',
            'workout_type': 'Strength',
            'duration_minutes': 62,
            'notes': 'Good session.',
        })
        self.assertRedirects(response, reverse('fitness_home'))
        workout = WorkoutLog.objects.get(user=self.customer)
        self.assertEqual(workout.title, 'Upper A')
        self.assertEqual(workout.duration_minutes, 62)

    def test_weekly_count_and_summary(self):
        current_week = week_start_for()
        first_day = timezone.make_aware(datetime.combine(current_week, time(hour=10)))
        second_day = timezone.make_aware(datetime.combine(current_week + timedelta(days=1), time(hour=18)))
        WorkoutLog.objects.create(user=self.customer, title='Push', logged_at=first_day, duration_minutes=45)
        WorkoutLog.objects.create(user=self.customer, title='Pull', logged_at=second_day, duration_minutes=50)
        self.assertEqual(weekly_workout_count(self.customer), 2)
        summary = fitness_summary(self.customer)
        self.assertEqual(summary['week_count'], 2)
        self.assertEqual(summary['total_workouts'], 2)
        self.assertEqual(summary['total_minutes'], 95)

    def test_weekly_streak_counts_completed_weeks(self):
        goal = WorkoutGoal.objects.create(user=self.customer, weekly_target=3)
        current_week = week_start_for()
        previous_week = current_week - timedelta(days=7)
        for day in [0, 1, 2]:
            WorkoutLog.objects.create(user=self.customer, title=f'Current {day}', logged_at=timezone.make_aware(datetime.combine(current_week + timedelta(days=day), time.min)))
            WorkoutLog.objects.create(user=self.customer, title=f'Previous {day}', logged_at=timezone.make_aware(datetime.combine(previous_week + timedelta(days=day), time.min)))
        self.assertEqual(current_weekly_streak(self.customer, target=goal.weekly_target), 2)

    def test_owner_is_redirected_from_customer_fitness_home(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('fitness_home'))
        self.assertRedirects(response, reverse('owner_dashboard'))

    def test_mobile_nav_urls_are_available(self):
        self.client.force_login(self.customer)
        for name in ['fitness_home', 'gym_list', 'my_memberships', 'workout_history', 'profile_hub', 'more_menu', 'discover', 'chat_home']:
            response = self.client.get(reverse(name))
            self.assertIn(response.status_code, [200, 302])

class FitnessThemeAndCalendarTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.customer = self.User.objects.create_user(
            username='calendar_customer',
            email='calendar@example.com',
            password='pass12345',
            role='CUSTOMER',
        )

    def test_activity_calendar_supports_selected_ranges(self):
        self.client.force_login(self.customer)
        for days in [30, 90, 120, 360]:
            response = self.client.get(reverse('fitness_home'), {'activity_days': days})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'Past {days} days')
            self.assertContains(response, 'data-activity-map')

    def test_invalid_activity_calendar_range_falls_back_to_30_days(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('fitness_home'), {'activity_days': 999})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Past 30 days')

    def test_mygym_contains_mobile_logout_and_theme_toggle(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('profile_hub'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profile')
        self.assertContains(response, 'Logout')
        self.assertContains(response, 'data-theme-toggle')

class FitnessActivityMapRegressionTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.customer = self.User.objects.create_user(
            username='activity_customer',
            email='activity@example.com',
            password='pass12345',
            role='CUSTOMER',
        )

    def test_activity_summary_counts_selected_range_not_all_time(self):
        now = timezone.now()
        WorkoutLog.objects.create(user=self.customer, title='Today', logged_at=now, duration_minutes=30)
        WorkoutLog.objects.create(user=self.customer, title='Yesterday', logged_at=now - timedelta(days=1), duration_minutes=40)
        WorkoutLog.objects.create(user=self.customer, title='Old', logged_at=now - timedelta(days=70), duration_minutes=50)
        summary = fitness_summary(self.customer, activity_days=30)
        self.assertEqual(summary['total_workouts'], 3)
        self.assertEqual(summary['activity_range_workouts'], 2)
        self.assertEqual(summary['activity_range_active_days'], 2)

    def test_activity_calendar_is_github_style_week_grid(self):
        self.client.force_login(self.customer)
        WorkoutLog.objects.create(user=self.customer, title='Today', logged_at=timezone.now(), duration_minutes=30)
        response = self.client.get(reverse('fitness_home'), {'activity_days': 30})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gh-activity-calendar')
        self.assertContains(response, 'gh-activity-cell level-1 today')
        self.assertContains(response, '1 active day in range')

    def test_activity_calendar_cells_are_interactive_and_copy_is_clean(self):
        self.client.force_login(self.customer)
        WorkoutLog.objects.create(user=self.customer, title='Today', logged_at=timezone.now(), duration_minutes=30)
        response = self.client.get(reverse('fitness_home'), {'activity_days': 30})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-activity-map')
        self.assertContains(response, 'data-activity-detail')
        self.assertContains(response, 'data-count="1"')
        self.assertNotContains(response, 'GitHub-style calendar · today is highlighted')

    def test_short_range_month_labels_do_not_overlap_partial_months(self):
        from .services import training_activity_calendar
        calendar = training_activity_calendar(self.customer, days=30)
        labels = calendar['month_labels']
        if len(labels) > 1:
            for previous, current in zip(labels, labels[1:]):
                self.assertGreaterEqual(current['column'] - previous['column'], 4)

    def test_mobile_nav_keeps_hamburger_fallback_available(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('fitness_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'navbar-toggler')
        self.assertContains(response, 'mg-mobile-tabbar')


class FitnessClarityUXTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.customer = self.User.objects.create_user(
            username='clarity_customer',
            email='clarity@example.com',
            password='pass12345',
            role='CUSTOMER',
        )

    def test_mobile_nav_uses_current_stage_labels(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('fitness_home'))
        self.assertEqual(response.status_code, 200)
        for label in ['Home', 'Explore', 'Visit', 'Activity', 'Profile']:
            self.assertContains(response, f'<small>{label}</small>', html=True)
        self.assertNotContains(response, '<small>MyGym</small>', html=True)
        self.assertNotContains(response, '<small>More</small>', html=True)
        self.assertNotContains(response, '<small>Chat</small>', html=True)
        self.assertNotContains(response, '<small>Discover</small>', html=True)

    def test_desktop_customer_nav_uses_same_five_destinations(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('fitness_home'))
        self.assertEqual(response.status_code, 200)
        for label in ['Home', 'Explore', 'Visit', 'Activity', 'Profile']:
            self.assertContains(response, f'>{label}</a>')
        self.assertNotContains(response, '>MyGym</a>')
        self.assertNotContains(response, '>More</a>')

    def test_more_menu_keeps_future_features_out_of_primary_nav(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('more_menu'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Discover preview')
        self.assertContains(response, 'Chat preview')
        self.assertContains(response, 'Logout')


class FitnessProfileEditTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.customer = self.User.objects.create_user(username='profile_customer', email='profile@example.com', password='pass12345', role='CUSTOMER')

    def test_customer_can_open_edit_profile(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('edit_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit your details')

    def test_customer_can_update_email_and_username(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('edit_profile'), {
            'username': 'clarity_customer_updated',
            'email': 'updated@example.com',
            'first_name': 'Clarity',
            'last_name': 'Customer',
            'phone': '+4912345',
        })
        self.assertRedirects(response, reverse('profile_hub'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.username, 'clarity_customer_updated')
        self.assertEqual(self.customer.email, 'updated@example.com')
