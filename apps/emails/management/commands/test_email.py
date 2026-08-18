from django.core.management.base import BaseCommand, CommandError
from apps.emails.services import send_app_email


class Command(BaseCommand):
    help = 'Send a test myGym email to verify console/SMTP email configuration.'

    def add_arguments(self, parser):
        parser.add_argument('to_email', type=str)

    def handle(self, *args, **options):
        to_email = options['to_email']
        ok = send_app_email(
            to_email,
            'myGym email system test',
            'welcome',
            {'user': type('DemoUser', (), {'username': 'Admin'})(), 'role': 'Test recipient'},
            fail_silently=False,
        )
        if not ok:
            raise CommandError('Email was not sent. Check recipient and email settings.')
        self.stdout.write(self.style.SUCCESS(f'Test email sent to {to_email}'))
