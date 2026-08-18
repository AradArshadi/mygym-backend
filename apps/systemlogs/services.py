import logging
import traceback

logger = logging.getLogger('mygym.events')


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_event(*, level='INFO', category='SYSTEM', event='event', message='', actor=None, request=None,
              related_model='', related_id='', metadata=None, exc_info=None):
    """Write operational events to both Python logging and the database.

    This function is intentionally defensive: logging must never break the product.
    If the database table is missing during deployment, file logging still works.
    """
    metadata = metadata or {}
    if exc_info:
        if exc_info is True:
            import sys
            exc_info = sys.exc_info()
        metadata.setdefault('exception', ''.join(traceback.format_exception(*exc_info)))

    log_message = f'[{category}] {event} | {message} | actor={getattr(actor, "username", None)} | related={related_model}:{related_id} | metadata={metadata}'
    log_level = getattr(logging, str(level).upper(), logging.INFO)
    logger.log(log_level, log_message)

    try:
        from .models import SystemLog
        SystemLog.objects.create(
            level=str(level).upper(),
            category=category,
            event=event,
            message=message,
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            related_model=related_model or '',
            related_id=str(related_id or ''),
            metadata=metadata,
            path=request.path if request else '',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
        )
    except Exception:
        logger.exception('Failed to persist SystemLog database entry')
