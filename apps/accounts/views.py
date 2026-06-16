from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView
from apps.core.api import api_response
from .serializers import UserSerializer

class MeView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        return api_response(True, "Profile loaded", UserSerializer(request.user).data)

class SmartTokenObtainPairView(TokenObtainPairView):
    pass

class SmartTokenRefreshView(TokenRefreshView):
    pass

class SmartTokenBlacklistView(TokenBlacklistView):
    pass
