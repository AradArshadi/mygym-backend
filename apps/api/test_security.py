from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase


class LoginSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="security_customer",
            email="security@example.com",
            password="CorrectPassword123!",
            role=getattr(User.Role, "CUSTOMER", "CUSTOMER"),
        )

    def tearDown(self):
        cache.clear()

    def _csrf_client(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        token = response.json()["csrfToken"]
        return client, token

    def test_login_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/v1/auth/login/",
            data={
                "username": self.user.username,
                "password": "CorrectPassword123!",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_valid_csrf_allows_login_request(self):
        client, token = self._csrf_client()
        response = client.post(
            "/api/v1/auth/login/",
            data={
                "username": self.user.username,
                "password": "wrong-password",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)

    def test_repeated_failed_logins_are_throttled(self):
        client, token = self._csrf_client()
        responses = []
        for _ in range(10):
            response = client.post(
                "/api/v1/auth/login/",
                data={
                    "username": self.user.username,
                    "password": "wrong-password",
                },
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )
            responses.append(response.status_code)

        self.assertIn(
            429,
            responses,
            msg=f"No throttling occurred. Responses: {responses}",
        )

    def test_login_throttle_does_not_return_500(self):
        client, token = self._csrf_client()
        statuses = []
        for _ in range(10):
            response = client.post(
                "/api/v1/auth/login/",
                data={
                    "username": self.user.username,
                    "password": "wrong-password",
                },
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )
            statuses.append(response.status_code)

        self.assertNotIn(500, statuses)
