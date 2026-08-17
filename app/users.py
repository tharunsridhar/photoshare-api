import uuid

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase

from app.config import settings
from app.db import User, get_user_db


class UserManager(UUIDIDMixin,BaseUserManager[User,uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret=settings.jwt_secret
    async def on_after_register(self, user: User, request: Request | None= None):
        print(f"User{user.id} has registered")
    async def on_after_forgot_password(self,user:User,token:str,request:Request | None= None):
        print(f"user{user.id} has forgotten password.Reset token:{token}")
    async def on_after_request_verify(self, user: User,token:str,request:Request | None= None):
        print(f"Verification requested for user {user.id}. Vertification token:{token}")

async def get_user_manager(user_db:SQLAlchemyUserDatabase=Depends(get_user_db)):
    yield UserManager(user_db)

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
def get_jwt_strategy():
    return JWTStrategy(secret=settings.jwt_secret,lifetime_seconds=settings.jwt_lifetime_seconds)
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy
)
fastapi_users=FastAPIUsers[User,uuid.UUID](get_user_manager,[auth_backend])
current_active_user=fastapi_users.current_user(active=True)


