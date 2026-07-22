import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


logger = logging.getLogger(__name__)


STATUS_MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "Données invalides.",
    status.HTTP_401_UNAUTHORIZED: "Authentification requise.",
    status.HTTP_403_FORBIDDEN: "Accès interdit.",
    status.HTTP_404_NOT_FOUND: "Ressource introuvable.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Méthode non autorisée.",
    status.HTTP_409_CONFLICT: "Conflit détecté.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Trop de requêtes.",
}


def api_response(
    success=True,
    message="OK",
    data=None,
    errors=None,
    status_code=status.HTTP_200_OK,
    headers=None,
):
    payload = {
        "success": bool(success),
        "message": str(message),
        "data": data if data is not None else {},
        "errors": errors if errors is not None else {},
    }
    return Response(payload, status=status_code, headers=headers)


def success_response(message="OK", data=None, status_code=status.HTTP_200_OK, headers=None):
    return api_response(
        success=True,
        message=message,
        data=data,
        status_code=status_code,
        headers=headers,
    )


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST, headers=None):
    return api_response(
        success=False,
        message=message,
        errors=errors,
        status_code=status_code,
        headers=headers,
    )


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        request = context.get("request")
        logger.exception(
            "event=unhandled_api_exception request_id=%s path=%s",
            getattr(request, "request_id", "-"),
            getattr(request, "path", ""),
            exc_info=exc,
        )
        return api_response(
            False,
            "Erreur interne du serveur.",
            {},
            {"detail": "Une erreur inattendue est survenue."},
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    message = STATUS_MESSAGES.get(
        response.status_code,
        "La requête n'a pas pu être traitée.",
    )

    return api_response(
        False,
        message,
        {},
        response.data,
        response.status_code,
        headers=response.headers,
    )
