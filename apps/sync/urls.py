from django.urls import path
from .views import SyncPullView, SyncPushView, SyncStatusView

urlpatterns = [path("push/", SyncPushView.as_view()), path("pull/", SyncPullView.as_view()), path("status/", SyncStatusView.as_view())]
