"""
Factory functions for creating test data.

These factories create model instances with sensible defaults.
Use db.flush() to get IDs without committing (for transaction rollback).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import secrets

import bcrypt
from sqlalchemy.orm import Session

from app.models import (
    User,
    Meal,
    Ingredient,
    MealIngredient,
    IngredientState,
    Symptom,
    DiagnosisRun,
    DiagnosisResult,
    DiagnosisCitation,
    UserFeedback,
    Session as UserSession,
    Invite,
)


# =============================================================================
# User Factory
# =============================================================================


def create_user(
    db: Session,
    email: Optional[str] = None,
    password: str = "testpassword123",
    is_admin: bool = False,
    **overrides,
) -> User:
    """
    Create a test user with hashed password.

    Args:
        db: Database session
        email: User email (auto-generated if not provided)
        password: Plain text password to hash
        is_admin: Whether user is an admin
        **overrides: Additional fields to override

    Returns:
        Created User object
    """
    if email is None:
        email = f"testuser_{secrets.token_hex(4)}@example.com"

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

    defaults = {
        "email": email.lower(),
        "password_hash": password_hash,
        "is_admin": is_admin,
    }
    defaults.update(overrides)

    user = User(**defaults)
    db.add(user)
    db.flush()
    return user


# =============================================================================
# Session Factory
# =============================================================================


def create_session(
    db: Session,
    user: User,
    expires_in: timedelta = timedelta(days=7),
    user_agent: str = "pytest-test-client",
    ip_address: str = "127.0.0.1",
    **overrides,
) -> UserSession:
    """
    Create a user session.

    Args:
        db: Database session
        user: User to create session for
        expires_in: Session expiration time from now
        user_agent: User agent string
        ip_address: Client IP address
        **overrides: Additional fields to override

    Returns:
        Created Session object
    """
    defaults = {
        "user_id": user.id,
        "token": secrets.token_urlsafe(32),
        "expires_at": datetime.now(timezone.utc) + expires_in,
        "user_agent": user_agent,
        "ip_address": ip_address,
    }
    defaults.update(overrides)

    session = UserSession(**defaults)
    db.add(session)
    db.flush()
    return session


# =============================================================================
# Invite Factory
# =============================================================================


def create_invite(
    db: Session,
    creator: User,
    expires_in: timedelta = timedelta(days=7),
    used: bool = False,
    used_by: Optional[User] = None,
    **overrides,
) -> Invite:
    """
    Create an invite token.

    Args:
        db: Database session
        creator: Admin user who created the invite
        expires_in: Expiration time from now
        used: Whether the invite has been used
        used_by: User who used the invite (if used)
        **overrides: Additional fields to override

    Returns:
        Created Invite object
    """
    now = datetime.now(timezone.utc)

    defaults = {
        "token": secrets.token_urlsafe(32),
        "created_by": creator.id,
        "expires_at": now + expires_in,
        "used_at": now if used else None,
        "used_by": used_by.id if used_by else None,
    }
    defaults.update(overrides)

    invite = Invite(**defaults)
    db.add(invite)
    db.flush()
    return invite


# =============================================================================
# Ingredient Factory
# =============================================================================


def create_ingredient(
    db: Session,
    name: Optional[str] = None,
    normalized_name: Optional[str] = None,
    **overrides,
) -> Ingredient:
    """
    Create an ingredient.

    Args:
        db: Database session
        name: Ingredient name (auto-generated if not provided)
        normalized_name: Normalized name (derived from name if not provided)
        **overrides: Additional fields to override

    Returns:
        Created Ingredient object
    """
    if name is None:
        name = f"Ingredient_{secrets.token_hex(4)}"

    if normalized_name is None:
        normalized_name = Ingredient.normalize_name(name)

    defaults = {
        "name": name,
        "normalized_name": normalized_name,
    }
    defaults.update(overrides)

    ingredient = Ingredient(**defaults)
    db.add(ingredient)
    db.flush()
    return ingredient


# =============================================================================
# Meal Factory
# =============================================================================


def create_meal(
    db: Session,
    user: User,
    name: Optional[str] = None,
    status: str = "published",
    timestamp: Optional[datetime] = None,
    **overrides,
) -> Meal:
    """
    Create a meal.

    Args:
        db: Database session
        user: User who owns the meal
        name: Meal name (auto-generated if not provided)
        status: 'draft' or 'published'
        timestamp: When the meal was logged
        **overrides: Additional fields to override

    Returns:
        Created Meal object
    """
    if name is None:
        name = f"Test Meal {secrets.token_hex(4)}"

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    defaults = {
        "user_id": user.id,
        "name": name,
        "status": status,
        "timestamp": timestamp,
        "name_source": "user-edit",
    }
    defaults.update(overrides)

    meal = Meal(**defaults)
    db.add(meal)
    db.flush()
    return meal


# =============================================================================
# MealIngredient Factory
# =============================================================================


def create_meal_ingredient(
    db: Session,
    meal: Meal,
    ingredient: Ingredient,
    state: IngredientState = IngredientState.COOKED,
    quantity_description: Optional[str] = None,
    confidence: Optional[float] = None,
    source: str = "manual",
    **overrides,
) -> MealIngredient:
    """
    Create a meal-ingredient link.

    Args:
        db: Database session
        meal: Meal to link
        ingredient: Ingredient to link
        state: Ingredient state (raw, cooked, processed)
        quantity_description: Quantity description
        confidence: AI confidence score
        source: 'ai' or 'manual'
        **overrides: Additional fields to override

    Returns:
        Created MealIngredient object
    """
    defaults = {
        "meal_id": meal.id,
        "ingredient_id": ingredient.id,
        "state": state,
        "quantity_description": quantity_description,
        "confidence": confidence,
        "source": source,
    }
    defaults.update(overrides)

    meal_ingredient = MealIngredient(**defaults)
    db.add(meal_ingredient)
    db.flush()
    return meal_ingredient


# =============================================================================
# Symptom Factory
# =============================================================================


def create_symptom(
    db: Session,
    user: User,
    raw_description: Optional[str] = None,
    tags: Optional[List[Dict]] = None,
    structured_type: Optional[str] = None,
    severity: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    episode_id: Optional[int] = None,
    **overrides,
) -> Symptom:
    """
    Create a symptom entry.

    Args:
        db: Database session
        user: User who logged the symptom
        raw_description: User's description (auto-generated if not provided)
        tags: List of {"name": str, "severity": int}
        structured_type: Symptom type (derived from tags if not provided)
        severity: Overall severity (derived from tags if not provided)
        start_time: When symptom started
        end_time: When symptom ended
        episode_id: Link to previous symptom if continuation
        **overrides: Additional fields to override

    Returns:
        Created Symptom object
    """
    if start_time is None:
        start_time = datetime.now(timezone.utc)

    if tags is None:
        tags = [{"name": "bloating", "severity": 5}]

    if raw_description is None:
        tag_descriptions = [f"{t['name']} ({t['severity']}/10)" for t in tags]
        raw_description = ", ".join(tag_descriptions)

    if structured_type is None and tags:
        # Use most severe tag as structured type
        sorted_tags = sorted(tags, key=lambda t: t.get("severity", 0), reverse=True)
        structured_type = sorted_tags[0]["name"].lower()

    if severity is None and tags:
        severity = max(t.get("severity", 0) for t in tags)

    defaults = {
        "user_id": user.id,
        "raw_description": raw_description,
        "tags": tags,
        "structured_type": structured_type,
        "severity": severity,
        "start_time": start_time,
        "end_time": end_time,
        "timestamp": start_time,
        "episode_id": episode_id,
    }
    defaults.update(overrides)

    symptom = Symptom(**defaults)
    db.add(symptom)
    db.flush()
    return symptom


# =============================================================================
# Diagnosis Factory Functions
# =============================================================================


def create_diagnosis_run(
    db: Session,
    user: User,
    meals_analyzed: int = 5,
    symptoms_analyzed: int = 3,
    sufficient_data: bool = True,
    status: str = "completed",
    date_range_start: Optional[datetime] = None,
    date_range_end: Optional[datetime] = None,
    **overrides,
) -> DiagnosisRun:
    """
    Create a diagnosis run.

    Args:
        db: Database session
        user: User who ran the diagnosis
        meals_analyzed: Number of meals analyzed
        symptoms_analyzed: Number of symptoms analyzed
        sufficient_data: Whether there was sufficient data
        status: 'pending', 'processing', 'completed', 'failed'
        date_range_start: Start of analysis range
        date_range_end: End of analysis range
        **overrides: Additional fields to override

    Returns:
        Created DiagnosisRun object
    """
    now = datetime.now(timezone.utc)

    if date_range_start is None:
        date_range_start = now - timedelta(days=30)
    if date_range_end is None:
        date_range_end = now

    defaults = {
        "user_id": user.id,
        "run_timestamp": now,
        "status": status,
        "meals_analyzed": meals_analyzed,
        "symptoms_analyzed": symptoms_analyzed,
        "date_range_start": date_range_start,
        "date_range_end": date_range_end,
        "sufficient_data": sufficient_data,
        "web_search_enabled": True,
    }
    defaults.update(overrides)

    run = DiagnosisRun(**defaults)
    db.add(run)
    db.flush()
    return run


def create_diagnosis_result(
    db: Session,
    run: DiagnosisRun,
    ingredient: Ingredient,
    confidence_score: float = 0.75,
    confidence_level: str = "high",
    times_eaten: int = 5,
    times_followed_by_symptoms: int = 4,
    associated_symptoms: Optional[List[Dict]] = None,
    **overrides,
) -> DiagnosisResult:
    """
    Create a diagnosis result.

    Args:
        db: Database session
        run: DiagnosisRun this result belongs to
        ingredient: Ingredient being diagnosed
        confidence_score: Confidence score (0.0-1.0)
        confidence_level: 'high', 'medium', 'low'
        times_eaten: How many times ingredient was eaten
        times_followed_by_symptoms: How many times symptoms followed
        associated_symptoms: List of symptom associations
        **overrides: Additional fields to override

    Returns:
        Created DiagnosisResult object
    """
    if associated_symptoms is None:
        associated_symptoms = [
            {"name": "bloating", "severity_avg": 6.5, "frequency": 4, "lag_hours": 1.5}
        ]

    defaults = {
        "run_id": run.id,
        "ingredient_id": ingredient.id,
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "immediate_correlation": 3,
        "delayed_correlation": 1,
        "cumulative_correlation": 0,
        "times_eaten": times_eaten,
        "times_followed_by_symptoms": times_followed_by_symptoms,
        "state_matters": False,
        "associated_symptoms": associated_symptoms,
    }
    defaults.update(overrides)

    result = DiagnosisResult(**defaults)
    db.add(result)
    db.flush()
    return result


def create_diagnosis_citation(
    db: Session,
    result: DiagnosisResult,
    source_url: str = "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    source_title: str = "Test Medical Citation",
    source_type: str = "medical_journal",
    snippet: Optional[str] = None,
    relevance_score: float = 0.85,
    **overrides,
) -> DiagnosisCitation:
    """
    Create a diagnosis citation.

    Args:
        db: Database session
        result: DiagnosisResult this citation supports
        source_url: URL of the source
        source_title: Title of the source
        source_type: 'nih', 'medical_journal', 'rd_site', 'other'
        snippet: Brief excerpt
        relevance_score: Relevance score (0.0-1.0)
        **overrides: Additional fields to override

    Returns:
        Created DiagnosisCitation object
    """
    defaults = {
        "result_id": result.id,
        "source_url": source_url,
        "source_title": source_title,
        "source_type": source_type,
        "snippet": snippet or "This is a test citation snippet.",
        "relevance_score": relevance_score,
    }
    defaults.update(overrides)

    citation = DiagnosisCitation(**defaults)
    db.add(citation)
    db.flush()
    return citation


# =============================================================================
# UserFeedback Factory
# =============================================================================


def create_user_feedback(
    db: Session,
    user: User,
    feature_type: str = "diagnosis_result",
    feature_id: int = 1,
    rating: int = 4,
    feedback_text: Optional[str] = None,
    **overrides,
) -> UserFeedback:
    """
    Create user feedback.

    Args:
        db: Database session
        user: User providing feedback
        feature_type: Type of feature ('meal_analysis', 'diagnosis_result', etc.)
        feature_id: ID of the feature in its table
        rating: Rating 0-5
        feedback_text: Optional feedback text
        **overrides: Additional fields to override

    Returns:
        Created UserFeedback object
    """
    defaults = {
        "user_id": user.id,
        "feature_type": feature_type,
        "feature_id": feature_id,
        "rating": rating,
        "feedback_text": feedback_text,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)

    feedback = UserFeedback(**defaults)
    db.add(feedback)
    db.flush()
    return feedback


# =============================================================================
# Composite Factories (for complex test scenarios)
# =============================================================================


def create_meal_with_ingredients(
    db: Session,
    user: User,
    ingredients: List[Dict[str, Any]],
    meal_name: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    **meal_overrides,
) -> Meal:
    """
    Create a meal with multiple ingredients.

    Args:
        db: Database session
        user: User who owns the meal
        ingredients: List of ingredient specs:
            [{"name": str, "state": IngredientState, "quantity": str (optional)}]
        meal_name: Name of the meal
        timestamp: When the meal was logged
        **meal_overrides: Additional meal fields

    Returns:
        Created Meal with ingredients attached
    """
    meal = create_meal(db, user, name=meal_name, timestamp=timestamp, **meal_overrides)

    for ing_spec in ingredients:
        # Find or create ingredient
        name = ing_spec["name"]
        normalized = Ingredient.normalize_name(name)

        ingredient = (
            db.query(Ingredient)
            .filter(Ingredient.normalized_name == normalized)
            .first()
        )

        if not ingredient:
            ingredient = create_ingredient(db, name=name)

        # Create meal-ingredient link
        state = ing_spec.get("state", IngredientState.COOKED)
        quantity = ing_spec.get("quantity")

        create_meal_ingredient(
            db, meal, ingredient, state=state, quantity_description=quantity
        )

    return meal


def create_symptom_episode(
    db: Session,
    user: User,
    tags: List[Dict],
    occurrences: int = 3,
    hours_between: float = 4.0,
    start_time: Optional[datetime] = None,
) -> List[Symptom]:
    """
    Create a series of linked symptoms (episode).

    Args:
        db: Database session
        user: User who logged the symptoms
        tags: Symptom tags for all occurrences
        occurrences: Number of symptom logs
        hours_between: Hours between each occurrence
        start_time: Time of first symptom

    Returns:
        List of created Symptom objects (linked via episode_id)
    """
    if start_time is None:
        start_time = datetime.now(timezone.utc)

    symptoms = []
    prev_id = None

    for i in range(occurrences):
        time = start_time + timedelta(hours=i * hours_between)
        symptom = create_symptom(
            db, user, tags=tags, start_time=time, episode_id=prev_id
        )
        symptoms.append(symptom)
        prev_id = symptom.id

    return symptoms


def create_test_scenario_onion_intolerance(
    db: Session,
    user: User,
    num_meals: int = 5,
) -> Dict[str, Any]:
    """
    Create a realistic onion intolerance test scenario.

    Creates meals with raw onion followed by bloating symptoms 0.5-1.5 hours later.

    Args:
        db: Database session
        user: User for the scenario
        num_meals: Number of meals to create

    Returns:
        Dict with created entities: {"meals": [...], "symptoms": [...], "onion": Ingredient}
    """
    onion = create_ingredient(db, name="Onion")
    meals = []
    symptoms = []

    base_time = datetime.now(timezone.utc) - timedelta(days=7)

    for i in range(num_meals):
        # Create meal
        meal_time = base_time + timedelta(days=i, hours=i * 3 % 12 + 8)  # Vary times
        meal = create_meal(
            db, user, name=f"Meal with onion {i + 1}", timestamp=meal_time
        )
        create_meal_ingredient(db, meal, onion, state=IngredientState.RAW)
        meals.append(meal)

        # Create symptom 0.5-1.5 hours later
        lag_hours = 0.5 + (i % 3) * 0.5  # Vary lag
        symptom_time = meal_time + timedelta(hours=lag_hours)
        severity = 5 + i % 5  # Vary severity 5-9
        symptom = create_symptom(
            db,
            user,
            tags=[{"name": "bloating", "severity": severity}],
            start_time=symptom_time,
        )
        symptoms.append(symptom)

    return {
        "meals": meals,
        "symptoms": symptoms,
        "onion": onion,
    }
