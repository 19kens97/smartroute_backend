from django.urls import path
from .views import ChangePasswordView, MeView, ProfileSignatureView, SmartTokenObtainPairView, SmartTokenRefreshView, SmartTokenBlacklistView

urlpatterns = [
    path("token/", SmartTokenObtainPairView.as_view()),
    path("token/refresh/", SmartTokenRefreshView.as_view()),
    path("token/blacklist/", SmartTokenBlacklistView.as_view()),
    path("me/", MeView.as_view()),
    path("change-password/", ChangePasswordView.as_view()),
    path("profile/signature/", ProfileSignatureView.as_view()),
]
