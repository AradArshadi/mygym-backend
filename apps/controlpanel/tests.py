from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from apps.accounts.models import User


class ControlPanelSafetyTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_user', password='pass12345', role=User.Role.ADMIN, is_staff=True)
        self.customer = User.objects.create_user(username='customer_user', password='pass12345', role=User.Role.CUSTOMER)

    def test_customer_cannot_access_safety_center(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('control_security'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_safety_center(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('control_security'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Safety Center')

    @override_settings(DEMO_TOOLS_ENABLED=False)
    def test_demo_tools_disabled_message(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('control_demo_tools'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Demo tools are disabled')


    @override_settings(DEMO_TOOLS_ENABLED=True)
    @patch('apps.controlpanel.views.call_command')
    def test_admin_can_seed_core_gym_data_from_demo_tools(self, mocked_call_command):
        def write_output(command_name, *args, **kwargs):
            kwargs['stdout'].write('Demo data created.\n')

        mocked_call_command.side_effect = write_output
        self.client.force_login(self.admin)

        response = self.client.post(reverse('control_demo_tools'), {
            'action': 'seed_gym_data',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Demo data created.')
        mocked_call_command.assert_called_once()
        self.assertEqual(mocked_call_command.call_args.args[0], 'seed_demo')

    @override_settings(DEMO_TOOLS_ENABLED=False)
    @patch('apps.controlpanel.views.call_command')
    def test_disabled_demo_tools_do_not_run_gym_seed(self, mocked_call_command):
        self.client.force_login(self.admin)

        response = self.client.post(reverse('control_demo_tools'), {
            'action': 'seed_gym_data',
        })

        self.assertRedirects(response, reverse('control_demo_tools'))
        mocked_call_command.assert_not_called()
