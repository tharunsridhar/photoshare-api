from django.contrib import admin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "is_active", "is_verified", "is_staff", "created_at"]
    search_fields = ["email"]
    ordering = ["-created_at"]
