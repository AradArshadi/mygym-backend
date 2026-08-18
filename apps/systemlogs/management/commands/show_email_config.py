from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Show sanitized email configuration for debugging deployment issues.'

    def handle(self, *args, **options):
        password = getattr(settings, 'EMAIL_HOST_PASSWORD', '')
        masked = 'SET' if password else 'EMPTY'
        self.stdout.write(f'EMAIL_BACKEND={settings.EMAIL_BACKEND}')
        self.stdout.write(f'EMAIL_HOST={settings.EMAIL_HOST}')
        self.stdout.write(f'EMAIL_PORT={settings.EMAIL_PORT}')
        self.stdout.write(f'EMAIL_USE_TLS={settings.EMAIL_USE_TLS}')
        self.stdout.write(f'EMAIL_USE_SSL={getattr(settings, "EMAIL_USE_SSL", False)}')
        self.stdout.write(f'EMAIL_HOST_USER={settings.EMAIL_HOST_USER}')
        self.stdout.write(f'EMAIL_HOST_PASSWORD={masked}')
        self.stdout.write(f'EMAIL_TIMEOUT={getattr(settings, "EMAIL_TIMEOUT", "")}')
        self.stdout.write(f'DEFAULT_FROM_EMAIL={settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'SERVER_EMAIL={getattr(settings, "SERVER_EMAIL", "")}')
        self.stdout.write(f'SUPPORT_EMAIL={settings.SUPPORT_EMAIL}')
        self.stdout.write(f'SITE_URL={getattr(settings, "SITE_URL", "")}')
        if 'smtp.EmailBackend' in settings.EMAIL_BACKEND and not settings.EMAIL_HOST_PASSWORD:
            self.stdout.write(self.style.WARNING('SMTP backend is active but EMAIL_HOST_PASSWORD is empty.'))
        if 'console.EmailBackend' in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING('Console backend prints email in terminal and does not send real email.'))
