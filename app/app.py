from fastapi import FastAPI,HTTPException,File,UploadFile,Form ,Depends
from fastapi.staticfiles import StaticFiles
from app.schemas import PostCreate,PostResponse,UserRead,UserCreate,UserUpdate
from app.db import Post,User,create_db_and_tables,get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.images import imagekit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import shutil
import os
import uuid
import tempfile
from app.users import auth_backend,current_active_user,fastapi_users

@asynccontextmanager
async def lifespan(app:FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(fastapi_users.get_auth_router(auth_backend),prefix="/auth/jwt",tags=["auth"])
app.include_router(fastapi_users.get_reset_password_router(),prefix="/auth",tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead,UserCreate),prefix="/auth",tags=["auth"])
app.include_router(fastapi_users.get_verify_router(UserRead),prefix="/auth",tags=["auth"])
app.include_router(fastapi_users.get_users_router(UserRead,UserUpdate),prefix="/users",tags=["users"])
'''
text_posts = {
    1: {
        "title": "Getting Started with FastAPI",
        "content": "FastAPI is a modern Python web framework.",
        "author": "Alice"
    },
    2: {
        "title": "Learning SQLAlchemy",
        "content": "SQLAlchemy is a powerful ORM for Python.",
        "author": "Bob"
    },
    3: {
        "title": "Python Tips",
        "content": "Use list comprehensions for cleaner code.",
        "author": "Charlie"
    },
    4: {
        "title": "REST APIs",
        "content": "REST uses HTTP methods like GET, POST, PUT, and DELETE.",
        "author": "David"
    },
    5: {
        "title": "Authentication",
        "content": "JWT is commonly used for API authentication.",
        "author": "Emma"
    },
    6: {
        "title": "Docker Basics",
        "content": "Docker packages applications into containers.",
        "author": "Frank"
    },
    7: {
        "title": "Async Programming",
        "content": "FastAPI works well with async and await.",
        "author": "Grace"
    },
    8: {
        "title": "PostgreSQL",
        "content": "PostgreSQL is a powerful open-source relational database.",
        "author": "Henry"
    },
    9: {
        "title": "Git Commands",
        "content": "Commit your changes frequently.",
        "author": "Isabella"
    },
    10: {
        "title": "Deployment",
        "content": "You can deploy FastAPI using Uvicorn and Nginx.",
        "author": "Jack"
    }
}

@app.get("/posts")
def get_all_posts():
    return text_posts
#query parameter
@app.get("/posts")
def get_all_posts(limit:int=None):
    if limit:
        return list(text_posts.values())[:limit]
    return text_posts

@app.get("/posts/{post_id}")
def get_post(post_id: int):
    if id not in text_posts:
        raise HTTPException(status_code=404, detail="Post not found")
    return text_posts.get(post_id)
#request body and post
@app.post("/posts")
def create_post(post:PostCreate)->PostResponse:
    new_post={"title":post.title,"content":post.content}
    text_posts[max(text_posts.keys())+1] = {"title":post.title,"content":post.content}
    return new_post
'''
@app.post("/upload")
async def upload_file(
        file: UploadFile = File(...),
        caption: str = Form(...),
        session: AsyncSession = Depends(get_async_session),
        content: str = Form(...),
        user: User = Depends(current_active_user),
):
    temp_file_path=None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            temp_file_path=temp_file.name
            shutil.copyfileobj(file.file, temp_file)
        upload_result=imagekit.upload_file(
            file=open(temp_file_path,"rb"),
            file_name=file.filename,
            options=UploadFileRequestOptions(
                use_unique_file_name=True,
                tags=["backend-upload"]
            )
        )
        if upload_result.response_metadata.http_status_code == 200:
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
            return post
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        file.file.close()





@app.get("/feed")
async def get_feed(
        session: AsyncSession = Depends(get_async_session),
        user:User=Depends(current_active_user)
):
    result=await session.execute(select(Post).order_by(Post.created_at.desc()))
    posts=[row[0] for row in result.all()]
    result=await session.execute(select(User))
    users=[row[0] for row in result.all()]
    user_dict={u.id:u.email for u in users}
    posts_data=[]
    for post in posts:
        posts_data.append({
            "id":str(post.id),
            "user_id":str(post.user_id),
            "caption":post.caption,
            "url":post.url,
            "file_type":post.file_type,
            "file_name":post.file_name,
            "created_at":post.created_at.isoformat(),
            "is_owner":post.user_id==user.id,
            "email":user_dict.get(post.user_id,"Unknown")
        }
        )
    return {"posts":posts_data}
@app.delete("/posts/{post_id}")
async def delete_post(
        post_id: str,
        session: AsyncSession = Depends(get_async_session),
        user:User=Depends(current_active_user)
):
    try:
        post_uuid=uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post id")
    try:
        result=await session.execute(select(Post).where(Post.id == post_uuid))
        post=result.scalars().first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.user_id != user.id:
            raise HTTPException(status_code=403, detail="Unauthorized, You are not allowed to perform this action")
        await session.delete(post)
        await session.commit()
        return {"message":"Post deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/", StaticFiles(directory="static", html=True), name="static")

