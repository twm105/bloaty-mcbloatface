#!/usr/bin/env python
"""
Populate dev database with test data for meal history and diagnosis features.

Run with: docker compose exec web python scripts/populate_dev_data.py
"""

import asyncio
import bcrypt
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.meal import Meal
from app.models.symptom import Symptom
from app.models.meal_ingredient import IngredientState
from app.services.meal_service import MealService
from app.services.ai_service import ClaudeService


# Image paths (relative to project root)
MEAL_IMAGES = [
    "uploads/meals/20260214_234755_18c78004.jpeg",
    "uploads/meals/20260214_234908_a703467d.jpeg",
    "uploads/meals/20260214_235025_52ece33b.jpeg",
    "uploads/meals/20260214_235113_9030c508.jpeg",
    "uploads/meals/20260214_235159_66edf5bb.jpeg",
    "uploads/meals/20260214_235239_28932aea.jpeg",
    "uploads/meals/20260214_235330_315eddc4.jpeg",
    "uploads/meals/20260214_235517_88fcc4a9.jpeg",
    "uploads/meals/20260214_232648_7da0f458.jpeg",
    "uploads/meals/20260214_135226_385c22e5.jpeg",
]

# Timezone
TZ = ZoneInfo("America/New_York")


def create_admin_user(db: Session) -> User:
    """Create admin user if not exists."""
    existing = db.query(User).filter(User.email == "tmaisey@gmail.com").first()
    if existing:
        print(f"Admin user already exists: {existing.id}")
        return existing

    password_hash = bcrypt.hashpw(
        "bloaty-admin".encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(
        email="tmaisey@gmail.com",
        password_hash=password_hash,
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Created admin user: {user.id}")
    return user


async def create_meal_with_ai_analysis(
    db: Session,
    user_id,
    image_path: str,
    timestamp: datetime,
    claude_service: ClaudeService,
) -> Meal:
    """Create a meal and run AI analysis to get ingredients."""
    # Create meal record
    meal = MealService.create_meal(
        db=db,
        user_id=user_id,
        image_path=image_path,
        timestamp=timestamp,
        local_timezone="America/New_York",
    )
    print(f"Created meal {meal.id} from {image_path}")

    # Run AI analysis
    try:
        analysis = await claude_service.analyze_meal_image(image_path)
        meal_name = analysis.get("meal_name", "Unknown Meal")
        ingredients = analysis.get("ingredients", [])

        # Update meal name
        meal.name = meal_name
        meal.name_source = "ai"
        meal.ai_raw_response = analysis.get("raw_response")
        meal.ai_suggested_ingredients = ingredients
        db.commit()

        print(f"  Meal name: {meal_name}")
        print(f"  Found {len(ingredients)} ingredients")

        # Add ingredients to meal
        for ing in ingredients:
            state_str = ing.get("state", "cooked").lower()
            if state_str == "raw":
                state = IngredientState.RAW
            elif state_str == "processed":
                state = IngredientState.PROCESSED
            else:
                state = IngredientState.COOKED

            MealService.add_ingredient_to_meal(
                db=db,
                meal_id=meal.id,
                ingredient_name=ing.get("name", "unknown"),
                state=state,
                quantity_description=ing.get("quantity"),
                confidence=ing.get("confidence"),
                source="ai",
            )

        # Publish meal
        MealService.publish_meal(db, meal.id)
        print(f"  Published meal {meal.id}")

    except Exception as e:
        print(f"  AI analysis failed: {e}")
        # Still publish the meal without AI analysis
        meal.name = "Unknown Meal"
        MealService.publish_meal(db, meal.id)

    return meal


def create_symptom(
    db: Session,
    user_id,
    timestamp: datetime,
    tags: list,
    raw_description: str,
    severity: int,
    structured_type: str,
) -> Symptom:
    """Create a symptom record."""
    symptom = Symptom(
        user_id=user_id,
        timestamp=timestamp,
        start_time=timestamp,  # Required for diagnosis queries
        raw_description=raw_description,
        tags=tags,
        severity=severity,
        structured_type=structured_type,
    )
    db.add(symptom)
    db.commit()
    db.refresh(symptom)
    print(f"Created symptom: {structured_type} (severity {severity}) at {timestamp}")
    return symptom


async def main():
    """Main function to populate the database."""
    db = SessionLocal()
    claude_service = ClaudeService()

    try:
        # Phase 1: Create admin user
        print("\n=== Phase 1: Creating admin user ===")
        user = create_admin_user(db)

        # Phase 2: Create meals with AI analysis
        print("\n=== Phase 2: Creating meals with AI analysis ===")

        # Define meal schedule over 3 days
        # Day 1: Feb 12, 2026
        # Day 2: Feb 13, 2026
        # Day 3: Feb 14, 2026

        meal_schedule = [
            # Day 1 - Feb 12
            (MEAL_IMAGES[0], datetime(2026, 2, 12, 12, 0, tzinfo=TZ)),  # Lunch
            (MEAL_IMAGES[1], datetime(2026, 2, 12, 12, 30, tzinfo=TZ)),  # Lunch dessert
            (MEAL_IMAGES[2], datetime(2026, 2, 12, 19, 0, tzinfo=TZ)),  # Dinner
            (MEAL_IMAGES[3], datetime(2026, 2, 12, 20, 0, tzinfo=TZ)),  # Dinner dessert
            # Day 2 - Feb 13
            (MEAL_IMAGES[4], datetime(2026, 2, 13, 12, 0, tzinfo=TZ)),  # Lunch
            (MEAL_IMAGES[5], datetime(2026, 2, 13, 12, 30, tzinfo=TZ)),  # Lunch dessert
            (MEAL_IMAGES[6], datetime(2026, 2, 13, 19, 0, tzinfo=TZ)),  # Dinner
            (MEAL_IMAGES[7], datetime(2026, 2, 13, 20, 0, tzinfo=TZ)),  # Dinner dessert
            # Day 3 - Feb 14
            (MEAL_IMAGES[8], datetime(2026, 2, 14, 12, 0, tzinfo=TZ)),  # Lunch
            (MEAL_IMAGES[9], datetime(2026, 2, 14, 19, 0, tzinfo=TZ)),  # Dinner
        ]

        meals = []
        for image_path, timestamp in meal_schedule:
            meal = await create_meal_with_ai_analysis(
                db, user.id, image_path, timestamp, claude_service
            )
            meals.append(meal)

        # Phase 3: Add correlating symptoms
        # Target dairy (cheese, cream, butter) → bloating pattern
        # Add symptoms 2-4 hours after meals containing trigger ingredients
        print("\n=== Phase 3: Adding correlating symptoms ===")

        # Symptoms after Day 1 lunch (if dairy was detected)
        create_symptom(
            db=db,
            user_id=user.id,
            timestamp=datetime(2026, 2, 12, 14, 30, tzinfo=TZ),  # 2.5 hours after lunch
            tags=[{"name": "bloating", "severity": 6}],
            raw_description="Feeling bloated after lunch",
            severity=6,
            structured_type="bloating",
        )

        # Symptoms after Day 1 dinner
        create_symptom(
            db=db,
            user_id=user.id,
            timestamp=datetime(2026, 2, 12, 22, 0, tzinfo=TZ),  # 3 hours after dinner
            tags=[{"name": "stomach pain", "severity": 5}],
            raw_description="Stomach discomfort after dinner",
            severity=5,
            structured_type="stomach pain",
        )

        # Symptoms after Day 2 lunch
        create_symptom(
            db=db,
            user_id=user.id,
            timestamp=datetime(2026, 2, 13, 15, 0, tzinfo=TZ),  # 3 hours after lunch
            tags=[{"name": "bloating", "severity": 7}],
            raw_description="Significant bloating after lunch",
            severity=7,
            structured_type="bloating",
        )

        # Symptoms after Day 2 dinner
        create_symptom(
            db=db,
            user_id=user.id,
            timestamp=datetime(2026, 2, 13, 21, 30, tzinfo=TZ),
            tags=[{"name": "bloating", "severity": 5}, {"name": "gas", "severity": 4}],
            raw_description="Bloating and gas after dinner",
            severity=5,
            structured_type="bloating",
        )

        # Symptoms after Day 3 lunch
        create_symptom(
            db=db,
            user_id=user.id,
            timestamp=datetime(2026, 2, 14, 14, 0, tzinfo=TZ),
            tags=[{"name": "bloating", "severity": 6}],
            raw_description="Bloating after Valentine's lunch",
            severity=6,
            structured_type="bloating",
        )

        # Delayed symptom (next day)
        create_symptom(
            db=db,
            user_id=user.id,
            timestamp=datetime(2026, 2, 15, 8, 0, tzinfo=TZ),  # Next morning
            tags=[{"name": "fatigue", "severity": 4}],
            raw_description="Feeling sluggish this morning",
            severity=4,
            structured_type="fatigue",
        )

        print("\n=== Done! ===")
        print(f"Created {len(meals)} meals and 6 symptoms")
        print("Login at http://localhost:8000 with:")
        print("  Email: tmaisey@gmail.com")
        print("  Password: bloaty-admin")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
