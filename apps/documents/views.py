from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from .models import Document
from .serializers import DocumentSerializer

class DocumentViewSet(ModelViewSet):
    queryset = Document.objects.select_related("vehicle", "uploaded_by").all().order_by("-id")
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)
