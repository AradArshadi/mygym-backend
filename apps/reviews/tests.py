from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.gyms.models import Gym
from apps.reviews.models import Favorite


class FavoriteGymTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='fav_owner', password='pass12345', role=User.Role.OWNER)
        self.customer = User.objects.create_user(username='fav_customer', password='pass12345', role=User.Role.CUSTOMER)
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='Favorite Gym',
            slug='favorite-gym',
            description='Favorite test.',
            city='Bamberg',
            address='Fav Street 1',
            email='fav@example.com',
            starting_price=Decimal('30.00'),
            status=Gym.Status.APPROVED,
        )

    def test_customer_can_add_and_remove_favorite(self):
        self.client.force_login(self.customer)
        url = reverse('toggle_favorite', args=[self.gym.id])
        response = self.client.post(url, {'next': reverse('gym_detail', args=[self.gym.slug])})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Favorite.objects.filter(user=self.customer, gym=self.gym).exists())
        response = self.client.post(url, {'next': reverse('gym_detail', args=[self.gym.slug])})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Favorite.objects.filter(user=self.customer, gym=self.gym).exists())

    def test_gym_detail_shows_favorite_button(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('gym_detail', args=[self.gym.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add to favorites')
