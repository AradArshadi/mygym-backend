import logging
import time

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from .services import log_event

request_logger = logging.getLogger('mygym.requests')


class RequestLoggingMiddleware(MiddlewareMixin):
    """Light request/error logging for production debugging.

    It logs errors and optionally all requests when LOG_ALL_REQUESTS=True.
    """
    def process_request(self, request):
        request._mygym_started_at = time.monotonic()

    def process_response(self, request, response):
        duration_ms = None
        if hasattr(request, '_mygym_started_at'):
            duration_ms = round((time.monotonic() - request._mygym_started_at) * 1000, 2)

        should_log_all = getattr(settings, 'LOG_ALL_REQUESTS', False)
        is_error = response.status_code >= 400
        if should_log_all or is_error:
            level = 'ERROR' if response.status_code >= 500 else 'WARNING' if response.status_code >= 400 else 'INFO'
            request_logger.info('%s %s %s %sms', request.method, request.path, response.status_code, duration_ms)
            log_event(
                level=level,
                category='SYSTEM',
                event='http_response',
                message=f'{request.method} {request.path} returned {response.status_code}',
                actor=getattr(request, 'user', None),
                request=request,
                metadata={'method': request.method, 'status_code': response.status_code, 'duration_ms': duration_ms},
            )
        return response

    def process_exception(self, request, exception):
        log_event(
            level='ERROR',
            category='SYSTEM',
            event='unhandled_exception',
            message=str(exception),
            actor=getattr(request, 'user', None),
            request=request,
            exc_info=True,
        )
        return None
