import logging
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.api import api_response
from apps.infractions.models import Infraction
from apps.scans.models import GeminiScan, Scan
from apps.sync.models import SyncLog
from apps.tickets.models import Ticket, TicketInfraction

logger = logging.getLogger(__name__)


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get_days(self, request):
        raw_days = request.query_params.get("days", "7")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 7
        return min(max(days, 1), 31)

    def get_period(self, days):
        today = timezone.localdate()
        start_date = today - timedelta(days=days - 1)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(timezone.datetime.combine(today + timedelta(days=1), timezone.datetime.min.time()))
        return today, start_date, start_dt, end_dt

    def get(self, request):
        started_at = timezone.now()
        days = self.get_days(request)
        logger.info("event=dashboard_summary_started request_id=%s user_id=%s days=%s", getattr(request, "request_id", "-"), request.user.pk, days)
        today, start_date, start_dt, end_dt = self.get_period(days)
        dates = [start_date + timedelta(days=index) for index in range(days)]

        scan_rows = (
            Scan.objects.filter(created_at__gte=start_dt, created_at__lt=end_dt)
            .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(count=Count("id"))
        )
        gemini_rows = (
            GeminiScan.objects.filter(scanned_at__gte=start_dt, scanned_at__lt=end_dt)
            .annotate(day=TruncDate("scanned_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(count=Count("id"))
        )
        ticket_rows = (
            Ticket.objects.filter(created_at__gte=start_dt, created_at__lt=end_dt)
            .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(count=Count("id"))
        )

        scans_by_day = {row["day"]: row["count"] for row in scan_rows}
        for row in gemini_rows:
            scans_by_day[row["day"]] = scans_by_day.get(row["day"], 0) + row["count"]
        tickets_by_day = {row["day"]: row["count"] for row in ticket_rows}

        daily_activity = [
            {
                "date": day.isoformat(),
                "label": day.strftime("%d/%m"),
                "scans": scans_by_day.get(day, 0),
                "tickets": tickets_by_day.get(day, 0),
            }
            for day in dates
        ]

        scans_total = sum(item["scans"] for item in daily_activity)
        tickets_total = sum(item["tickets"] for item in daily_activity)
        infraction_total = TicketInfraction.objects.filter(ticket__created_at__gte=start_dt, ticket__created_at__lt=end_dt).count()
        pending_sync = SyncLog.objects.exclude(status="SUCCESS").count()

        top_rows = list(
            TicketInfraction.objects.filter(ticket__created_at__gte=start_dt, ticket__created_at__lt=end_dt)
            .values("infraction_id", "infraction__code", "infraction__label")
            .annotate(count=Count("id"))
            .order_by("-count", "infraction__code")[:5]
        )
        top_infractions = [
            {
                "id": row["infraction_id"],
                "number": row["infraction__code"],
                "label": row["infraction__label"],
                "count": row["count"],
                "percentage": round((row["count"] / infraction_total) * 100, 1) if infraction_total else 0,
            }
            for row in top_rows
        ]

        activity_distribution = [
            {"key": "scans", "label": "Scans", "count": scans_total},
            {"key": "tickets", "label": "PV", "count": tickets_total},
        ]

        by_status = dict(Ticket.objects.values_list("status").annotate(c=Count("id")))
        data = {
            "period": {
                "days": days,
                "start_date": start_date.isoformat(),
                "end_date": today.isoformat(),
            },
            "totals": {
                "scans": scans_total,
                "tickets": tickets_total,
                "infractions": infraction_total,
                "pending_sync": pending_sync,
            },
            "daily_activity": daily_activity,
            "activity_distribution": activity_distribution,
            "top_infractions": top_infractions,
            "tickets_by_status": by_status,
            "total_tickets": Ticket.objects.count(),
            "scans_today": scans_by_day.get(today, 0),
            "tickets_today": tickets_by_day.get(today, 0),
            "pending_sync": pending_sync,
            "alerts_today": 0,
        }
        duration_ms = (timezone.now() - started_at).total_seconds() * 1000
        logger.info("event=dashboard_summary_completed request_id=%s user_id=%s days=%s scans=%s tickets=%s duration_ms=%.2f", getattr(request, "request_id", "-"), request.user.pk, days, scans_total, tickets_total, duration_ms)
        return api_response(True, "Dashboard summary", data)



