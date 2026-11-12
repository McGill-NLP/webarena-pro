from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String(120), nullable=False)
    is_host: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hometown: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    avatar_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    listings: Mapped[list["Listing"]] = relationship(back_populates="host")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="guest")
    wishlist_items: Mapped[list["WishlistItem"]] = relationship(back_populates="user")
    reviews: Mapped[list["Review"]] = relationship(back_populates="user")
    sent_messages: Mapped[list["Message"]] = relationship(back_populates="sender")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(120), nullable=False)
    price_per_night: Mapped[float] = mapped_column(Float, nullable=False)
    cleaning_fee: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    service_fee: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    bedrooms: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    beds: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    baths: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    max_guests: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    amenities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    house_rules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocked_ranges: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list, nullable=False)

    host: Mapped[User] = relationship(back_populates="listings")
    images: Mapped[list["ListingImage"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="ListingImage.display_order",
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="desc(Review.created_at)",
    )
    bookings: Mapped[list["Booking"]] = relationship(back_populates="listing")
    availability_entries: Mapped[list["Availability"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )
    wishlist_items: Mapped[list["WishlistItem"]] = relationship(back_populates="listing")
    threads: Mapped[list["MessageThread"]] = relationship(back_populates="listing")

    @property
    def primary_image(self) -> str:
        if self.images:
            return self.images[0].url
        return "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1200&q=80"


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    alt_text: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="images")


class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="availability_entries")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="reviews")
    user: Mapped[User] = relationship(back_populates="reviews")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    confirmation_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    guest_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="confirmed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="bookings")
    guest: Mapped[User] = relationship(back_populates="bookings")

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="wishlist_items")
    listing: Mapped[Listing] = relationship(back_populates="wishlist_items")


class MessageThread(Base):
    __tablename__ = "message_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    guest_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="threads")
    guest: Mapped[User] = relationship(foreign_keys=[guest_id])
    host: Mapped[User] = relationship(foreign_keys=[host_id])
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("message_threads.id"), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    thread: Mapped[MessageThread] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship(back_populates="sent_messages")


class TaskDefinition(Base):
    __tablename__ = "task_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), nullable=False)
    start_path: Mapped[str] = mapped_column(String(255), default="/", nullable=False)
    persona_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    validator_key: Mapped[str] = mapped_column(String(80), nullable=False)
    validation_target: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    persona: Mapped[User] = relationship()
