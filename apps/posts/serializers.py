from rest_framework import serializers

from apps.posts.models import Post


class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ["id", "user", "caption", "url", "thumbnail_url", "file_type", "file_name", "created_at"]
        read_only_fields = fields
