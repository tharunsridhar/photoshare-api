import uuid

from django.conf import settings
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.posts import cache
from apps.posts.images import imagekit
from apps.posts.models import Post
from apps.posts.serializers import PostSerializer
from apps.posts.tasks import generate_thumbnail_task


def _serialize_post(post: Post) -> dict:
    """Viewer-independent fields only - this is what goes in the shared
    cache. is_owner depends on who's asking, so it's computed per-request
    after reading from cache, never stored in it."""
    return {
        "id": str(post.id),
        "user_id": str(post.user_id),
        "caption": post.caption,
        "url": post.url,
        "thumbnail_url": post.thumbnail_url,
        "file_type": post.file_type,
        "file_name": post.file_name,
        "created_at": post.created_at.isoformat(),
        "email": post.user.email,
    }


def _parse_post_id(post_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(post_id)
    except ValueError:
        return None


class UploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        file_obj = request.FILES.get("file")
        if file_obj is None:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        # required, not defaulted - the FastAPI port's Form(...) makes caption
        # mandatory too, and a silent "" here would be a quiet contract change
        if "caption" not in request.data:
            return Response({"detail": "caption is required"}, status=status.HTTP_400_BAD_REQUEST)
        caption = request.data["caption"]

        upload_result = imagekit.upload_file(
            file=file_obj,
            file_name=file_obj.name,
            options=UploadFileRequestOptions(use_unique_file_name=True, tags=["backend-upload"]),
        )
        if upload_result.response_metadata.http_status_code != 200:
            return Response({"detail": "Media upload failed"}, status=status.HTTP_502_BAD_GATEWAY)

        post = Post.objects.create(
            user=request.user,
            caption=caption,
            url=upload_result.url,
            file_type="video" if (file_obj.content_type or "").startswith("video") else "image",
            file_name=upload_result.name,
        )
        cache.bump_feed_version()
        # fire-and-forget - the worker picks this up separately, off this
        # request entirely; the response doesn't wait on it
        generate_thumbnail_task.delay(str(post.id))
        return Response(PostSerializer(post).data, status=status.HTTP_201_CREATED)


class FeedView(APIView):
    def get(self, request):
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))

        version = cache.get_feed_version()
        cache_key = cache.feed_cache_key(version, page, page_size)
        cached_posts = cache.get_json(cache_key)

        if cached_posts is None:
            # select_related eager-loads the owning User via the FK instead
            # of separately fetching every user row and building a lookup dict
            start = (page - 1) * page_size
            posts = list(Post.objects.select_related("user").order_by("-created_at")[start : start + page_size])
            cached_posts = [_serialize_post(post) for post in posts]
            cache.set_json(cache_key, cached_posts, settings.FEED_CACHE_TTL_SECONDS)

        posts_data = [{**post, "is_owner": post["user_id"] == str(request.user.id)} for post in cached_posts]
        return Response({"posts": posts_data, "page": page, "page_size": page_size})


class PostDetailView(APIView):
    """GET/DELETE /posts/{post_id}. post_id is a plain <str:...> path
    segment, not Django's <uuid:...> converter - an unparseable id has to
    reach this view and get a clean 400, not a 404 from the URL resolver
    simply failing to match a route."""

    def get(self, request, post_id):
        post_uuid = _parse_post_id(post_id)
        if post_uuid is None:
            return Response({"detail": "Invalid post id"}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = cache.post_cache_key(post_id)
        cached_post = cache.get_json(cache_key)

        if cached_post is None:
            post = Post.objects.select_related("user").filter(id=post_uuid).first()
            if post is None:
                return Response({"detail": "Post not found"}, status=status.HTTP_404_NOT_FOUND)
            cached_post = _serialize_post(post)
            cache.set_json(cache_key, cached_post, settings.POST_CACHE_TTL_SECONDS)

        return Response({**cached_post, "is_owner": cached_post["user_id"] == str(request.user.id)})

    def delete(self, request, post_id):
        post_uuid = _parse_post_id(post_id)
        if post_uuid is None:
            return Response({"detail": "Invalid post id"}, status=status.HTTP_400_BAD_REQUEST)

        post = Post.objects.filter(id=post_uuid).first()
        if post is None:
            return Response({"detail": "Post not found"}, status=status.HTTP_404_NOT_FOUND)
        if post.user_id != request.user.id:
            return Response(
                {"detail": "Unauthorized, You are not allowed to perform this action"},
                status=status.HTTP_403_FORBIDDEN,
            )
        post.delete()
        cache.bump_feed_version()
        cache.invalidate_post_cache(post_id)
        return Response({"message": "Post deleted successfully"})
