"""Announcement endpoints for the High School Management System API."""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Payload used for announcement create and update operations."""

    message: str
    expiration_date: str
    start_date: Optional[str] = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message is required")
        if len(value) > 280:
            raise ValueError("Message must be 280 characters or less")
        return value

    @field_validator("expiration_date")
    @classmethod
    def validate_expiration_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Expiration date must use YYYY-MM-DD format") from exc
        return value

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Start date must use YYYY-MM-DD format") from exc
        return value


class AnnouncementResponse(BaseModel):
    id: str
    message: str
    start_date: Optional[str]
    expiration_date: str


def _assert_teacher_session(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": announcement["_id"],
        "message": announcement["message"],
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement["expiration_date"]
    }


def _validate_date_order(payload: AnnouncementPayload) -> None:
    if not payload.start_date:
        return

    start = date.fromisoformat(payload.start_date)
    expiration = date.fromisoformat(payload.expiration_date)
    if start > expiration:
        raise HTTPException(
            status_code=400,
            detail="Start date cannot be after expiration date"
        )


@router.get("", response_model=List[AnnouncementResponse])
@router.get("/", response_model=List[AnnouncementResponse])
def get_active_announcements() -> List[AnnouncementResponse]:
    """Return announcements active today for public display in the banner."""
    today = date.today().isoformat()

    query = {
        "$and": [
            {"expiration_date": {"$gte": today}},
            {
                "$or": [
                    {"start_date": None},
                    {"start_date": {"$exists": False}},
                    {"start_date": {"$lte": today}}
                ]
            }
        ]
    }

    announcements = announcements_collection.find(query).sort([
        ("expiration_date", 1),
        ("_id", 1)
    ])

    return [_serialize_announcement(item) for item in announcements]


@router.get("/manage", response_model=List[AnnouncementResponse])
def list_announcements_for_management(
    teacher_username: Optional[str] = Query(None)
) -> List[AnnouncementResponse]:
    """Return all announcements for authenticated management UI."""
    _assert_teacher_session(teacher_username)

    announcements = announcements_collection.find({}).sort([
        ("expiration_date", 1),
        ("_id", 1)
    ])
    return [_serialize_announcement(item) for item in announcements]


@router.post("", response_model=AnnouncementResponse)
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Create a new announcement with required expiration and optional start date."""
    _assert_teacher_session(teacher_username)
    _validate_date_order(payload)

    announcement_id = uuid4().hex[:12]
    record = {
        "_id": announcement_id,
        "message": payload.message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date
    }

    announcements_collection.insert_one(record)
    return _serialize_announcement(record)


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Update an existing announcement."""
    _assert_teacher_session(teacher_username)
    _validate_date_order(payload)

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": payload.message,
                "start_date": payload.start_date,
                "expiration_date": payload.expiration_date
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement."""
    _assert_teacher_session(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
