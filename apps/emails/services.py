import logging
import sys

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.systemlogs.services import log_event

email_logger = logging.getLogger('mygym.emails')


def send_app_email(to_email, subject, template_name, context=None, *, fail_silently=True, actor=None, request=None, related_model='', related_id=''):
    """Send a branded myGym email with full diagnostics.

    The function logs every attempt, success and failure. During development and deployment,
    this makes SMTP problems visible in logs/emails.log, logs/mygym.log and the Control Deck logs.
    """
    if not to_email:
        log_event(
            level='WARNING',
            category='EMAIL',
            event='email_skipped_missing_recipient',
            message=f'Skipped email: {subject}',
            actor=actor,
            request=request,
            related_model=related_model,
            related_id=related_id,
        )
        return False

    context = context or {}
    context.setdefault('brand_name', 'myGym')
    context.setdefault('support_email', getattr(settings, 'SUPPORT_EMAIL', settings.DEFAULT_FROM_EMAIL))
    context.setdefault('site_url', getattr(settings, 'SITE_URL', ''))

    email_logger.info('Preparing email subject=%s to=%s template=%s backend=%s host=%s user=%s',
                      subject, to_email, template_name, settings.EMAIL_BACKEND, settings.EMAIL_HOST, settings.EMAIL_HOST_USER)

    try:
        html_body = render_to_string(f'emails/{template_name}.html', context)
        text_body = strip_tags(html_body)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        email.attach_alternative(html_body, 'text/html')
        sent_count = email.send(fail_silently=False)
        ok = sent_count > 0

        log_event(
            level='INFO' if ok else 'WARNING',
            category='EMAIL',
            event='email_sent' if ok else 'email_not_sent',
            message=f'Subject={subject} To={to_email} Sent count={sent_count}',
            actor=actor,
            request=request,
            related_model=related_model,
            related_id=related_id,
            metadata={
                'subject': subject,
                'to_email': to_email,
                'template': template_name,
                'backend': settings.EMAIL_BACKEND,
                'host': settings.EMAIL_HOST,
            },
        )
        email_logger.info('Email result subject=%s to=%s sent_count=%s', subject, to_email, sent_count)
        return ok
    except Exception as exc:
        email_logger.exception('Email failed subject=%s to=%s template=%s', subject, to_email, template_name)
        log_event(
            level='ERROR',
            category='EMAIL',
            event='email_failed',
            message=f'{subject} to {to_email} failed: {exc}',
            actor=actor,
            request=request,
            related_model=related_model,
            related_id=related_id,
            metadata={'subject': subject, 'to_email': to_email, 'template': template_name, 'backend': settings.EMAIL_BACKEND},
            exc_info=sys.exc_info(),
        )
        if not fail_silently:
            raise
        return False


def send_welcome_email(user, *, request=None):
    return send_app_email(
        user.email,
        'Welcome to myGym',
        'welcome',
        {'user': user, 'role': user.get_role_display()},
        actor=user,
        request=request,
        related_model='User',
        related_id=user.id,
    )


def send_booking_created_to_owner(booking, *, actor=None, request=None):
    recipient = booking.gym.email or booking.gym.owner.email
    return send_app_email(
        recipient,
        f'New booking request for {booking.gym.name}',
        'booking_created_owner',
        {'booking': booking, 'gym': booking.gym, 'customer': booking.customer},
        actor=actor or booking.customer,
        request=request,
        related_model='Booking',
        related_id=booking.id,
    )


def send_booking_status_to_customer(booking, action_text, *, actor=None, request=None):
    return send_app_email(
        booking.customer.email,
        f'myGym booking {action_text}',
        'booking_status_customer',
        {'booking': booking, 'gym': booking.gym, 'customer': booking.customer, 'action_text': action_text},
        actor=actor,
        request=request,
        related_model='Booking',
        related_id=booking.id,
    )


def send_gym_status_to_owner(gym, action_text, *, actor=None, request=None):
    return send_app_email(
        gym.owner.email,
        f'Your gym was {action_text}',
        'gym_status_owner',
        {'gym': gym, 'owner': gym.owner, 'action_text': action_text},
        actor=actor,
        request=request,
        related_model='Gym',
        related_id=gym.id,
    )


def send_review_notice_to_owner(review, *, actor=None, request=None):
    return send_app_email(
        review.gym.owner.email,
        f'New review for {review.gym.name}',
        'review_notice_owner',
        {'review': review, 'gym': review.gym, 'customer': review.user},
        actor=actor or review.user,
        request=request,
        related_model='Review',
        related_id=review.id,
    )


def send_session_qr_to_customer(session, qr_url, qr_data_uri='', *, actor=None, request=None):
    return send_app_email(
        session.customer.email,
        f'Your myGym session QR for {session.gym.name}',
        'session_qr_customer',
        {'session': session, 'gym': session.gym, 'customer': session.customer, 'qr_url': qr_url, 'qr_data_uri': qr_data_uri},
        actor=actor,
        request=request,
        related_model='Session',
        related_id=session.id,
    )


def send_membership_access_pass_to_customer(subscription, qr_url, qr_data_uri='', *, actor=None, request=None):
    return send_app_email(
        subscription.customer.email,
        f'Your myGym Access Pass for {subscription.gym.name}',
        'membership_access_pass_customer',
        {'subscription': subscription, 'gym': subscription.gym, 'customer': subscription.customer, 'qr_url': qr_url, 'qr_data_uri': qr_data_uri},
        actor=actor,
        request=request,
        related_model='GymSubscription',
        related_id=subscription.id,
    )
