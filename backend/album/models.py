"""Seven persistent entities; historical rows are never physically deleted by commands."""
from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user','admin')"),
        CheckConstraint("status IN ('active','disabled')"),
        CheckConstraint("token_version >= 0 AND admin_failures >= 0 AND login_failures >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(20, collation="BINARY"), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String, default="user")
    status: Mapped[str] = mapped_column(String, default="active")
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    admin_failures: Mapped[int] = mapped_column(Integer, default=0)
    admin_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    login_failures: Mapped[int] = mapped_column(Integer, default=0)
    login_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Work(Base):
    __tablename__ = "works"
    __table_args__ = (
        CheckConstraint("status IN ('visible','removed')"),
        Index("ix_work_status_created", "status", "created_at", "id"),
        Index("ix_work_user_created", "user_id", "created_at", "id"),
        Index("ix_work_date_status", "activity_date", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    seed_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(50), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    activity_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="visible")
    cover_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_mime: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint("kind IN ('image','video')"),
        CheckConstraint("size_bytes > 0 AND position >= 0"),
        Index("ix_media_work_active_position", "work_id", "active", "position"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    kind: Mapped[str] = mapped_column(String)
    file_key: Mapped[str] = mapped_column(Text, unique=True)
    mime: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(10, collation="BINARY"), unique=True)


class WorkTag(Base):
    __tablename__ = "work_tags"
    __table_args__ = (Index("ix_worktag_tag_work", "tag_id", "work_id"),)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comment_work_created", "work_id", "created_at", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("work_id", "user_id"),
        CheckConstraint("score BETWEEN 1 AND 5"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
