"""API endpoints for meal logging and management."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.meal_ingredient import IngredientState
from app.models.user_feedback import UserFeedback
from app.services.meal_service import meal_service
from app.services.file_service import file_service
from app.services.ai_service import (
    ClaudeService,
    ServiceUnavailableError,
    RateLimitError,
)
from app.services.auth.dependencies import get_current_user

router = APIRouter(prefix="/meals", tags=["meals"])
templates = Jinja2Templates(directory="app/templates")

# Initialize AI service
claude_service = ClaudeService()


@router.get("/log", response_class=HTMLResponse)
async def meal_log_page(request: Request, user: User = Depends(get_current_user)):
    """Meal logging page."""
    return templates.TemplateResponse(
        "meals/log.html", {"request": request, "user": user}
    )


@router.post("/create")
async def create_meal(
    request: Request,
    image: Optional[UploadFile] = File(None),
    user_notes: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    meal_timestamp: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
        user_id=user.id,
        image_path=image_path,
        user_notes=user_notes,
        country=country,
        timestamp=timestamp,
    )

    # Redirect to ingredient editing
    return RedirectResponse(url=f"/meals/{meal.id}/edit-ingredients", status_code=303)


@router.get("/{meal_id}/edit-ingredients", response_class=HTMLResponse)
async def edit_ingredients_page(
    request: Request,
    meal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Page for adding/editing meal ingredients."""
    meal = meal_service.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Verify ownership
    if meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get existing feedback for meal analysis (if any)
    existing_feedback = None
    if meal.ai_suggested_ingredients:
        existing_feedback = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.user_id == user.id,
                UserFeedback.feature_type == "meal_analysis",
                UserFeedback.feature_id == meal_id,
            )
            .first()
        )

    return templates.TemplateResponse(
        "meals/edit_ingredients.html",
        {
            "request": request,
            "meal": meal,
            "user": user,
            "ingredient_states": [state.value for state in IngredientState],
            "existing_rating": existing_feedback.rating if existing_feedback else 0,
            "existing_feedback": existing_feedback.feedback_text
            if existing_feedback
            else "",
        },
    )


@router.post("/{meal_id}/analyze-image")
async def analyze_meal_image(
    request: Request,
    meal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyze meal image with Claude AI and return ingredient suggestions.

    This endpoint is called automatically by the edit_ingredients page via htmx
    when a meal has an associated image.

    Returns: HTML partial with AI-suggested ingredients
    """
    meal = meal_service.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Verify ownership
    if meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not meal.image_path:
        raise HTTPException(
            status_code=400, detail="No image associated with this meal"
        )

    try:
        # Step 1: Validate that image contains food
        is_food = await claude_service.validate_meal_image(meal.image_path)
        if not is_food:
            return templates.TemplateResponse(
                "meals/partials/analysis_error.html",
                {
                    "request": request,
                    "error": "This doesn't appear to be a food image. Please upload a photo of your meal.",
                    "show_manual_entry": True,
                },
            )

        # Step 2: Analyze image for ingredients and meal name
        result = await claude_service.analyze_meal_image(
            image_path=meal.image_path, user_notes=meal.user_notes
        )

        # Store AI analysis results for evals/data science
        meal_service.update_meal_ai_response(db, meal_id, result["raw_response"])

        # Update meal with AI-suggested name and store original suggestions
        meal.name = result["meal_name"]
        meal.name_source = "ai"  # Track that name came from AI
        meal.ai_suggested_ingredients = result["ingredients"]  # Store for evals
        db.commit()

        # Auto-accept: Add all AI-suggested ingredients to the meal with source='ai'
        for suggestion in result["ingredients"]:
            try:
                ingredient_state = IngredientState(suggestion["state"])
                meal_service.add_ingredient_to_meal(
                    db=db,
                    meal_id=meal_id,
                    ingredient_name=suggestion["name"],
                    state=ingredient_state,
                    quantity_description=suggestion.get("quantity"),
                    confidence=suggestion.get("confidence"),
                    source="ai",
                )
            except (ValueError, KeyError):
                # Skip malformed suggestions
                continue

        # Refresh meal to get all ingredients
        db.refresh(meal)

        # Return HTML to replace the entire AI container
        from fastapi.responses import HTMLResponse

        # Build complete status bar + content section wrapped in #ai-container
        response_html = f"""
        <div id="ai-container">
            <!-- Complete status bar (replaces analyzing bar) -->
            <div style="
                background: #d4edda;
                border-left: 4px solid #28a745;
                color: #155724;
                padding: 0.75rem 1rem;
                border-radius: 8px;
                margin-bottom: 1.5rem;
                font-size: 14px;
            ">
                ✓ AI Analysis Complete - Ready for review
            </div>

            <!-- Content section -->
            <div id="analysis-and-ingredients">
            <header style="margin-bottom: 1.5rem;">
                <h1
                    id="meal-name-header"
                    onclick="makeEditable(this, {meal.id}, null, 'meal_name')"
                    style="cursor: text; padding: 0.25rem; border-radius: 8px; margin-bottom: 0.5rem;"
                    title="Click to edit meal name"
                >
                    {meal.name or "Untitled Meal"}
                </h1>
                <p style="font-size: 14px; color: #666; margin: 0;">Click any field to edit</p>
            </header>

            <section style="margin-bottom: 1.5rem;">
                <h3>Ingredients</h3>
                <div id="ingredients-list">
        """

        # Build all ingredient items
        ingredients_parts = [response_html]
        for mi in meal.meal_ingredients:
            ingredient_partial = templates.TemplateResponse(
                "meals/partials/ingredient_item.html",
                {"request": {}, "meal_ingredient": mi},
            )
            ingredients_parts.append(ingredient_partial.body.decode())

        ingredients_parts.append("""
                </div>
            </section>
            </div>
        </div>
        """)

        return HTMLResponse(content="".join(ingredients_parts))

    except ServiceUnavailableError:
        return templates.TemplateResponse(
            "meals/partials/analysis_error.html",
            {
                "request": request,
                "error": "AI service is temporarily unavailable. Please try again in a moment.",
                "show_manual_entry": True,
            },
        )
    except RateLimitError:
        return templates.TemplateResponse(
            "meals/partials/analysis_error.html",
            {
                "request": request,
                "error": "Too many requests. Please wait a minute and try again.",
                "show_manual_entry": True,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "meals/partials/analysis_error.html",
            {
                "request": request,
                "error": f"Analysis failed: {str(e)}",
                "show_manual_entry": True,
            },
        )


@router.post("/{meal_id}/ingredients/add")
async def add_ingredient(
    meal_id: int,
    ingredient_name: str = Form(...),
    state: str = Form(...),
    quantity: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add an ingredient to a meal."""
    # Validate meal exists
    meal = meal_service.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Verify ownership
    if meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

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
        quantity_description=quantity,
    )

    # Return HTML partial for htmx
    return templates.TemplateResponse(
        "meals/partials/ingredient_item.html",
        {"request": {}, "meal_ingredient": meal_ingredient},
    )


