from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.gyms.models import Gym, GymImage


class RestoreDemoCoverTests(TestCase):
    def test_restores_only_missing_demo_svgs_without_changing_records(self):
        owner = User.objects.create_user(username='cover-owner', role='OWNER')
        gym = Gym.objects.create(owner=owner, name='Gym <&>', slug='cover-gym', description='Test', city='Test', address='Test', starting_price=10)
        missing = GymImage.objects.create(gym=gym, source='placeholder', image='gyms/generated/demo.svg')
        GymImage.objects.create(gym=gym, source='owner_upload', image='gyms/generated/owner.svg')
        GymImage.objects.create(gym=gym, source='placeholder', image='gyms/generated/../../outside.svg')
        GymImage.objects.create(gym=gym, source='placeholder', image='gyms/generated/remote.svg', external_url='https://example.com/photo.jpg')
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            call_command('restore_demo_covers', stdout=StringIO())
            target = Path(directory) / missing.image.name
            content = target.read_text(encoding='utf-8')
            self.assertIn('Gym &lt;&amp;&gt; - demo illustration', content)
            self.assertFalse((Path(directory) / 'gyms/generated/owner.svg').exists())
            self.assertFalse((Path(directory) / 'gyms/generated/remote.svg').exists())
            target.write_text('Existing content', encoding='utf-8')
            call_command('restore_demo_covers', stdout=StringIO())
            self.assertEqual(target.read_text(encoding='utf-8'), 'Existing content')
        missing.refresh_from_db()
        self.assertEqual(missing.image.name, 'gyms/generated/demo.svg')
