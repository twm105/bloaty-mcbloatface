"""Admin dashboard service for platform usage metrics."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import case, cast, func, String
from sqlalchemy.orm import Session

from app.models import (
    AIUsageLog,
    DiagnosisRun,
    Meal,
    Symptom,
    User,
)
from app.models.session import Session as UserSession

logger = logging.getLogger(__name__)


def backfill_orphaned_usage_logs(db: Session) -> int:
    """Backfill NULL user_id on ai_usage_logs via diagnosis_runs join.

    Returns the number of records updated.
    """
    try:
        orphan_count = (
            db.query(func.count(AIUsageLog.id))
            .filter(
                AIUsageLog.user_id.is_(None),
                AIUsageLog.request_type == "diagnosis_run",
            )
            .scalar()
        )
        if not orphan_count:
            return 0

        updated = (
            db.query(AIUsageLog)
            .filter(
                AIUsageLog.user_id.is_(None),
                AIUsageLog.request_type == "diagnosis_run",
                AIUsageLog.request_id == cast(DiagnosisRun.id, String),
            )
            .update(
                {AIUsageLog.user_id: DiagnosisRun.user_id},
                synchronize_session=False,
            )
        )
        db.commit()
        logger.info("Backfilled user_id on %d orphaned ai_usage_logs", updated)
        return updated
    except Exception:
        logger.exception("Failed to backfill orphaned ai_usage_logs")
        db.rollback()
        return 0


def _cents_to_dollars(cents) -> float:
    """Convert cents (Decimal or None) to dollars float."""
    if cents is None:
        return 0.0
    return round(float(cents) / 100, 2)


def _week_boundaries(num_weeks: int = 4) -> list[tuple[datetime, datetime, datetime]]:
    """Return (start, end, monday) boundaries for the last N calendar weeks.

    Weeks are Monday-aligned. The most recent entry is the current
    (possibly partial) week. Returns tuples of (start, end, monday)
    where monday is the w/c date, oldest first (chronological L→R).
    """
    now = datetime.utcnow()
    # Find the Monday of the current week (weekday 0 = Monday)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    current_monday = today - timedelta(days=today.weekday())

    weeks = []
    for i in range(num_weeks):
        monday = current_monday - timedelta(weeks=i)
        start = monday
        end = monday + timedelta(days=7)
        weeks.append((start, end, monday))
    weeks.reverse()
    return weeks


def get_all_users_overview(db: Session) -> list[dict]:
    """
    Get overview stats for all users in a single batch query.

    Returns list of dicts with: user, member_since, total_meals,
    total_symptoms, total_api_spend_dollars, weekly_spend.
    """
    users = db.query(User).order_by(User.created_at).all()
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Batch: meal counts per user
    meal_counts = dict(
        db.query(Meal.user_id, func.count(Meal.id))
        .filter(Meal.user_id.in_(user_ids))
        .group_by(Meal.user_id)
        .all()
    )

    # Batch: symptom counts per user
    symptom_counts = dict(
        db.query(Symptom.user_id, func.count(Symptom.id))
        .filter(Symptom.user_id.in_(user_ids))
        .group_by(Symptom.user_id)
        .all()
    )

    # Batch: total spend per user
    spend_totals = dict(
        db.query(
            AIUsageLog.user_id,
            func.sum(AIUsageLog.estimated_cost_cents),
        )
        .filter(AIUsageLog.user_id.in_(user_ids))
        .group_by(AIUsageLog.user_id)
        .all()
    )

    # Batch: weekly spend bucketed by Monday-aligned calendar weeks
    weeks = _week_boundaries(4)
    week_labels = [w[2].strftime("w/c %b %d") for w in weeks]
    week_cases = []
    for idx, (start, end, _monday) in enumerate(weeks):
        week_cases.append(
            func.sum(
                case(
                    (
                        (AIUsageLog.timestamp >= start) & (AIUsageLog.timestamp < end),
                        AIUsageLog.estimated_cost_cents,
                    ),
                    else_=Decimal("0"),
                )
            ).label(f"week_{idx}")
        )

    weekly_rows = (
        db.query(AIUsageLog.user_id, *week_cases)
        .filter(
            AIUsageLog.user_id.in_(user_ids),
            AIUsageLog.timestamp >= weeks[0][0],
        )
        .group_by(AIUsageLog.user_id)
        .all()
    )
    weekly_by_user = {}
    for row in weekly_rows:
        weekly_by_user[row[0]] = [_cents_to_dollars(row[i + 1]) for i in range(4)]

    results = []
    for u in users:
        results.append(
            {
                "user": u,
                "member_since": u.created_at,
                "total_meals": meal_counts.get(u.id, 0),
                "total_symptoms": symptom_counts.get(u.id, 0),
                "total_api_spend_dollars": _cents_to_dollars(spend_totals.get(u.id)),
                "weekly_spend": weekly_by_user.get(u.id, [0.0, 0.0, 0.0, 0.0]),
            }
        )

    return results, week_labels


def get_platform_totals(db: Session) -> dict:
    """Get platform-wide summary totals."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = db.query(func.count(User.id)).scalar() or 0
    total_meals = db.query(func.count(Meal.id)).scalar() or 0
    total_symptoms = db.query(func.count(Symptom.id)).scalar() or 0

    total_spend_cents = db.query(
        func.sum(AIUsageLog.estimated_cost_cents)
    ).scalar() or Decimal("0")
    month_spend_cents = db.query(func.sum(AIUsageLog.estimated_cost_cents)).filter(
        AIUsageLog.timestamp >= month_start
    ).scalar() or Decimal("0")

    return {
        "total_users": total_users,
        "total_meals": total_meals,
        "total_symptoms": total_symptoms,
        "total_api_spend_dollars": _cents_to_dollars(total_spend_cents),
        "spend_this_month": _cents_to_dollars(month_spend_cents),
    }


