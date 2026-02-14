"""Business logic for meal management."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
            timestamp=timestamp or datetime.utcnow(),
            status='draft'  # New meals start as drafts
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
        confidence: Optional[float] = None,
        source: str = 'user-add'
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

        # Find or create ingredient (handle race condition)
        ingredient = db.query(Ingredient).filter(
            Ingredient.normalized_name == normalized_name
        ).first()

        if not ingredient:
            try:
                ingredient = Ingredient(
                    name=ingredient_name,
                    normalized_name=normalized_name
                )
                db.add(ingredient)
                db.flush()
            except IntegrityError:
                # Race condition: another request created it, rollback and fetch
                db.rollback()
                ingredient = db.query(Ingredient).filter(
                    Ingredient.normalized_name == normalized_name
                ).first()

        # Create meal-ingredient link
        meal_ingredient = MealIngredient(
            meal_id=meal_id,
            ingredient_id=ingredient.id,
            state=state,
            quantity_description=quantity_description,
            confidence=confidence,
            source=source
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
        """Get all published meals for a user, ordered by timestamp descending."""
        return db.query(Meal).filter(
            Meal.user_id == user_id,
            Meal.status == 'published'  # Only show published meals in history
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
    def update_meal_ai_response(
        db: Session,
        meal_id: int,
        ai_response: str
    ) -> Optional[Meal]:
        """
        Update the AI raw response for a meal (for debugging/auditing).

        Args:
            db: Database session
            meal_id: Meal ID
            ai_response: Raw AI response JSON

        Returns:
            Updated Meal object or None if not found
        """
        meal = db.query(Meal).filter(Meal.id == meal_id).first()
        if not meal:
            return None

        meal.ai_raw_response = ai_response
        db.commit()
        db.refresh(meal)
        return meal

    @staticmethod
    def update_meal_name(
        db: Session,
        meal_id: int,
        name: str
    ) -> Optional[Meal]:
        """
        Update the meal name.

        Args:
            db: Database session
            meal_id: Meal ID
            name: New meal name

        Returns:
            Updated Meal object or None if not found
        """
        meal = db.query(Meal).filter(Meal.id == meal_id).first()
        if not meal:
            return None

        # Track source change: if AI-suggested name was edited, mark as user-edit
        if meal.name != name and meal.name_source == 'ai':
            meal.name_source = 'user-edit'

        meal.name = name
        db.commit()
        db.refresh(meal)
        return meal

    @staticmethod
    def update_ingredient_in_meal(
        db: Session,
        meal_ingredient_id: int,
        ingredient_name: Optional[str] = None,
        quantity_description: Optional[str] = None
    ) -> Optional[MealIngredient]:
        """
        Update an ingredient's name or quantity.

        Args:
            db: Database session
            meal_ingredient_id: MealIngredient ID
            ingredient_name: New ingredient name (if changing)
            quantity_description: New quantity description

        Returns:
            Updated MealIngredient or None if not found
        """
        meal_ingredient = db.query(MealIngredient).filter(
            MealIngredient.id == meal_ingredient_id
        ).first()

        if not meal_ingredient:
            return None

        modified = False

        # Update ingredient if name changed
        if ingredient_name and ingredient_name != meal_ingredient.ingredient.name:
            normalized_name = Ingredient.normalize_name(ingredient_name)

            # Find or create new ingredient (handle race condition)
            ingredient = db.query(Ingredient).filter(
                Ingredient.normalized_name == normalized_name
            ).first()

            if not ingredient:
                try:
                    ingredient = Ingredient(
                        name=ingredient_name,
                        normalized_name=normalized_name
                    )
                    db.add(ingredient)
                    db.flush()
                except IntegrityError:
                    # Race condition: another request created it, rollback and fetch
                    db.rollback()
                    ingredient = db.query(Ingredient).filter(
                        Ingredient.normalized_name == normalized_name
                    ).first()
                    # Re-fetch meal_ingredient since we rolled back
                    meal_ingredient = db.query(MealIngredient).filter(
                        MealIngredient.id == meal_ingredient_id
                    ).first()

            meal_ingredient.ingredient_id = ingredient.id
            modified = True

        # Update quantity if provided and different
        if quantity_description is not None:
            if meal_ingredient.quantity_description != quantity_description:
                meal_ingredient.quantity_description = quantity_description
                modified = True

        # Track source change: if AI-suggested ingredient was edited, mark as user-edit
        if modified and meal_ingredient.source == 'ai':
            meal_ingredient.source = 'user-edit'

        db.commit()
        db.refresh(meal_ingredient)
        return meal_ingredient

    @staticmethod
    def update_ingredient_state(
        db: Session,
        meal_ingredient_id: int,
        state: IngredientState
    ) -> Optional[MealIngredient]:
        """
        Update an ingredient's state (raw/cooked/processed).

        Args:
            db: Database session
            meal_ingredient_id: MealIngredient ID
            state: New ingredient state

        Returns:
            Updated MealIngredient or None if not found
        """
        meal_ingredient = db.query(MealIngredient).filter(
            MealIngredient.id == meal_ingredient_id
        ).first()

        if not meal_ingredient:
            return None

        # Track source change: if AI-suggested state was changed, mark as user-edit
        if meal_ingredient.state != state and meal_ingredient.source == 'ai':
            meal_ingredient.source = 'user-edit'

        meal_ingredient.state = state
        db.commit()
        db.refresh(meal_ingredient)
        return meal_ingredient

    @staticmethod
    def publish_meal(db: Session, meal_id: int) -> Optional[Meal]:
        """
        Publish a meal (change status from draft to published).

        Args:
            db: Database session
            meal_id: Meal ID

        Returns:
            Published Meal object or None if not found
        """
        meal = db.query(Meal).filter(Meal.id == meal_id).first()
        if not meal:
            return None

        meal.status = 'published'
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
