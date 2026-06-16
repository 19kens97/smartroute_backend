from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

def api_response(success=True, message="OK", data=None, errors=None, status_code=status.HTTP_200_OK):
    return Response({"success": success, "message": message, "data": data if data is not None else {}, "errors": errors if errors is not None else {}}, status=status_code)

def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return api_response(False, "Internal server error", {}, {"detail": "Unexpected error"}, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return api_response(False, "Request failed", {}, response.data, response.status_code)
