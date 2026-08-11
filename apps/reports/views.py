from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.core.api import api_response
from apps.core.openapi import ApiEnvelopeSerializer

from .pagination import ReportsPagination
from .permissions import ReportsPermission
from .serializers import (
    AgentReportSerializer,
    DelitReportSerializer,
    InfractionReportSerializer,
    TicketReportSerializer,
    VerbalizationReportSerializer,
)
from .services import (
    build_summary,
    get_agent_report_queryset,
    get_delit_report_queryset,
    get_infraction_report_queryset,
    get_ticket_report_queryset,
    get_verbalization_report_queryset,
    serialize_agent_row,
    serialize_delit_row,
    serialize_infraction_row,
    serialize_ticket_row,
    serialize_verbalization_row,
)


class BaseReportView(APIView):
    permission_classes = [ReportsPermission]
    pagination_class = ReportsPagination

    def paginate(self, request, queryset, serializer_class, row_builder):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = [row_builder(item) for item in page]
        serializer = serializer_class(rows, many=True)
        return paginator.get_paginated_response(serializer.data)

    def run_report(
        self,
        request,
        queryset_builder,
        serializer_class,
        row_builder,
    ):
        try:
            queryset = queryset_builder(request.query_params)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"filters": str(exc)}) from exc

        return self.paginate(
            request,
            queryset,
            serializer_class,
            row_builder,
        )


class ReportsSummaryView(BaseReportView):
    @extend_schema(responses={200: ApiEnvelopeSerializer}, tags=["reports"])
    def get(self, request):
        try:
            data = build_summary(request.query_params)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"filters": str(exc)}) from exc

        return api_response(
            True,
            "Résumé des rapports.",
            data,
        )


class TicketsReportView(BaseReportView):
    @extend_schema(responses={200: TicketReportSerializer(many=True)}, tags=["reports"])
    def get(self, request):
        return self.run_report(
            request,
            get_ticket_report_queryset,
            TicketReportSerializer,
            serialize_ticket_row,
        )


class VerbalizationsReportView(BaseReportView):
    @extend_schema(responses={200: VerbalizationReportSerializer(many=True)}, tags=["reports"])
    def get(self, request):
        return self.run_report(
            request,
            get_verbalization_report_queryset,
            VerbalizationReportSerializer,
            serialize_verbalization_row,
        )


class InfractionsReportView(BaseReportView):
    @extend_schema(responses={200: InfractionReportSerializer(many=True)}, tags=["reports"])
    def get(self, request):
        return self.run_report(
            request,
            get_infraction_report_queryset,
            InfractionReportSerializer,
            serialize_infraction_row,
        )


class DelitsReportView(BaseReportView):
    @extend_schema(responses={200: DelitReportSerializer(many=True)}, tags=["reports"])
    def get(self, request):
        return self.run_report(
            request,
            get_delit_report_queryset,
            DelitReportSerializer,
            serialize_delit_row,
        )


class AgentsReportView(BaseReportView):
    @extend_schema(responses={200: AgentReportSerializer(many=True)}, tags=["reports"])
    def get(self, request):
        return self.run_report(
            request,
            get_agent_report_queryset,
            AgentReportSerializer,
            serialize_agent_row,
        )
