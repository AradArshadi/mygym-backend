from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """
    IP-based throttling specifically for the login endpoint.

    The actual rate is configured through REST_FRAMEWORK:
        DEFAULT_THROTTLE_RATES["login"]
    """

    scope = "login"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }
