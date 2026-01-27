"""Business logic for meal management."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.meal import Meal
from app.models.meal_ingredient import MealIngredient, IngredientState
from app.models.ingredient import Ingredient


class MealService:
    """Service for meal-related operations."""

    @staticmethod
    def create_meal(
        db: Session,
        user_id: UUID,
        image_path: Optional[str] = None,
        user_notes: Optional[str] = None,
        country: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Meal:
        """
        Create a new meal entry.

        Args:
            db: Database session
            user_id: User ID
            image_path: Path to uploaded meal image
            user_notes: User's notes about the meal
            country: Country where meal was consumed
            timestamp: Meal timestamp (defaults to now)

        Returns:
            Created Meal object
        """
        meal = Meal(
            user_id=user_id,
            image_path=image_path,
            user_notes=user_notes,
            country=country,
            timestamp=timestamp or datetime.utcnow()
        )
        db.add(meal)
        db.commit()
        db.refresh(meal)
        return meal

    @staticmethod
    def add_ingredient_to_meal(
        db: Session,
        meal_id: int,
        ingredient_name: str,
        state: IngredientState,
        quantity_description: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> MealIngredient:
        """
        Add an ingredient to a meal, creating the ingredient if it doesn't exist.

        Args:
            db: Database session
            meal_id: Meal ID
            ingredient_name: Name of ingredient
            state: Ingredient state (raw, cooked, processed)
            quantity_description: Free-text quantity description
            confidence: AI confidence score (if applicable)

        Returns:
            Created MealIngredient object
        """
        # Normalize ingredient name
        normalized_name = Ingredient.normalize_name(ingredient_name)

        # Find or create ingredient
        ingredient = db.query(Ingredient).filter(
            Ingredient.normalized_name == normalized_name
        ).first()

        if not ingredient:
            ingredient = Ingredient(
                name=ingredient_name,
                normalized_name=normalized_name
            )
            db.add(ingredient)
            db.flush()

        # Create meal-ingredient link
        meal_ingredient = MealIngredient(
            meal_id=meal_id,
            ingredient_id=ingredient.id,
            state=state,
            quantity_description=quantity_description,
            confidence=confidence
        )
        db.add(meal_ingredient)
        db.commit()
        db.refresh(meal_ingredient)
        return meal_ingredient

    @staticmethod
    def remove_ingredient_from_meal(
        db: Session,
        meal_ingredient_id: int
    ) -> bool:
        """
        Remove an ingredient from a meal.

        Args:
            db: Database session
            meal_ingredient_id: MealIngredient ID

        Returns:
            True if deleted, False if not found
        """
        meal_ingredient = db.query(MealIngredient).filter(
            MealIngredient.id == meal_ingredient_id
        ).first()

        if meal_ingredient:
            db.delete(meal_ingredient)
            db.commit()
            return True
        return False

    @staticmethod
    def get_meal(db: Session, meal_id: int) -> Optional[Meal]:
        """Get a meal by ID with all relationships loaded."""
        return db.query(Meal).filter(Meal.id == meal_id).first()

    @staticmethod
    def get_user_meals(
        db: Session,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Meal]:
        """Get all meals for a user, ordered by timestamp descending."""
        return db.query(Meal).filter(
            Meal.user_id == user_id
        ).order_by(
            Meal.timestamp.desc()
        ).limit(limit).offset(offset).all()

    @staticmethod
    def update_meal(
        db: Session,
        meal_id: int,
        user_notes: Optional[str] = None,
        country: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Optional[Meal]:
        """
        Update meal details.

        Args:
            db: Database session
            meal_id: Meal ID
            user_notes: Updated notes
            country: Updated country
            timestamp: Updated timestamp

        Returns:
            Updated Meal object or None if not found
        """
        meal = db.query(Meal).filter(Meal.id == meal_id).first()
        if not meal:
            return None

        if user_notes is not None:
            meal.user_notes = user_notes
        if country is not None:
            meal.country = country
        if timestamp is not None:
            meal.timestamp = timestamp

        db.commit()
        db.refresh(meal)
        return meal

    @staticmethod
    def delete_meal(db: Session, meal_id: int) -> bool:
        """
        Delete a meal and all associated ingredients.

        Args:
            db: Database session
            meal_id: Meal ID

        Returns:
            True if deleted, False if not found
        """
        meal = db.query(Meal).filter(Meal.id == meal_id).first()
        if meal:
            db.delete(meal)
            db.commit()
            return True
        return False


# Singleton instance
meal_service = MealService()
