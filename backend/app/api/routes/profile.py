from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.profile import ProfileCreate, ProfileOut
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("", response_model=ProfileOut, status_code=201)
def save_profile(body: ProfileCreate, response: Response, db: Session = Depends(get_db)):
    """Validate and store a developer profile. 201 when created; 200 with the existing profile when an
    identical one (ignoring case and order) was already saved."""
    row, created = profile_service.create_or_get_profile(db, body)
    if not created:
        response.status_code = 200
    return row
