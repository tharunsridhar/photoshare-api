"""ORM models + async engine/session."""

import asyncio
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

# psycopg's async mode can't run on Windows' default ProactorEventLoop - every
# entrypoint that ends up importing this module (uvicorn, alembic env.py,
# pytest) needs the selector loop instead. Setting the policy here, once, at
# import time covers all of them from a single place.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    posts = relationship("Post", back_populates="user")


class Post(Base):
    __tablename__ = "posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # indexed: every /feed query and the ownership check on delete filter by this FK
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)
    caption = Column(Text)
    url = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    # populated asynchronously by generate_thumbnail_task (app/tasks.py) after
    # upload - null until the background job runs, which is why /feed and
    # /posts/{id} treat it as optional rather than waiting on it
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # indexed: /feed's default (and only) sort order is created_at desc
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    user = relationship("User", back_populates="posts")


# pool_size + max_overflow: up to 15 concurrent connections from one app
# instance. pool_timeout: fail fast (30s) instead of hanging when the pool
# is exhausted. pool_recycle: recycle connections every 30 min so we never
# hand out one a managed Postgres provider has silently closed for being
# idle too long. pool_pre_ping: a cheap check before handing out a pooled
# connection, so a dead one surfaces as a quick reconnect, not a mid-request
# "server closed the connection unexpectedly".
engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)
