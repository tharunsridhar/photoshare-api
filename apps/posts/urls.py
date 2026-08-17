from django.urls import path

from apps.posts.views import FeedView, PostDetailView, UploadView

urlpatterns = [
    path("upload", UploadView.as_view(), name="upload"),
    path("feed", FeedView.as_view(), name="feed"),
    path("posts/<str:post_id>", PostDetailView.as_view(), name="post-detail"),
]
