from django.urls import path
from .views import TicketsReportView
urlpatterns=[path("tickets/", TicketsReportView.as_view())]
