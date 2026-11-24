import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, UnprocessableError
from app.ml.profile import DeveloperProfile
from app.models import Profile


def _hash(p: DeveloperProfile) -> str:
    canonical = {
        "skills": sorted(x.lower() for x in p.skills),
        "learning_interests": sorted(x.lower() for x in p.learning_interests),
        "domains": sorted(x.lower() for x in p.domains),
        "preferred_languages": sorted(x.lower() for x in p.preferred_languages),
        "experience_level": p.experience_level,
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def create_or_get_profile(db: Session, p: DeveloperProfile) -> tuple[Profile, bool]:
    """Validate and persist. Identical content (case/order-insensitive) returns the existing row."""
    if p.is_empty:
        raise UnprocessableError(
            "Profile needs at least one skill, preferred language, domain or learning interest",
            [{"field": "body", "message": "profile is empty"}])
    h = _hash(p)
    existing = db.scalar(select(Profile).where(Profile.content_hash == h))
    if existing:
        return existing, False
    row = Profile(content_hash=h, **p.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # a concurrent request saved the same profile between our lookup and insert
        db.rollback()
        existing = db.scalar(select(Profile).where(Profile.content_hash == h))
        if existing is None:
            raise
        return existing, False
    return row, True


def get_profile(db: Session, profile_id: int) -> Profile:
    row = db.get(Profile, profile_id)
    if row is None:
        raise NotFoundError(f"Profile {profile_id} not found")
    return row


def to_ml_profile(row: Profile) -> DeveloperProfile:
    return DeveloperProfile(
        skills=row.skills, learning_interests=row.learning_interests, experience_level=row.experience_level,
        domains=row.domains, preferred_languages=row.preferred_languages)
