from django.contrib.auth import get_user_model
from rest_framework import serializers
User=get_user_model()

class UserSerializer(serializers.ModelSerializer):
    full_name=serializers.SerializerMethodField()

    def get_full_name(self, obj):
        full=f"{obj.first_name} {obj.last_name}".strip()
        return full or obj.username

    class Meta:
        model=User
        fields=(
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "badge_number",
            "phone",
            "precinct",
            "post",
            "nif",
        )
