import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache import (
    bump_feed_version,
    feed_cache_key,
    get_feed_version,
    get_json,
    invalidate_post_cache,
    post_cache_key,
    set_json,
)
from app.config import settings
from app.db import Post, User, get_async_session
from app.images import imagekit
from app.schemas import UserCreate, UserRead, UserUpdate
from app.tasks import generate_thumbnail_task
from app.users import auth_backend, current_active_user, fastapi_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)

# Auth is Bearer-token only (no cookies), so allow_credentials stays False.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"])


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


@app.get("/health", tags=["health"])
async def health_check(session: AsyncSession = Depends(get_async_session)):
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    body = {"status": "ok" if db_status == "ok" else "error", "database": db_status}
    return JSONResponse(content=body, status_code=200 if db_status == "ok" else 503)


@app.post("/upload")
async def upload_file(
        file: UploadFile = File(...),
        caption: str = Form(...),
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user),
):
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            temp_file_path = temp_file.name
            # both of these are blocking calls (disk I/O, then a network call to
            # ImageKit) - running them in a threadpool keeps the event loop free
            # to serve other requests while this upload is in flight
            await run_in_threadpool(shutil.copyfileobj, file.file, temp_file)

        def _do_upload():
            with open(temp_file_path, "rb") as f:
                return imagekit.upload_file(
                    file=f,
                    file_name=file.filename,
                    options=UploadFileRequestOptions(use_unique_file_name=True, tags=["backend-upload"]),
                )

        upload_result = await run_in_threadpool(_do_upload)

        if upload_result.response_metadata.http_status_code != 200:
            raise HTTPException(status_code=502, detail="Media upload failed")

        post = Post(
            user_id=user.id,
            caption=caption,
            url=upload_result.url,
            file_type="video" if file.content_type.startswith("video") else "image",
            file_name=upload_result.name,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)

        await bump_feed_version()
        # fire-and-forget - the worker picks this up separately, off this
        # request entirely; the response doesn't wait on it
        generate_thumbnail_task.delay(str(post.id))

        return post
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        file.file.close()


@app.get("/feed")
async def get_feed(
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user),
        page: int = 1,
        page_size: int = 20,
):
    version = await get_feed_version()
    cache_key = feed_cache_key(version, page, page_size)
    cached_posts = await get_json(cache_key)

    if cached_posts is None:
        # eager-load the owning User via the FK relationship instead of
        # separately fetching every user row in the system and building a
        # lookup dict
        result = await session.execute(
            select(Post)
            .options(selectinload(Post.user))
            .order_by(Post.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        posts = result.scalars().all()
        cached_posts = [_serialize_post(post) for post in posts]
        await set_json(cache_key, cached_posts, settings.feed_cache_ttl_seconds)

    posts_data = [{**post, "is_owner": post["user_id"] == str(user.id)} for post in cached_posts]
    return {"posts": posts_data, "page": page, "page_size": page_size}


@app.get("/posts/{post_id}")
async def get_post_detail(
        post_id: str,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user),
):
    try:
        post_uuid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post id") from None

    cache_key = post_cache_key(post_id)
    cached_post = await get_json(cache_key)

    if cached_post is None:
        result = await session.execute(select(Post).options(selectinload(Post.user)).where(Post.id == post_uuid))
        post = result.scalars().first()
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found")
        cached_post = _serialize_post(post)
        await set_json(cache_key, cached_post, settings.post_cache_ttl_seconds)

    return {**cached_post, "is_owner": cached_post["user_id"] == str(user.id)}


@app.delete("/posts/{post_id}")
async def delete_post(
        post_id: str,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user),
):
    try:
        post_uuid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post id") from None

    result = await session.execute(select(Post).where(Post.id == post_uuid))
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="Unauthorized, You are not allowed to perform this action")
    await session.delete(post)
    await session.commit()
    await bump_feed_version()
    await invalidate_post_cache(post_id)
    return {"message": "Post deleted successfully"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
