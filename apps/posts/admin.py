from django.contrib import admin

from apps.posts.models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "file_type", "created_at"]
    search_fields = ["caption", "file_name"]