@router.delete("/{meal_id}/ingredients/{meal_ingredient_id}")
async def remove_ingredient(
    meal_id: int,
    meal_ingredient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove an ingredient from a meal."""
    # Verify ownership
    meal = meal_service.get_meal(db, meal_id)
    if meal and meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    success = meal_service.remove_ingredient_from_meal(db, meal_ingredient_id)
    if not success:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    # Return empty response - htmx will remove the element
    from fastapi.responses import Response

    return Response(status_code=200)


@router.post("/{meal_id}/complete")
async def complete_meal(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Publish meal and redirect to history."""
    # Verify ownership before publishing
    existing_meal = meal_service.get_meal(db, meal_id)
    if existing_meal and existing_meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Publish the meal (changes status from draft to published)
    meal = meal_service.publish_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    return RedirectResponse(url="/meals/history", status_code=303)


@router.get("/history", response_class=HTMLResponse)
async def meal_history_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Meal history page."""
    meals = meal_service.get_user_meals(db, user.id, limit=50)

    return templates.TemplateResponse(
        "meals/history.html", {"request": request, "user": user, "meals": meals}
    )


@router.put("/{meal_id}/name")
async def update_meal_name(
    meal_id: int,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update meal name (inline editing)."""
    # Verify ownership
    existing_meal = meal_service.get_meal(db, meal_id)
    if existing_meal and existing_meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    meal = meal_service.update_meal_name(db, meal_id, name)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    return {"status": "updated", "name": name}


@router.put("/{meal_id}")
async def update_meal_metadata(
    meal_id: int,
    country: Optional[str] = Form(None),
    user_notes: Optional[str] = Form(None),
    timestamp: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update meal metadata (country, notes, timestamp) - inline editing."""
    # Verify ownership
    existing_meal = meal_service.get_meal(db, meal_id)
    if existing_meal and existing_meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Parse timestamp if provided
    parsed_timestamp = None
    if timestamp:
        parsed_timestamp = datetime.fromisoformat(timestamp)

    meal = meal_service.update_meal(
        db=db,
        meal_id=meal_id,
        country=country,
        user_notes=user_notes,
        timestamp=parsed_timestamp,
    )
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    return {
        "status": "updated",
        "country": meal.country,
        "user_notes": meal.user_notes,
        "timestamp": meal.timestamp.isoformat() if meal.timestamp else None,
    }


@router.put("/{meal_id}/ingredients/{meal_ingredient_id}")
async def update_ingredient(
    meal_id: int,
    meal_ingredient_id: int,
    ingredient_name: Optional[str] = Form(None),
    quantity: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update ingredient name or quantity (inline editing)."""
    # Verify ownership
    meal = meal_service.get_meal(db, meal_id)
    if meal and meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    meal_ingredient = meal_service.update_ingredient_in_meal(
        db=db,
        meal_ingredient_id=meal_ingredient_id,
        ingredient_name=ingredient_name,
        quantity_description=quantity,
    )

    if not meal_ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    return {
        "status": "updated",
        "ingredient_name": meal_ingredient.ingredient.name,
        "quantity": meal_ingredient.quantity_description,
    }


@router.patch("/ingredients/{meal_ingredient_id}/state")
async def update_ingredient_state(
    meal_ingredient_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update ingredient state (raw/cooked/processed)."""
    data = await request.json()
    new_state = data.get("state")

    if new_state not in ["raw", "cooked", "processed"]:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Update state
    meal_ingredient = meal_service.update_ingredient_state(
        db=db, meal_ingredient_id=meal_ingredient_id, state=IngredientState(new_state)
    )

    if not meal_ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    return {"status": "success", "state": new_state}


@router.delete("/{meal_id}")
async def delete_meal(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a meal."""
    # Get meal to delete image file
    meal = meal_service.get_meal(db, meal_id)

    # Verify ownership
    if meal and meal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if meal and meal.image_path:
        file_service.delete_file(meal.image_path)

    success = meal_service.delete_meal(db, meal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Return empty response - htmx will remove the element
    from fastapi.responses import Response

    return Response(status_code=200)
