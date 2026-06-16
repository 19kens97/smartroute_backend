from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from apps.core.api import api_response
from apps.tickets.models import Ticket

class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        by_status = {k: v for k, v in Ticket.objects.values_list("status").annotate(c=Count("id"))}
        return api_response(True, "Dashboard summary", {"tickets_by_status": by_status, "total_tickets": Ticket.objects.count()})
