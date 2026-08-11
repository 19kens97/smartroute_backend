from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class ForgotPasswordThrottle(AnonRateThrottle):
    scope = "forgot_password"


class ResetPasswordThrottle(AnonRateThrottle):
    scope = "reset_password"


class LoginIpRateThrottle(AnonRateThrottle):
    scope = "login_ip"


class LoginIdentifierRateThrottle(SimpleRateThrottle):
    scope = "login_identifier"

    def get_cache_key(self, request, view):
        identifier = self.get_identifier(request)
        if not identifier:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": identifier,
        }

    def get_identifier(self, request):
        raw = (
            request.data.get("email")
            or request.data.get("username")
            or request.data.get("dossier_number")
            or ""
        )
        normalized = str(raw).strip().lower()
        if not normalized:
            return None
        return normalized
