from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)


def revoke_all_user_refresh_tokens(user) -> int:
    """Révoque tous les refresh tokens enregistrés pour un utilisateur."""
    revoked_count = 0

    for outstanding_token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=outstanding_token)
        if created:
            revoked_count += 1

    return revoked_count
