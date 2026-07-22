from django.urls import path

from .views import (
    CustomTokenView,
    PersonalLoginAPIView,
    ProfessionalLoginAPIView,
    UserCreateAPIView,
    UserDeactivateAPIView,
    UserDetailView,
    UserListView,
    UserProfileUpdateView,
    UserProfileView,
)

urlpatterns = [
    path(
        "auth/professional/login/",
        ProfessionalLoginAPIView.as_view(),
        name="professional-login",
    ),
    path(
        "auth/personal/login/",
        PersonalLoginAPIView.as_view(),
        name="personal-login",
    ),
    path(
        "auth/token/refresh/",
        CustomTokenView.as_view(),
        name="token-refresh",
    ),
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/create/", UserCreateAPIView.as_view(), name="user-create"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path(
        "users/<int:pk>/deactivate/",
        UserDeactivateAPIView.as_view(),
        name="user-deactivate",
    ),
    path("me/", UserProfileView.as_view(), name="user-profile"),
    path("me/update/", UserProfileUpdateView.as_view(), name="user-profile-update"),
]
