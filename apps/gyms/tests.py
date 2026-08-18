from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.gyms.models import Gym, GymImage, MembershipPlan
from apps.gyms.image_hosting import HostedImage

class GymControlCenterUXTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='gym_control_owner',
            email='owner@example.com',
            password='pass12345',
            role=User.Role.OWNER,
        )
        self.customer = User.objects.create_user(
            username='gym_control_customer',
            email='customer@example.com',
            password='pass12345',
            role=User.Role.CUSTOMER,
        )
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='Premium Control Gym',
            slug='premium-control-gym',
            description='A gym used for control center UX tests.',
            city='Bamberg',
            address='Owner Street 1',
            email='gym@example.com',
            starting_price=Decimal('39.00'),
            status=Gym.Status.APPROVED,
        )
        self.plan = MembershipPlan.objects.create(
            gym=self.gym,
            title='Monthly Access',
            description='Full access membership.',
            price=Decimal('49.00'),
            duration_days=30,
        )

    def test_manage_page_uses_premium_control_center_layout(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_gym_manage', args=[self.gym.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gym-control-hero-card')
        self.assertContains(response, 'gym-control-tabs')
        self.assertContains(response, 'plan-card-grid')
        self.assertContains(response, 'plan-control-card')
        self.assertContains(response, 'New plan')
        self.assertContains(response, 'Membership plans')
        self.assertContains(response, 'Analytics')

    def test_edit_page_groups_form_into_professional_sections(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_gym_edit', args=[self.gym.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'management-form-card')
        self.assertContains(response, 'Basic information')
        self.assertContains(response, 'Address and map data')
        self.assertContains(response, 'Customer contact channels')
        self.assertContains(response, 'Save gym profile')
        self.assertContains(response, 'sticky-save-card')

    def test_customer_cannot_manage_owner_gym(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('owner_gym_manage', args=[self.gym.slug]))
        self.assertEqual(response.status_code, 403)

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from .forms import GymImageForm


class GymImageUploadSafetyTests(TestCase):
    @override_settings(MAX_GYM_IMAGE_UPLOAD_MB=1, ALLOWED_GYM_IMAGE_EXTENSIONS=['jpg', 'jpeg', 'png', 'webp'])
    def test_rejects_non_image_upload(self):
        upload = SimpleUploadedFile('bad.txt', b'not-an-image', content_type='text/plain')
        form = GymImageForm(files={'image': upload}, data={'alt_text': 'bad', 'is_cover': ''})
        self.assertFalse(form.is_valid())


class GymExploreFeedTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='explore_feed_owner',
            email='explore-owner@example.com',
            password='pass12345',
            role=User.Role.OWNER,
        )
        for index in range(21):
            Gym.objects.create(
                owner=self.owner,
                name='باشگاه نمونه' if index == 0 else f'Explore Gym {index:02d}',
                slug=f'explore-gym-{index:02d}',
                description='A detailed gym description used to verify the Explore card feed.',
                city='تهران' if index == 0 else 'Bamberg',
                address=f'Explore Street {index}',
                starting_price=Decimal('29.00') + index,
                status=Gym.Status.APPROVED,
            )

    def test_landing_is_separate_from_explore_and_search_targets_marketplace(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Find the gym that fits your lifestyle.')
        self.assertContains(response, f'action="{reverse("gym_list")}"')
        self.assertNotContains(response, 'data-mobile-gym-deck')

        explore = self.client.get(reverse('gym_list'), {'q': 'Explore Gym 05'})
        self.assertEqual(explore.status_code, 200)
        self.assertContains(explore, 'Find your next gym.')
        self.assertContains(explore, 'Explore Gym 05')
        self.assertNotContains(explore, 'Find the gym that fits your lifestyle.')

    def test_first_page_preserves_desktop_pagination_and_mobile_feed_markup(self):
        response = self.client.get(reverse('gym_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['gyms']), 20)
        html = response.content.decode()
        self.assertEqual(html.count('data-mobile-gym-slide data-gym-id='), 20)
        self.assertEqual(html.count('class="mobile-gym-more-info"'), 20)
        self.assertIn('data-mobile-explore-toolbar', html)
        self.assertIn('data-mobile-filter-open', html)
        self.assertIn('data-mobile-search-open', html)
        self.assertIn('data-mobile-search-sheet', html)
        self.assertIn('data-mobile-filter-sheet', html)
        self.assertIn('mobile-filter-form', html)
        self.assertIn('data-next-url="?page=2"', html)
        self.assertIn('class="pagination-shell mt-5"', html)
        self.assertIn('Next 20', html)
        self.assertIn('mobile-gym-meta-row', html)
        self.assertIn('dir="auto"', html)
        self.assertNotIn('explore-filter-visual', html)
        self.assertNotIn('explore-results-toolbar-spacer', html)

    def test_second_page_contains_only_remaining_gym_and_no_next_feed_url(self):
        response = self.client.get(reverse('gym_list'), {'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(len(response.context['gyms']), 1)
        html = response.content.decode()
        self.assertEqual(html.count('data-mobile-gym-slide data-gym-id='), 1)
        self.assertIn('data-next-url=""', html)
        self.assertIn('Previous', html)

from io import BytesIO
from unittest.mock import patch
from PIL import Image as PILImage
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.gyms.models import Gym, GymImage, MembershipPlan


class GymImageExternalHostingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='imgbb_owner',
            email='imgbb-owner@example.com',
            password='pass12345',
            role=User.Role.OWNER,
        )
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='Remote Photo Gym',
            slug='remote-photo-gym',
            description='Gym used to verify remote image storage.',
            city='Bamberg',
            address='Remote Street 1',
            starting_price=Decimal('20.00'),
            status=Gym.Status.APPROVED,
        )

    def _valid_png(self):
        buffer = BytesIO()
        PILImage.new('RGB', (4, 4), (255, 128, 0)).save(buffer, format='PNG')
        return SimpleUploadedFile('gym.png', buffer.getvalue(), content_type='image/png')

    @patch('apps.gyms.forms.upload_image')
    def test_form_stores_remote_url_and_not_local_image(self, mocked_upload):
        mocked_upload.return_value = HostedImage(
            id='remote123',
            url='https://i.ibb.co/example/gym.png',
            display_url='https://i.ibb.co/example/gym.png',
            delete_url='https://ibb.co/delete/example',
            width=4,
            height=4,
            size=80,
        )
        form = GymImageForm(
            data={'alt_text': 'Remote gym', 'is_cover': 'on'},
            files={'image': self._valid_png()},
        )
        self.assertTrue(form.is_valid(), form.errors)
        image = form.save(commit=False)
        image.gym = self.gym
        image.save()

        self.assertFalse(bool(image.image))
        self.assertEqual(image.external_url, 'https://i.ibb.co/example/gym.png')
        self.assertEqual(image.source, 'imgbb')
        self.assertEqual(image.remote_id, 'remote123')
        self.assertEqual(image.image_url, 'https://i.ibb.co/example/gym.png')

    def test_image_url_prefers_remote_url_over_legacy_local_reference(self):
        image = GymImage(
            gym=self.gym,
            image='gyms/legacy.jpg',
            external_url='https://i.ibb.co/example/remote.jpg',
        )
        self.assertEqual(image.image_url, 'https://i.ibb.co/example/remote.jpg')