def get_user_detail(db: Session, user_id: UUID) -> Optional[dict]:
    """Get comprehensive usage detail for a single user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Last active (most recent session)
    last_session = (
        db.query(UserSession.created_at)
        .filter(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
        .first()
    )
    last_active = last_session[0] if last_session else None

    # Meals
    total_meals = (
        db.query(func.count(Meal.id)).filter(Meal.user_id == user_id).scalar() or 0
    )
    meals_this_month = (
        db.query(func.count(Meal.id))
        .filter(Meal.user_id == user_id, Meal.timestamp >= month_start)
        .scalar()
        or 0
    )
    meals_with_images = (
        db.query(func.count(Meal.id))
        .filter(Meal.user_id == user_id, Meal.image_path.isnot(None))
        .scalar()
        or 0
    )
    meals_published = (
        db.query(func.count(Meal.id))
        .filter(Meal.user_id == user_id, Meal.status == "published")
        .scalar()
        or 0
    )

    # Symptoms
    total_symptoms = (
        db.query(func.count(Symptom.id)).filter(Symptom.user_id == user_id).scalar()
        or 0
    )
    symptoms_this_month = (
        db.query(func.count(Symptom.id))
        .filter(Symptom.user_id == user_id, Symptom.start_time >= month_start)
        .scalar()
        or 0
    )
    unique_symptom_types = (
        db.query(func.count(func.distinct(Symptom.structured_type)))
        .filter(Symptom.user_id == user_id)
        .scalar()
        or 0
    )

    # API usage
    api_stats = (
        db.query(
            func.count(AIUsageLog.id),
            func.sum(AIUsageLog.estimated_cost_cents),
            func.sum(AIUsageLog.input_tokens),
            func.sum(AIUsageLog.output_tokens),
            func.sum(AIUsageLog.cached_tokens),
        )
        .filter(AIUsageLog.user_id == user_id)
        .first()
    )
    total_api_calls = api_stats[0] or 0
    total_spend_cents = api_stats[1] or Decimal("0")
    total_input_tokens = api_stats[2] or 0
    total_output_tokens = api_stats[3] or 0
    total_cached_tokens = api_stats[4] or 0

    spend_this_month_cents = db.query(func.sum(AIUsageLog.estimated_cost_cents)).filter(
        AIUsageLog.user_id == user_id, AIUsageLog.timestamp >= month_start
    ).scalar() or Decimal("0")

    # Weekly spend with Monday-aligned date labels
    weeks = _week_boundaries(4)
    weekly_spend = []
    for start, end, monday in weeks:
        week_cents = db.query(func.sum(AIUsageLog.estimated_cost_cents)).filter(
            AIUsageLog.user_id == user_id,
            AIUsageLog.timestamp >= start,
            AIUsageLog.timestamp < end,
        ).scalar() or Decimal("0")
        weekly_spend.append(
            {
                "label": f"w/c {monday.strftime('%b %d')}",
                "dollars": _cents_to_dollars(week_cents),
            }
        )

    # Feature usage by service_type
    feature_usage = dict(
        db.query(AIUsageLog.service_type, func.count(AIUsageLog.id))
        .filter(AIUsageLog.user_id == user_id)
        .group_by(AIUsageLog.service_type)
        .all()
    )

    # Diagnosis runs
    total_diagnosis_runs = (
        db.query(func.count(DiagnosisRun.id))
        .filter(DiagnosisRun.user_id == user_id)
        .scalar()
        or 0
    )
    completed_diagnosis_runs = (
        db.query(func.count(DiagnosisRun.id))
        .filter(DiagnosisRun.user_id == user_id, DiagnosisRun.status == "completed")
        .scalar()
        or 0
    )

    return {
        "user": user,
        "account": {
            "member_since": user.created_at,
            "last_active": last_active,
            "role": "admin" if user.is_admin else "user",
        },
        "meals": {
            "total": total_meals,
            "this_month": meals_this_month,
            "with_images": meals_with_images,
            "published": meals_published,
        },
        "symptoms": {
            "total": total_symptoms,
            "this_month": symptoms_this_month,
            "unique_types": unique_symptom_types,
        },
        "api": {
            "total_calls": total_api_calls,
            "total_spend_dollars": _cents_to_dollars(total_spend_cents),
            "spend_this_month": _cents_to_dollars(spend_this_month_cents),
        },
        "weekly_spend": weekly_spend,
        "feature_usage": feature_usage,
        "tokens": {
            "input": total_input_tokens,
            "output": total_output_tokens,
            "cached": total_cached_tokens,
        },
        "diagnosis": {
            "total_runs": total_diagnosis_runs,
            "completed_runs": completed_diagnosis_runs,
        },
    }
