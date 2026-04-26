import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean,
    ForeignKey, Integer, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ScrapeStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"


class Profile(Base):
    __tablename__ = "profiles"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_url   = Column(String(2048), unique=True, nullable=False, index=True)
    username     = Column(String(255), index=True)
    display_name = Column(String(255))
    bio          = Column(Text)
    phone        = Column(String(64))
    location     = Column(String(255))
    price        = Column(String(128))
    extra_data   = Column(Text)
    is_active    = Column(Boolean, default=True)
    is_archived  = Column(Boolean, default=False)
    first_seen   = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_scraped = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_changed = Column(DateTime, default=datetime.utcnow, nullable=False)

    photos = relationship(
        "Photo",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="Photo.position",
    )
    advertisements = relationship(
        "Advertisement",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="Advertisement.last_seen.desc()",
    )


class Photo(Base):
    __tablename__ = "photos"

    id                = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id        = Column(String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url        = Column(String(2048), nullable=False)
    r2_key            = Column(String(1024), nullable=False)
    r2_url            = Column(String(2048), nullable=False)
    thumbnail_r2_key  = Column(String(1024))
    thumbnail_r2_url  = Column(String(2048))
    position          = Column(Integer, default=0)
    downloaded_at     = Column(DateTime, default=datetime.utcnow)
    file_size_bytes   = Column(Integer)
    width             = Column(Integer)
    height            = Column(Integer)

    profile = relationship("Profile", back_populates="photos")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id                = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    started_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at       = Column(DateTime)
    status            = Column(SAEnum(ScrapeStatus), default=ScrapeStatus.running)
    profiles_found     = Column(Integer, default=0)
    profiles_processed = Column(Integer, default=0)
    profiles_new       = Column(Integer, default=0)
    profiles_updated   = Column(Integer, default=0)
    photos_downloaded  = Column(Integer, default=0)
    error_message      = Column(Text)


class Advertisement(Base):
    __tablename__ = "advertisements"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id   = Column(String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url   = Column(String(2048), unique=True, nullable=False)
    title        = Column(String(512))
    category     = Column(String(128))
    location     = Column(String(255))
    description  = Column(Text)
    published_at = Column(DateTime, nullable=True)
    first_seen   = Column(DateTime, default=datetime.utcnow)
    last_seen    = Column(DateTime, default=datetime.utcnow)
    is_active    = Column(Boolean, default=True)

    profile = relationship("Profile", back_populates="advertisements")


class ScraperSettings(Base):
    __tablename__ = "scraper_settings"

    id                      = Column(String(8), primary_key=True, default="settings")
    min_age                 = Column(Integer, nullable=True)
    max_age                 = Column(Integer, nullable=True)
    min_weight              = Column(Integer, nullable=True)
    max_weight              = Column(Integer, nullable=True)
    min_height              = Column(Integer, nullable=True)
    max_height              = Column(Integer, nullable=True)
    gender_filter           = Column(Text, nullable=True)  # comma-separated: "Vrouw,Man,Trans,Koppel"
    scrape_interval_minutes = Column(Integer, nullable=True)
