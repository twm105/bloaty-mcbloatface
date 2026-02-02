#!/usr/bin/env python3
"""Create realistic test data for diagnosis feature testing."""
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models import Meal, Symptom, Ingredient, MealIngredient
from app.models.meal_ingredient import IngredientState
import uuid

# MVP single-user ID
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

def create_test_data():
    """Create test data for diagnosis feature."""
    db = SessionLocal()

    try:
        # Get or create ingredients
        onion = db.query(Ingredient).filter_by(normalized_name='onion').first()
        if not onion:
            onion = Ingredient(name='Onion', normalized_name='onion')
            db.add(onion)
            db.flush()

        milk = db.query(Ingredient).filter_by(normalized_name='milk').first()
        if not milk:
            milk = Ingredient(name='Milk', normalized_name='milk')
            db.add(milk)
            db.flush()

        chicken = db.query(Ingredient).filter_by(normalized_name='chicken').first()
        if not chicken:
            chicken = Ingredient(name='Chicken', normalized_name='chicken')
            db.add(chicken)
            db.flush()

        print(f"Ingredients: onion={onion.id}, milk={milk.id}, chicken={chicken.id}")

        # SCENARIO 1: Onion intolerance (immediate reactions 0.5-1.5 hours)
        # 5 meals with raw onion, each followed by bloating

        onion_meals = [
            {
                "timestamp": datetime(2026, 2, 3, 10, 0, 0, tzinfo=timezone.utc),
                "name": "Onion omelette",
                "symptom_time": datetime(2026, 2, 3, 11, 0, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "bloating", "severity": 7}],
            },
            {
                "timestamp": datetime(2026, 2, 3, 18, 0, 0, tzinfo=timezone.utc),
                "name": "Salad with raw onion",
                "symptom_time": datetime(2026, 2, 3, 18, 45, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "bloating", "severity": 6}, {"name": "cramping", "severity": 5}],
            },
            {
                "timestamp": datetime(2026, 2, 4, 12, 0, 0, tzinfo=timezone.utc),
                "name": "Sandwich with raw onion",
                "symptom_time": datetime(2026, 2, 4, 13, 30, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "bloating", "severity": 8}],
            },
            {
                "timestamp": datetime(2026, 2, 5, 7, 0, 0, tzinfo=timezone.utc),
                "name": "Veggie omelette with onion",
                "symptom_time": datetime(2026, 2, 5, 8, 0, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "bloating", "severity": 7}, {"name": "gas", "severity": 6}],
            },
            {
                "timestamp": datetime(2026, 2, 5, 13, 0, 0, tzinfo=timezone.utc),
                "name": "Burrito with raw onion",
                "symptom_time": datetime(2026, 2, 5, 13, 50, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "bloating", "severity": 9}, {"name": "cramping", "severity": 7}],
            },
        ]

        for meal_data in onion_meals:
            meal = Meal(
                user_id=MVP_USER_ID,
                timestamp=meal_data["timestamp"],
                name=meal_data["name"],
                status="published",
            )
            db.add(meal)
            db.flush()

            meal_ing = MealIngredient(
                meal_id=meal.id,
                ingredient_id=onion.id,
                state=IngredientState.RAW,
            )
            db.add(meal_ing)

            symptom = Symptom(
                user_id=MVP_USER_ID,
                start_time=meal_data["symptom_time"],
                raw_description="Bloating",
                tags=meal_data["symptom_tags"],
            )
            db.add(symptom)

            print(f"Created onion meal {meal.id} at {meal.timestamp} with symptom at {symptom.start_time}")

        # SCENARIO 2: Milk intolerance (delayed reactions 6-14 hours)
        # 5 meals with processed milk, each followed by gas/cramping

        milk_meals = [
            {
                "timestamp": datetime(2026, 2, 3, 8, 0, 0, tzinfo=timezone.utc),
                "name": "Coffee with milk",
                "symptom_time": datetime(2026, 2, 3, 16, 0, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "gas", "severity": 6}, {"name": "cramping", "severity": 5}],
            },
            {
                "timestamp": datetime(2026, 2, 4, 9, 0, 0, tzinfo=timezone.utc),
                "name": "Cereal with milk",
                "symptom_time": datetime(2026, 2, 4, 19, 0, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "gas", "severity": 7}, {"name": "bloating", "severity": 6}],
            },
            {
                "timestamp": datetime(2026, 2, 5, 7, 30, 0, tzinfo=timezone.utc),
                "name": "Latte",
                "symptom_time": datetime(2026, 2, 5, 19, 30, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "gas", "severity": 8}, {"name": "cramping", "severity": 7}, {"name": "diarrhea", "severity": 6}],
            },
            {
                "timestamp": datetime(2026, 2, 6, 8, 0, 0, tzinfo=timezone.utc),
                "name": "Yogurt parfait with milk",
                "symptom_time": datetime(2026, 2, 6, 14, 0, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "bloating", "severity": 7}, {"name": "cramping", "severity": 6}],
            },
            {
                "timestamp": datetime(2026, 2, 6, 10, 0, 0, tzinfo=timezone.utc),
                "name": "Cappuccino",
                "symptom_time": datetime(2026, 2, 7, 0, 0, 0, tzinfo=timezone.utc),
                "symptom_tags": [{"name": "gas", "severity": 8}, {"name": "bloating", "severity": 7}],
            },
        ]

        for meal_data in milk_meals:
            meal = Meal(
                user_id=MVP_USER_ID,
                timestamp=meal_data["timestamp"],
                name=meal_data["name"],
                status="published",
            )
            db.add(meal)
            db.flush()

            meal_ing = MealIngredient(
                meal_id=meal.id,
                ingredient_id=milk.id,
                state=IngredientState.PROCESSED,
            )
            db.add(meal_ing)

            symptom = Symptom(
                user_id=MVP_USER_ID,
                start_time=meal_data["symptom_time"],
                raw_description="Bloating",
                tags=meal_data["symptom_tags"],
            )
            db.add(symptom)

            print(f"Created milk meal {meal.id} at {meal.timestamp} with symptom at {symptom.start_time}")

        # SCENARIO 3: Chicken (CONTROL - no symptoms)
        # 3 meals with cooked chicken, no symptoms follow

        chicken_meals = [
            {
                "timestamp": datetime(2026, 2, 3, 12, 30, 0, tzinfo=timezone.utc),
                "name": "Grilled chicken salad",
            },
            {
                "timestamp": datetime(2026, 2, 4, 18, 30, 0, tzinfo=timezone.utc),
                "name": "Chicken breast with veggies",
            },
            {
                "timestamp": datetime(2026, 2, 5, 19, 0, 0, tzinfo=timezone.utc),
                "name": "Chicken stir fry",
            },
        ]

        for meal_data in chicken_meals:
            meal = Meal(
                user_id=MVP_USER_ID,
                timestamp=meal_data["timestamp"],
                name=meal_data["name"],
                status="published",
            )
            db.add(meal)
            db.flush()

            meal_ing = MealIngredient(
                meal_id=meal.id,
                ingredient_id=chicken.id,
                state=IngredientState.COOKED,
            )
            db.add(meal_ing)

            print(f"Created chicken meal {meal.id} at {meal.timestamp} (control - no symptom)")

        db.commit()
        print("\n✅ Test data created successfully!")
        print("\nExpected correlations:")
        print("  - ONION (RAW): HIGH confidence - 5 meals, 5-10 immediate symptoms (0.5-1.5 hours)")
        print("  - MILK (PROCESSED): MEDIUM-HIGH confidence - 5 meals, 5-10 delayed symptoms (6-14 hours)")
        print("  - CHICKEN (COOKED): LOW/NONE - 3 meals, 0 symptoms")

    except Exception as e:
        print(f"Error creating test data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_test_data()
