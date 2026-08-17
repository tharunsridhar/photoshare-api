import uuid

from django.conf import settings
from django.db import models


class Post(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # indexed: every /feed query and the ownership check on delete filter by this FK
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts", db_index=True)
    caption = models.TextField(blank=True)
    url = models.CharField(max_length=2048)
    # populated asynchronously by generate_thumbnail_task (apps/posts/tasks.py)
    # after upload - null until the background job runs, which is why /feed
    # and /posts/{id} treat it as optional rather than waiting on it
    thumbnail_url = models.CharField(max_length=2048, null=True, blank=True)
    file_type = models.CharField(max_length=20)
    file_name = models.CharField(max_length=255)
    # indexed: /feed's default (and only) sort order is created_at desc
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.id} ({self.file_type})"
