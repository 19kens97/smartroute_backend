from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from apps.core.api import api_response
from apps.tickets.models import Ticket

class TicketsReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        data = list(Ticket.objects.values("id", "status", "driver_license", "plate_number_snapshot", "created_at")[:100])
        return api_response(True, "Tickets report", {"results": data})
