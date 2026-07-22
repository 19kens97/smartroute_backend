from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("nif", "first_name", "last_name", "birth_date")
    search_fields = ("nif", "first_name", "last_name")


@admin.register(get_user_model())
class UserAdmin(DjangoUserAdmin):
    search_fields = ("username", "email", "person__nif", "person__first_name", "person__last_name")
