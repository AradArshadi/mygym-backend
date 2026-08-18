from django.core import mail
from django.test import TestCase, override_settings
from apps.accounts.models import User
from apps.emails.services import send_welcome_email
class EmailServiceTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_welcome_email_is_sent(self):
        user=User.objects.create_user(username="customer",email="customer@example.com",password="x")
        self.assertTrue(send_welcome_email(user)); self.assertEqual(len(mail.outbox),1)
