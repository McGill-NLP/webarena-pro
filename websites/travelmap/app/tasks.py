from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Availability, Booking, Message, MessageThread, TaskDefinition, WishlistItem
from app.seed import parse_date


def serialize_task(task: TaskDefinition, include_credentials: bool = True) -> dict[str, Any]:
    payload = {
        "id": task.id,
        "slug": task.slug,
        "title": task.title,
        "category": task.category,
        "difficulty": task.difficulty,
        "start_path": task.start_path,
        "intent": task.intent,
        "success_criteria": task.success_criteria,
        "validator_key": task.validator_key,
        "validation_target": task.validation_target,
        "persona": {
            "id": task.persona.id,
            "name": task.persona.name,
            "email": task.persona.email,
            "is_host": task.persona.is_host,
        },
    }
    if include_credentials:
        payload["persona"]["password"] = task.persona.password
    return payload


def _evaluate_booking_exists(db: Session, target: dict[str, Any]) -> dict[str, Any]:
    booking = db.scalar(
        select(Booking).where(
            Booking.listing_id == target["listing_id"],
            Booking.guest_id == target["guest_id"],
            Booking.check_in == parse_date(target["check_in"]),
            Booking.check_out == parse_date(target["check_out"]),
            Booking.status == "confirmed",
        )
    )
    return {
        "success": booking is not None,
        "evidence": booking.confirmation_code if booking else None,
    }


def _evaluate_wishlist_contains(db: Session, target: dict[str, Any]) -> dict[str, Any]:
    item = db.scalar(
        select(WishlistItem).where(
            WishlistItem.user_id == target["user_id"],
            WishlistItem.listing_id == target["listing_id"],
        )
    )
    return {"success": item is not None, "evidence": {"wishlist_item_id": item.id} if item else None}


def _evaluate_message_contains(db: Session, target: dict[str, Any]) -> dict[str, Any]:
    needle = target["body_contains"].lower()
    message = db.scalar(
        select(Message)
        .join(MessageThread, Message.thread_id == MessageThread.id)
        .where(
            MessageThread.listing_id == target["listing_id"],
            MessageThread.guest_id == target["guest_id"],
            Message.body.ilike(f"%{needle}%"),
        )
        .order_by(Message.created_at.desc())
    )
    return {"success": message is not None, "evidence": {"message_id": message.id} if message else None}


def _evaluate_blocked_range(db: Session, target: dict[str, Any]) -> dict[str, Any]:
    start_date = parse_date(target["start"])
    end_date = parse_date(target["end"])
    entries = db.scalars(
        select(Availability).where(
            Availability.listing_id == target["listing_id"],
            Availability.date >= start_date,
            Availability.date < end_date,
        )
    ).all()
    success = bool(entries) and all(not entry.is_available for entry in entries)
    return {
        "success": success,
        "evidence": {
            "checked_dates": [entry.date.isoformat() for entry in entries],
            "blocked": [not entry.is_available for entry in entries],
        },
    }


def _evaluate_booking_canceled(db: Session, target: dict[str, Any]) -> dict[str, Any]:
    booking = db.scalar(
        select(Booking).where(
            Booking.confirmation_code == target["confirmation_code"],
            Booking.guest_id == target["guest_id"],
        )
    )
    return {
        "success": booking is not None and booking.status == "canceled",
        "evidence": {"status": booking.status} if booking else None,
    }


EVALUATORS = {
    "booking_exists": _evaluate_booking_exists,
    "wishlist_contains": _evaluate_wishlist_contains,
    "message_contains": _evaluate_message_contains,
    "blocked_range": _evaluate_blocked_range,
    "booking_canceled": _evaluate_booking_canceled,
}


def evaluate_task(db: Session, task: TaskDefinition) -> dict[str, Any]:
    evaluator = EVALUATORS[task.validator_key]
    outcome = evaluator(db, task.validation_target)
    return {
        "task_id": task.id,
        "slug": task.slug,
        "title": task.title,
        "success": outcome["success"],
        "evidence": outcome.get("evidence"),
    }
