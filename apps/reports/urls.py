from django.urls import path

from .views import (
    AgentsReportView,
    DelitsReportView,
    InfractionsReportView,
    ReportsSummaryView,
    TicketsReportView,
    VerbalizationsReportView,
)


app_name = "reports"

urlpatterns = [
    path("summary/", ReportsSummaryView.as_view(), name="summary"),
    path("tickets/", TicketsReportView.as_view(), name="tickets"),
    path(
        "verbalizations/",
        VerbalizationsReportView.as_view(),
        name="verbalizations",
    ),
    path(
        "infractions/",
        InfractionsReportView.as_view(),
        name="infractions",
    ),
    path("delits/", DelitsReportView.as_view(), name="delits"),
    path("agents/", AgentsReportView.as_view(), name="agents"),
]
