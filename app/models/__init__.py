"""
Database models for Bloaty McBloatface.

Import all models here so Alembic can detect them for migrations.
"""

from app.database import Base
from app.models.user import User
from app.models.ingredient import Ingredient
from app.models.ingredient_category import IngredientCategory
from app.models.ingredient_category_relation import IngredientCategoryRelation
from app.models.meal import Meal
from app.models.meal_ingredient import MealIngredient, IngredientState
from app.models.symptom import Symptom
from app.models.user_settings import UserSettings
from app.models.data_export import DataExport
from app.models.eval_run import EvalRun

__all__ = [
    "Base",
    "User",
    "Ingredient",
    "IngredientCategory",
    "IngredientCategoryRelation",
    "Meal",
    "MealIngredient",
    "IngredientState",
    "Symptom",
    "UserSettings",
    "DataExport",
    "EvalRun",
]
