"""API endpoints for meal logging and management."""
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.meal_ingredient import IngredientState
from app.services.meal_service import meal_service
from app.services.file_service import file_service

router = APIRouter(prefix="/meals", tags=["meals"])
templates = Jinja2Templates(directory="app/templates")

# MVP single-user ID
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.get("/log", response_class=HTMLResponse)
async def meal_log_page(request: Request):
    """Meal logging page."""
    return templates.TemplateResponse("meals/log.html", {"request": request})


@router.post("/create")
async def create_meal(
    request: Request,
    image: Optional[UploadFile] = File(None),
    user_notes: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    meal_timestamp: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Create a new meal entry with optional image.

    Returns: Redirect to ingredient editing page
    """
    # Handle image upload
    image_path = None
    if image and image.filename:
        try:
            image_path = await file_service.save_meal_image(image)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Parse timestamp
    timestamp = None
    if meal_timestamp:
        try:
            timestamp = datetime.fromisoformat(meal_timestamp)
        except ValueError:
            timestamp = datetime.utcnow()
    else:
        timestamp = datetime.utcnow()

    # Create meal
    meal = meal_service.create_meal(
        db=db,
        user_id=MVP_USER_ID,
        image_path=image_path,
        user_notes=user_notes,
        country=country,
        timestamp=timestamp
    )

    # Redirect to ingredient editing
    return RedirectResponse(
        url=f"/meals/{meal.id}/edit-ingredients",
        status_code=303
    )


@router.get("/{meal_id}/edit-ingredients", response_class=HTMLResponse)
async def edit_ingredients_page(
    request: Request,
    meal_id: int,
    db: Session = Depends(get_db)
):
    """Page for adding/editing meal ingredients."""
    meal = meal_service.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    return templates.TemplateResponse(
        "meals/edit_ingredients.html",
        {
            "request": request,
            "meal": meal,
            "ingredient_states": [state.value for state in IngredientState]
        }
    )


@router.post("/{meal_id}/ingredients/add")
async def add_ingredient(
    meal_id: int,
    ingredient_name: str = Form(...),
    state: str = Form(...),
    quantity: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Add an ingredient to a meal."""
    # Validate meal exists
    meal = meal_service.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Validate state
    try:
        ingredient_state = IngredientState(state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state: {state}")

    # Add ingredient
    meal_ingredient = meal_service.add_ingredient_to_meal(
        db=db,
        meal_id=meal_id,
        ingredient_name=ingredient_name,
        state=ingredient_state,
        quantity_description=quantity
    )

    # Return HTML partial for htmx
    return templates.TemplateResponse(
        "meals/partials/ingredient_item.html",
        {
            "request": {},
            "meal_ingredient": meal_ingredient
        }
    )


@router.delete("/{meal_id}/ingredients/{meal_ingredient_id}")
async def remove_ingredient(
    meal_id: int,
    meal_ingredient_id: int,
    db: Session = Depends(get_db)
):
    """Remove an ingredient from a meal."""
    success = meal_service.remove_ingredient_from_meal(db, meal_ingredient_id)
    if not success:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    return {"status": "deleted"}


@router.post("/{meal_id}/complete")
async def complete_meal(
    meal_id: int,
    db: Session = Depends(get_db)
):
    """Mark meal as complete and redirect to history."""
    meal = meal_service.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    return RedirectResponse(url="/meals/history", status_code=303)


@router.get("/history", response_class=HTMLResponse)
async def meal_history_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """Meal history page."""
    meals = meal_service.get_user_meals(db, MVP_USER_ID, limit=50)

    return templates.TemplateResponse(
        "meals/history.html",
        {
            "request": request,
            "meals": meals
        }
    )


@router.delete("/{meal_id}")
async def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db)
):
    """Delete a meal."""
    # Get meal to delete image file
    meal = meal_service.get_meal(db, meal_id)
    if meal and meal.image_path:
        file_service.delete_file(meal.image_path)

    success = meal_service.delete_meal(db, meal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Meal not found")

    return {"status": "deleted"}
