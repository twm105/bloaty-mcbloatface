"""Unit tests for admin dashboard service."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.services.admin_dashboard_service import (
    backfill_orphaned_usage_logs,
    get_all_users_overview,
    get_platform_totals,
    get_user_detail,
)
from tests.factories import (
    create_ai_usage_log,
    create_diagnosis_run,
    create_meal,
    create_session,
    create_symptom,
    create_user,
)


def _find_by_email(results, email):
    """Find a user row by email in overview results."""
    for r in results:
        if r["user"].email == email:
            return r
    return None


class TestGetAllUsersOverview:
    def test_returns_all_users(self, db: Session):
        """Overview includes newly created users."""
        user = create_user(db, email="overview_test@example.com")
        result, week_labels = get_all_users_overview(db)
        row = _find_by_email(result, "overview_test@example.com")
        assert row is not None
        assert row["user"].id == user.id

    def test_returns_week_labels(self, db: Session):
        """Overview returns 4 Monday-aligned week labels."""
        _result, week_labels = get_all_users_overview(db)
        assert len(week_labels) == 4
        for label in week_labels:
            assert label.startswith("w/c ")

    def test_user_with_no_data_has_zero_counts(self, db: Session):
        create_user(db, email="empty_overview@example.com")
        result, _labels = get_all_users_overview(db)
        row = _find_by_email(result, "empty_overview@example.com")

        assert row["total_meals"] == 0
        assert row["total_symptoms"] == 0
        assert row["total_api_spend_dollars"] == 0.0
        assert row["weekly_spend"] == [0.0, 0.0, 0.0, 0.0]

    def test_counts_match_user_data(self, db: Session):
        user1 = create_user(db, email="ov_user1@example.com")
        user2 = create_user(db, email="ov_user2@example.com")

        create_meal(db, user1)
        create_meal(db, user1)
        create_meal(db, user2)

        create_symptom(db, user1)
        create_symptom(db, user2)
        create_symptom(db, user2)
        create_symptom(db, user2)

        create_ai_usage_log(db, user1, estimated_cost_cents=100.0)
        create_ai_usage_log(db, user2, estimated_cost_cents=250.0)

        result, _labels = get_all_users_overview(db)
        r1 = _find_by_email(result, "ov_user1@example.com")
        r2 = _find_by_email(result, "ov_user2@example.com")

        assert r1["total_meals"] == 2
        assert r1["total_symptoms"] == 1
        assert r1["total_api_spend_dollars"] == 1.00

        assert r2["total_meals"] == 1
        assert r2["total_symptoms"] == 3
        assert r2["total_api_spend_dollars"] == 2.50

    def test_weekly_spend_current_week(self, db: Session):
        """Spend logged today appears in the last (current) week bucket (chronological)."""
        user = create_user(db, email="weekly_ov@example.com")
        now = datetime.utcnow()

        create_ai_usage_log(
            db, user, estimated_cost_cents=100.0, timestamp=now - timedelta(hours=1)
        )

        result, _labels = get_all_users_overview(db)
        row = _find_by_email(result, "weekly_ov@example.com")
        # Chronological order: oldest first, current week is last (index 3)
        assert row["weekly_spend"][3] == 1.00

    def test_weekly_spend_older_week(self, db: Session):
        """Spend logged 2 weeks ago appears in the correct earlier bucket."""
        user = create_user(db, email="weekly_old@example.com")
        now = datetime.utcnow()

        create_ai_usage_log(
            db, user, estimated_cost_cents=200.0, timestamp=now - timedelta(weeks=2)
        )

        result, _labels = get_all_users_overview(db)
        row = _find_by_email(result, "weekly_old@example.com")
        # Chronological: index 1 is ~2 weeks ago, should have the spend
        assert sum(row["weekly_spend"]) == 2.00
        # The spend must NOT be in the current week (last bucket)
        assert row["weekly_spend"][3] == 0.0

    def test_week_labels_chronological_order(self, db: Session):
        """Week labels are oldest-first (chronological L→R)."""
        create_user(db, email="week_order@example.com")
        _result, week_labels = get_all_users_overview(db)
        # Parse dates from labels "w/c Mon DD"
        dates = []
        for label in week_labels:
            # Extract date part after "w/c "
            date_str = label[4:]
            now = datetime.utcnow()
            parsed = datetime.strptime(f"{date_str} {now.year}", "%b %d %Y")
            dates.append(parsed)
        # Each date should be <= the next
        for i in range(len(dates) - 1):
            assert dates[i] <= dates[i + 1]


class TestGetPlatformTotals:
    def test_includes_created_data(self, db: Session):
        """Platform totals include data we create."""
        # Get baseline
        baseline = get_platform_totals(db)

        user = create_user(db, email="totals_test@example.com")
        create_meal(db, user)
        create_meal(db, user)
        create_symptom(db, user)
        create_ai_usage_log(db, user, estimated_cost_cents=500.0)
        create_ai_usage_log(db, user, estimated_cost_cents=300.0)

        result = get_platform_totals(db)
        assert result["total_users"] == baseline["total_users"] + 1
        assert result["total_meals"] == baseline["total_meals"] + 2
        assert result["total_symptoms"] == baseline["total_symptoms"] + 1
        # Spend increased by $8.00
        assert (
            round(
                result["total_api_spend_dollars"] - baseline["total_api_spend_dollars"],
                2,
            )
            == 8.00
        )


class TestGetUserDetail:
    def test_nonexistent_user(self, db: Session):
        import uuid

        result = get_user_detail(db, uuid.uuid4())
        assert result is None

    def test_user_with_no_data(self, db: Session):
        user = create_user(db, email="detail_empty@example.com")
        result = get_user_detail(db, user.id)

        assert result is not None
        assert result["user"].id == user.id
        assert result["meals"]["total"] == 0
        assert result["symptoms"]["total"] == 0
        assert result["api"]["total_calls"] == 0
        assert result["api"]["total_spend_dollars"] == 0.0
        assert result["tokens"]["input"] == 0
        assert result["diagnosis"]["total_runs"] == 0

    def test_user_with_full_data(self, db: Session):
        user = create_user(db, email="detail_full@example.com")

        # Meals
        create_meal(db, user, status="published", image_path="/uploads/test.jpg")
        create_meal(db, user, status="draft")

        # Symptoms
        create_symptom(db, user, tags=[{"name": "bloating", "severity": 5}])
        create_symptom(db, user, tags=[{"name": "nausea", "severity": 3}])

        # API usage
        create_ai_usage_log(
            db,
            user,
            service_type="meal_analysis",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=200,
            estimated_cost_cents=150.0,
        )
        create_ai_usage_log(
            db,
            user,
            service_type="diagnosis",
            input_tokens=2000,
            output_tokens=800,
            cached_tokens=0,
            estimated_cost_cents=300.0,
        )

        # Session (for last active)
        create_session(db, user)

        # Diagnosis run
        create_diagnosis_run(db, user, status="completed")

        result = get_user_detail(db, user.id)

        assert result["meals"]["total"] == 2
        assert result["meals"]["published"] == 1
        assert result["meals"]["with_images"] == 1

        assert result["symptoms"]["total"] == 2
        assert result["symptoms"]["unique_types"] == 2

        assert result["api"]["total_calls"] == 2
        assert result["api"]["total_spend_dollars"] == 4.50

        assert result["tokens"]["input"] == 3000
        assert result["tokens"]["output"] == 1300
        assert result["tokens"]["cached"] == 200

        assert result["feature_usage"]["meal_analysis"] == 1
        assert result["feature_usage"]["diagnosis"] == 1

        assert result["diagnosis"]["total_runs"] == 1
        assert result["diagnosis"]["completed_runs"] == 1

        assert result["account"]["last_active"] is not None
        assert result["account"]["role"] == "user"

    def test_admin_role(self, db: Session):
        user = create_user(db, email="detail_admin@example.com", is_admin=True)
        result = get_user_detail(db, user.id)
        assert result["account"]["role"] == "admin"


class TestBackfillOrphanedUsageLogs:
    def test_backfill_resolves_orphaned_logs(self, db: Session):
        """Orphaned diagnosis_run logs get user_id from matching DiagnosisRun."""
        user = create_user(db, email="backfill_test@example.com")
        run = create_diagnosis_run(db, user, status="completed")

        log = create_ai_usage_log(db, user, service_type="diagnosis")
        # Simulate the bug: NULL user_id with request_id linking to the run
        log.user_id = None
        log.request_id = str(run.id)
        log.request_type = "diagnosis_run"
        db.flush()

        updated = backfill_orphaned_usage_logs(db)
        assert updated == 1

        db.refresh(log)
        assert log.user_id == user.id

    def test_backfill_no_orphans_returns_zero(self, db: Session):
        """No NULL records → returns 0 with no writes."""
        user = create_user(db, email="no_orphans@example.com")
        create_ai_usage_log(db, user, service_type="diagnosis")

        result = backfill_orphaned_usage_logs(db)
        assert result == 0

    def test_backfill_skips_non_diagnosis_logs(self, db: Session):
        """Logs without request_type='diagnosis_run' are left alone."""
        user = create_user(db, email="skip_non_diag@example.com")

        log = create_ai_usage_log(db, user, service_type="meal_analysis")
        log.user_id = None
        log.request_type = "meal"
        log.request_id = "123"
        db.flush()

        backfill_orphaned_usage_logs(db)

        db.refresh(log)
        assert log.user_id is None

    def test_backfill_is_idempotent(self, db: Session):
        """Running twice doesn't change already-filled records."""
        user = create_user(db, email="idempotent@example.com")
        run = create_diagnosis_run(db, user, status="completed")

        log = create_ai_usage_log(db, user, service_type="diagnosis")
        log.user_id = None
        log.request_id = str(run.id)
        log.request_type = "diagnosis_run"
        db.flush()

        first = backfill_orphaned_usage_logs(db)
        assert first == 1

        db.refresh(log)
        assert log.user_id == user.id

        second = backfill_orphaned_usage_logs(db)
        assert second == 0
