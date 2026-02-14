"""Seed stub user for MVP single-user mode."""

import uuid
from app.database import SessionLocal
from app.models.user import User
from app.models.user_settings import UserSettings


# Hardcoded UUID for MVP single-user
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def seed_user():
    """Seed the database with a stub user for MVP."""
    db = SessionLocal()

    try:
        # Check if user already exists
        existing = db.query(User).filter(User.id == MVP_USER_ID).first()
        if existing:
            print("MVP user already exists. Skipping.")
            return

        # Create stub user
        user = User(
            id=MVP_USER_ID,
            email=None,  # No email in MVP
        )
        db.add(user)

        # Create default settings
        settings = UserSettings(
            user_id=MVP_USER_ID,
            disclaimer_acknowledged=False,
            data_processing_consent=False,
            privacy_policy_version="1.0",
        )
        db.add(settings)

        db.commit()
        print(f"Successfully created MVP user with ID: {MVP_USER_ID}")

    except Exception as e:
        print(f"Error seeding user: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_user()
