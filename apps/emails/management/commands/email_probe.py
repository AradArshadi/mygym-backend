from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils.html import strip_tags


class Command(BaseCommand):
    help = 'Deep email diagnostic: print sanitized config, open connection, and send a test email.'

    def add_arguments(self, parser):
        parser.add_argument('to_email', type=str)
        parser.add_argument('--template', action='store_true', help='Send the branded myGym welcome template.')
        parser.add_argument('--subject', default='myGym SMTP diagnostic test')

    @staticmethod
    def mask(value):
        if not value:
            return 'EMPTY'
        value = str(value)
        if len(value) <= 4:
            return 'SET'
        return f'{value[:2]}***{value[-2:]}'

    def handle(self, *args, **options):
        to_email = options['to_email']
        subject = options['subject']

        self.stdout.write('Email configuration:')
        self.stdout.write(f'  EMAIL_BACKEND={settings.EMAIL_BACKEND}')
        self.stdout.write(f'  EMAIL_HOST={getattr(settings, "EMAIL_HOST", "")}')
        self.stdout.write(f'  EMAIL_PORT={getattr(settings, "EMAIL_PORT", "")}')
        self.stdout.write(f'  EMAIL_USE_TLS={getattr(settings, "EMAIL_USE_TLS", False)}')
        self.stdout.write(f'  EMAIL_USE_SSL={getattr(settings, "EMAIL_USE_SSL", False)}')
        self.stdout.write(f'  EMAIL_HOST_USER={getattr(settings, "EMAIL_HOST_USER", "")}')
        self.stdout.write(f'  EMAIL_HOST_PASSWORD={self.mask(getattr(settings, "EMAIL_HOST_PASSWORD", ""))}')
        self.stdout.write(f'  EMAIL_TIMEOUT={getattr(settings, "EMAIL_TIMEOUT", "")}')
        self.stdout.write(f'  DEFAULT_FROM_EMAIL={settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'  SERVER_EMAIL={getattr(settings, "SERVER_EMAIL", "")}')
        self.stdout.write(f'  SUPPORT_EMAIL={getattr(settings, "SUPPORT_EMAIL", "")}')
        self.stdout.write(f'  SITE_URL={getattr(settings, "SITE_URL", "")}')
        self.stdout.write('')

        if 'console.EmailBackend' in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING(
                'Console email backend is active. This is correct for local dev, but it does not deliver real emails.'
            ))

        try:
            connection = get_connection(fail_silently=False)
            self.stdout.write('Opening email connection...')
            connection.open()
            self.stdout.write(self.style.SUCCESS('Connection opened.'))

            if options['template']:
                demo_user = type('DemoUser', (), {'username': 'SMTP Tester'})()
                html_body = render_to_string('emails/welcome.html', {
                    'user': demo_user,
                    'role': 'SMTP diagnostic recipient',
                    'brand_name': 'myGym',
                    'support_email': getattr(settings, 'SUPPORT_EMAIL', settings.DEFAULT_FROM_EMAIL),
                    'site_url': getattr(settings, 'SITE_URL', ''),
                })
                text_body = strip_tags(html_body)
            else:
                text_body = 'This is a myGym SMTP diagnostic email. If you received this, email delivery works.'
                html_body = '<h2>myGym SMTP diagnostic</h2><p>If you received this, email delivery works.</p>'

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
                connection=connection,
            )
            email.attach_alternative(html_body, 'text/html')

            self.stdout.write(f'Sending email to {to_email}...')
            sent_count = email.send(fail_silently=False)
            connection.close()

            if sent_count != 1:
                raise CommandError(f'Email send returned sent_count={sent_count}, expected 1.')

            self.stdout.write(self.style.SUCCESS(f'Diagnostic email sent to {to_email}.'))
        except Exception as exc:
            raise CommandError(f'SMTP diagnostic failed: {exc.__class__.__name__}: {exc}')
