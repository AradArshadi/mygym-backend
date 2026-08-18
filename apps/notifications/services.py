from apps.systemlogs.services import log_event

from .models import Notification


def create_notification_safely(*, request=None, **notification_kwargs):
    """Create an in-app notification without hiding failures.

    Notifications are secondary: they should not crash booking/review flows. But if they fail,
    the error must be visible in SystemLog and file logs instead of disappearing silently.
    """
    try:
        return Notification.objects.create(**notification_kwargs)
    except Exception as exc:
        sender = notification_kwargs.get('sender')
        recipient = notification_kwargs.get('recipient')
        log_event(
            level='ERROR',
            category='NOTIFICATION',
            event='notification_create_failed',
            message=f"Failed to create notification '{notification_kwargs.get('title', '')}': {exc}",
            actor=sender,
            request=request,
            related_model='Notification',
            metadata={
                'recipient_id': getattr(recipient, 'id', None),
                'sender_id': getattr(sender, 'id', None),
                'kind': notification_kwargs.get('kind', ''),
                'title': notification_kwargs.get('title', ''),
                'url': notification_kwargs.get('url', ''),
            },
            exc_info=True,
        )
        return None
