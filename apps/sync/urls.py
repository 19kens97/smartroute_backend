from django.urls import path

from .views import (
    SyncDeviceRegisterView,
    SyncDeviceRevokeView,
    SyncDevicesView,
    SyncPullView,
    SyncPushView,
    SyncStatusView,
)


app_name = "sync"

urlpatterns = [
    path(
        "devices/",
        SyncDevicesView.as_view(),
        name="devices",
    ),
    path(
        "devices/register/",
        SyncDeviceRegisterView.as_view(),
        name="device-register",
    ),
    path(
        "devices/revoke/",
        SyncDeviceRevokeView.as_view(),
        name="device-revoke",
    ),
    path("push/", SyncPushView.as_view(), name="push"),
    path("pull/", SyncPullView.as_view(), name="pull"),
    path("status/", SyncStatusView.as_view(), name="status"),
]
