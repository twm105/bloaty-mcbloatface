"""Diagnosis service for analyzing ingredient-symptom correlations."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text, and_, func
from sqlalchemy.orm import Session

from app.models import (
    DiagnosisRun,
    DiagnosisResult,
    DiagnosisCitation,
    DiscountedIngredient,
    Meal,
    Symptom,
    Ingredient,
    MealIngredient,
    User,
)
from app.config import settings


class DiagnosisService:
    """Service for running diagnosis analysis on meal and symptom data."""

    # Minimum data thresholds (loaded from central config)
    MIN_MEALS = settings.diagnosis_min_meals
    MIN_SYMPTOM_OCCURRENCES = settings.diagnosis_min_symptom_occurrences

    # Temporal lag windows (in hours)
    IMMEDIATE_LAG_MIN = 0
    IMMEDIATE_LAG_MAX = 2
    DELAYED_LAG_MIN = 4
    DELAYED_LAG_MAX = 24
    CUMULATIVE_LAG_MIN = 24
    CUMULATIVE_LAG_MAX = 168  # 7 days

    # Symptom clustering window (in hours)
    CLUSTERING_WINDOW = 4

    def __init__(self, db: Session):
        """Initialize diagnosis service."""
        self.db = db

    def get_correlated_ingredient_ids(self, user_id: str) -> List[int]:
        """
        Find all ingredients that have symptom correlations using holistic data.

        This looks at ALL data (windowed by max occurrences) to find ingredients
        that have appeared before symptoms at least MIN_SYMPTOM_OCCURRENCES times.

        Returns:
            List of ingredient IDs that have meaningful correlations
        """
        max_occurrences = settings.diagnosis_max_ingredient_occurrences

        query = text(
            """
            WITH ingredient_meal_counts AS (
                -- Count how many meals each ingredient appears in
                SELECT
                    mi.ingredient_id,
                    COUNT(DISTINCT m.id) as meal_count
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                WHERE m.user_id = :user_id
                  AND m.status = 'published'
                GROUP BY mi.ingredient_id
            ),
            symptom_episodes AS (
                SELECT
                    s.id as symptom_id,
                    s.start_time
                FROM symptoms s
                WHERE s.user_id = :user_id
                  AND s.tags IS NOT NULL
            ),
            ingredient_symptom_counts AS (
                -- For each ingredient, count symptoms that occurred within 7 days after eating it
                SELECT
                    mi.ingredient_id,
                    COUNT(DISTINCT se.symptom_id) as symptom_count
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                CROSS JOIN symptom_episodes se
                WHERE m.user_id = :user_id
                  AND m.status = 'published'
                  AND m.timestamp < se.start_time
                  AND m.timestamp >= se.start_time - INTERVAL '7 days'
                GROUP BY mi.ingredient_id
            )
            SELECT imc.ingredient_id
            FROM ingredient_meal_counts imc
            JOIN ingredient_symptom_counts isc ON imc.ingredient_id = isc.ingredient_id
            WHERE isc.symptom_count >= :min_symptom_occurrences
              AND imc.meal_count >= 2  -- Need at least 2 data points
            ORDER BY isc.symptom_count DESC
            """
        )

        result = self.db.execute(
            query,
            {
                "user_id": str(user_id),
                "min_symptom_occurrences": self.MIN_SYMPTOM_OCCURRENCES,
            }
        )

        return [row[0] for row in result]

    def check_data_sufficiency(
        self, user_id: str, date_range_start: datetime, date_range_end: datetime
    ) -> Tuple[bool, int, int]:
        """
        Check if user has sufficient data for diagnosis.

        Returns:
            Tuple of (sufficient_data, meals_count, symptoms_count)
        """
        # Count published meals in date range
        meals_count = (
            self.db.query(func.count(Meal.id))
            .filter(
                Meal.user_id == user_id,
                Meal.status == "published",
                Meal.timestamp >= date_range_start,
                Meal.timestamp <= date_range_end,
            )
            .scalar()
        )

        # Count symptom entries with tags in date range
        symptoms_count = (
            self.db.query(func.count(Symptom.id))
            .filter(
                Symptom.user_id == user_id,
                Symptom.tags.isnot(None),
                Symptom.start_time >= date_range_start,
                Symptom.start_time <= date_range_end,
            )
            .scalar()
        )

        sufficient_data = (
            meals_count >= self.MIN_MEALS
            and symptoms_count >= self.MIN_SYMPTOM_OCCURRENCES
        )

        return sufficient_data, meals_count or 0, symptoms_count or 0

    def get_temporal_correlations(
        self, user_id: str, date_range_start: datetime, date_range_end: datetime
    ) -> List[Dict]:
        """
        Run SQL temporal windowing analysis.

        For each ingredient consumed, calculates correlation with symptoms
        across three temporal lag windows: immediate (0-2hr), delayed (4-24hr),
        and cumulative (24hr+).

        Returns:
            List of dicts with correlation data per ingredient-symptom pair.
        """
        query = text(
            """
            WITH symptom_episodes AS (
                -- Extract all symptom occurrences with tags
                SELECT
                    s.id as symptom_id,
                    s.user_id,
                    s.start_time,
                    jsonb_array_elements(s.tags) as tag
                FROM symptoms s
                WHERE s.user_id = :user_id
                  AND s.tags IS NOT NULL
                  AND s.start_time >= :date_range_start
                  AND s.start_time <= :date_range_end
            ),
            ingredient_exposures AS (
                -- Cross-join meals with symptoms, calculate lag hours
                SELECT
                    i.id as ingredient_id,
                    i.normalized_name as ingredient_name,
                    mi.state as ingredient_state,
                    m.id as meal_id,
                    m.timestamp as meal_timestamp,
                    se.symptom_id,
                    se.tag->>'name' as symptom_name,
                    COALESCE((se.tag->>'severity')::numeric, 0) as symptom_severity,
                    EXTRACT(EPOCH FROM (se.start_time - m.timestamp))/3600 as lag_hours
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                JOIN ingredients i ON mi.ingredient_id = i.id
                CROSS JOIN symptom_episodes se
                WHERE m.user_id = se.user_id
                  AND m.timestamp < se.start_time  -- Meal precedes symptom
                  AND m.timestamp >= se.start_time - INTERVAL '7 days'
                  AND m.status = 'published'
                  AND m.timestamp >= :date_range_start
                  AND m.timestamp <= :date_range_end
            ),
            temporal_correlations AS (
                SELECT
                    ingredient_id,
                    ingredient_name,
                    ingredient_state,
                    symptom_name,
                    COUNT(DISTINCT CASE WHEN lag_hours BETWEEN :immediate_min AND :immediate_max THEN symptom_id END) as immediate_count,
                    COUNT(DISTINCT CASE WHEN lag_hours BETWEEN :delayed_min AND :delayed_max THEN symptom_id END) as delayed_count,
                    COUNT(DISTINCT CASE WHEN lag_hours > :cumulative_min AND lag_hours <= :cumulative_max THEN symptom_id END) as cumulative_count,
                    COUNT(DISTINCT symptom_id) as symptom_occurrences,
                    AVG(symptom_severity) as avg_severity,
                    AVG(lag_hours) as avg_lag_hours
                FROM ingredient_exposures
                GROUP BY ingredient_id, ingredient_name, ingredient_state, symptom_name
            ),
            ingredient_consumption AS (
                -- Count total times each ingredient was eaten
                SELECT
                    i.id as ingredient_id,
                    mi.state as ingredient_state,
                    COUNT(DISTINCT m.id) as times_eaten
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                JOIN ingredients i ON mi.ingredient_id = i.id
                WHERE m.user_id = :user_id
                  AND m.status = 'published'
                  AND m.timestamp >= :date_range_start
                  AND m.timestamp <= :date_range_end
                GROUP BY i.id, mi.state
            )
            SELECT
                tc.ingredient_id,
                tc.ingredient_name,
                tc.ingredient_state,
                tc.symptom_name,
                tc.immediate_count,
                tc.delayed_count,
                tc.cumulative_count,
                tc.symptom_occurrences,
                tc.avg_severity,
                tc.avg_lag_hours,
                ic.times_eaten
            FROM temporal_correlations tc
            JOIN ingredient_consumption ic
                ON tc.ingredient_id = ic.ingredient_id
                AND tc.ingredient_state = ic.ingredient_state
            WHERE tc.symptom_occurrences >= :min_symptom_occurrences
            ORDER BY tc.symptom_occurrences DESC, tc.avg_severity DESC
            """
        )

        params = {
            "user_id": str(user_id),
            "date_range_start": date_range_start,
            "date_range_end": date_range_end,
            "immediate_min": self.IMMEDIATE_LAG_MIN,
            "immediate_max": self.IMMEDIATE_LAG_MAX,
            "delayed_min": self.DELAYED_LAG_MIN,
            "delayed_max": self.DELAYED_LAG_MAX,
            "cumulative_min": self.CUMULATIVE_LAG_MIN,
            "cumulative_max": self.CUMULATIVE_LAG_MAX,
            "min_symptom_occurrences": self.MIN_SYMPTOM_OCCURRENCES,
        }

        print(f"DEBUG get_temporal_correlations params: {params}")

        result = self.db.execute(query, params)

        return [
            {
                "ingredient_id": row[0],
                "ingredient_name": row[1],
                "ingredient_state": row[2],
                "symptom_name": row[3],
                "immediate_count": row[4],
                "delayed_count": row[5],
                "cumulative_count": row[6],
                "symptom_occurrences": row[7],
                "avg_severity": float(row[8]) if row[8] else 0.0,
                "avg_lag_hours": float(row[9]) if row[9] else 0.0,
                "times_eaten": row[10],
            }
            for row in result
        ]

    def get_symptom_clusters(
        self, user_id: str, date_range_start: datetime, date_range_end: datetime
    ) -> List[Dict]:
        """
        Detect co-occurring symptoms within clustering window.

        Finds symptoms that occur within CLUSTERING_WINDOW hours of each other,
        which may indicate multi-symptom patterns triggered by the same ingredient.

        Returns:
            List of dicts with symptom cluster data.
        """
        query = text(
            """
            WITH symptom_tags AS (
                SELECT
                    s.id as symptom_id,
                    s.user_id,
                    s.start_time,
                    jsonb_array_elements(s.tags) as tag
                FROM symptoms s
                WHERE s.user_id = :user_id
                  AND s.tags IS NOT NULL
                  AND s.start_time >= :date_range_start
                  AND s.start_time <= :date_range_end
            ),
            symptom_clusters AS (
                SELECT
                    s1.symptom_id as symptom1_id,
                    s2.symptom_id as symptom2_id,
                    LOWER(s1.tag->>'name') as symptom1_name,
                    LOWER(s2.tag->>'name') as symptom2_name,
                    ABS(EXTRACT(EPOCH FROM (s1.start_time - s2.start_time))/3600) as time_diff_hours
                FROM symptom_tags s1
                JOIN symptom_tags s2
                    ON s1.user_id = s2.user_id
                    AND s1.symptom_id < s2.symptom_id
                WHERE ABS(EXTRACT(EPOCH FROM (s1.start_time - s2.start_time))/3600) <= :clustering_window
            )
            SELECT
                symptom1_name,
                symptom2_name,
                COUNT(*) as co_occurrence_count,
                AVG(time_diff_hours) as avg_time_diff
            FROM symptom_clusters
            GROUP BY symptom1_name, symptom2_name
            HAVING COUNT(*) >= 2
            ORDER BY co_occurrence_count DESC
            """
        )

        result = self.db.execute(
            query,
            {
                "user_id": str(user_id),
                "date_range_start": date_range_start,
                "date_range_end": date_range_end,
                "clustering_window": self.CLUSTERING_WINDOW,
            },
        )

        return [
            {
                "symptom1_name": row[0],
                "symptom2_name": row[1],
                "co_occurrence_count": row[2],
                "avg_time_diff": float(row[3]) if row[3] else 0.0,
            }
            for row in result
        ]

    def get_ingredient_cooccurrence(
        self, user_id: str, date_range_start: datetime, date_range_end: datetime
    ) -> List[Dict]:
        """
        Calculate co-occurrence statistics for ingredient pairs.

        Computes:
        - Conditional probability P(B|A): How often B appears given A
        - Lift: P(B|A) / P(B) - how much more likely B is given A vs baseline

        Flags pairs with high co-occurrence (P > 0.8 OR lift > 3.0) as potential confounders.

        Returns:
            List of dicts with co-occurrence data for ingredient pairs.
        """
        query = text(
            """
            WITH ingredient_meals AS (
                -- Get all (meal_id, ingredient_id) pairs
                SELECT DISTINCT
                    m.id as meal_id,
                    i.id as ingredient_id,
                    i.normalized_name as ingredient_name
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                JOIN ingredients i ON mi.ingredient_id = i.id
                WHERE m.user_id = :user_id
                  AND m.status = 'published'
                  AND m.timestamp >= :date_range_start
                  AND m.timestamp <= :date_range_end
            ),
            ingredient_totals AS (
                -- Count total meals each ingredient appears in
                SELECT
                    ingredient_id,
                    ingredient_name,
                    COUNT(DISTINCT meal_id) as total_meals
                FROM ingredient_meals
                GROUP BY ingredient_id, ingredient_name
            ),
            total_meals_count AS (
                -- Total meals in period
                SELECT COUNT(DISTINCT meal_id) as total FROM ingredient_meals
            ),
            cooccurrence AS (
                -- Count meals where both ingredients appear
                SELECT
                    a.ingredient_id as ingredient_a_id,
                    a.ingredient_name as ingredient_a_name,
                    b.ingredient_id as ingredient_b_id,
                    b.ingredient_name as ingredient_b_name,
                    COUNT(DISTINCT a.meal_id) as both_count
                FROM ingredient_meals a
                JOIN ingredient_meals b
                    ON a.meal_id = b.meal_id
                    AND a.ingredient_id < b.ingredient_id  -- Avoid duplicates & self-pairs
                GROUP BY a.ingredient_id, a.ingredient_name, b.ingredient_id, b.ingredient_name
            )
            SELECT
                c.ingredient_a_id,
                c.ingredient_a_name,
                c.ingredient_b_id,
                c.ingredient_b_name,
                c.both_count,
                ta.total_meals as a_total_meals,
                tb.total_meals as b_total_meals,
                tm.total as total_meals,
                -- P(B|A) = P(A and B) / P(A)
                CASE WHEN ta.total_meals > 0
                    THEN c.both_count::float / ta.total_meals
                    ELSE 0
                END as p_b_given_a,
                -- P(A|B) = P(A and B) / P(B)
                CASE WHEN tb.total_meals > 0
                    THEN c.both_count::float / tb.total_meals
                    ELSE 0
                END as p_a_given_b,
                -- Lift(A->B) = P(B|A) / P(B) = P(A,B) * N / (P(A) * P(B))
                CASE WHEN ta.total_meals > 0 AND tb.total_meals > 0
                    THEN (c.both_count::float * tm.total) / (ta.total_meals * tb.total_meals::float)
                    ELSE 0
                END as lift
            FROM cooccurrence c
            JOIN ingredient_totals ta ON c.ingredient_a_id = ta.ingredient_id
            JOIN ingredient_totals tb ON c.ingredient_b_id = tb.ingredient_id
            CROSS JOIN total_meals_count tm
            WHERE c.both_count >= 2  -- Minimum co-occurrence threshold
            ORDER BY lift DESC, c.both_count DESC
            """
        )

        result = self.db.execute(
            query,
            {
                "user_id": str(user_id),
                "date_range_start": date_range_start,
                "date_range_end": date_range_end,
            },
        )

        cooccurrence_data = []
        for row in result:
            p_b_given_a = float(row[8]) if row[8] else 0.0
            p_a_given_b = float(row[9]) if row[9] else 0.0
            lift = float(row[10]) if row[10] else 0.0

            cooccurrence_data.append({
                "ingredient_a_id": row[0],
                "ingredient_a_name": row[1],
                "ingredient_b_id": row[2],
                "ingredient_b_name": row[3],
                "both_count": row[4],
                "a_total_meals": row[5],
                "b_total_meals": row[6],
                "total_meals": row[7],
                "p_b_given_a": p_b_given_a,
                "p_a_given_b": p_a_given_b,
                "lift": lift,
                # Flag high co-occurrence pairs as potential confounders
                "is_high_cooccurrence": p_b_given_a > 0.8 or p_a_given_b > 0.8 or lift > 3.0,
            })

        print(f"DEBUG get_ingredient_cooccurrence: Found {len(cooccurrence_data)} pairs, "
              f"{sum(1 for c in cooccurrence_data if c['is_high_cooccurrence'])} high co-occurrence")

        return cooccurrence_data

    def get_cooccurrence_for_ingredient(
        self, ingredient_id: int, cooccurrence_data: List[Dict]
    ) -> List[Dict]:
        """
        Get all high co-occurrence pairs involving a specific ingredient.

        Args:
            ingredient_id: The ingredient to find confounders for
            cooccurrence_data: Full co-occurrence data from get_ingredient_cooccurrence()

        Returns:
            List of co-occurrence records where ingredient appears, sorted by lift descending
        """
        relevant = []
        for pair in cooccurrence_data:
            if not pair["is_high_cooccurrence"]:
                continue
            if pair["ingredient_a_id"] == ingredient_id:
                relevant.append({
                    "with_ingredient_id": pair["ingredient_b_id"],
                    "with_ingredient_name": pair["ingredient_b_name"],
                    "conditional_probability": pair["p_b_given_a"],
                    "reverse_probability": pair["p_a_given_b"],
                    "lift": pair["lift"],
                    "cooccurrence_meals": pair["both_count"],
                })
            elif pair["ingredient_b_id"] == ingredient_id:
                relevant.append({
                    "with_ingredient_id": pair["ingredient_a_id"],
                    "with_ingredient_name": pair["ingredient_a_name"],
                    "conditional_probability": pair["p_a_given_b"],
                    "reverse_probability": pair["p_b_given_a"],
                    "lift": pair["lift"],
                    "cooccurrence_meals": pair["both_count"],
                })

        # Sort by lift descending
        relevant.sort(key=lambda x: x["lift"], reverse=True)
        return relevant

    def get_holistic_ingredient_data(
        self, user_id: str, ingredient_id: int
    ) -> Optional[Dict]:
        """
        Get holistic analysis data for a single ingredient.

        This method gathers ALL available data for an ingredient (windowed by
        max occurrences) to enable a comprehensive, one-time classification.

        The co-occurrence data provides the "bridge" to other ingredients,
        showing which foods this ingredient typically appears with.

        Args:
            user_id: User ID
            ingredient_id: The ingredient to analyze

        Returns:
            Dict with correlation and co-occurrence data, or None if insufficient data
        """
        max_occurrences = settings.diagnosis_max_ingredient_occurrences

        # Step 1: Get the most recent N meal occurrences for this ingredient
        # This windows the data to avoid unbounded analysis
        query = text(
            """
            WITH recent_meals AS (
                -- Get the N most recent meals containing this ingredient
                SELECT m.id as meal_id, m.timestamp, mi.state as ingredient_state,
                       ROW_NUMBER() OVER (ORDER BY m.timestamp DESC) as rn
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                WHERE m.user_id = :user_id
                  AND mi.ingredient_id = :ingredient_id
                  AND m.status = 'published'
            ),
            windowed_meals AS (
                SELECT meal_id, timestamp, ingredient_state
                FROM recent_meals
                WHERE rn <= :max_occurrences
            ),
            symptom_episodes AS (
                -- Get all symptoms for this user
                SELECT
                    s.id as symptom_id,
                    s.start_time,
                    jsonb_array_elements(s.tags) as tag
                FROM symptoms s
                WHERE s.user_id = :user_id
                  AND s.tags IS NOT NULL
            ),
            ingredient_exposures AS (
                -- Cross-join windowed meals with symptoms, calculate lag
                SELECT
                    wm.meal_id,
                    wm.timestamp as meal_timestamp,
                    wm.ingredient_state,
                    se.symptom_id,
                    se.tag->>'name' as symptom_name,
                    COALESCE((se.tag->>'severity')::numeric, 0) as symptom_severity,
                    EXTRACT(EPOCH FROM (se.start_time - wm.timestamp))/3600 as lag_hours
                FROM windowed_meals wm
                CROSS JOIN symptom_episodes se
                WHERE wm.timestamp < se.start_time
                  AND wm.timestamp >= se.start_time - INTERVAL '7 days'
            ),
            correlation_stats AS (
                SELECT
                    symptom_name,
                    COUNT(DISTINCT CASE WHEN lag_hours BETWEEN :immediate_min AND :immediate_max THEN symptom_id END) as immediate_count,
                    COUNT(DISTINCT CASE WHEN lag_hours BETWEEN :delayed_min AND :delayed_max THEN symptom_id END) as delayed_count,
                    COUNT(DISTINCT CASE WHEN lag_hours > :cumulative_min AND lag_hours <= :cumulative_max THEN symptom_id END) as cumulative_count,
                    COUNT(DISTINCT symptom_id) as symptom_occurrences,
                    AVG(symptom_severity) as avg_severity,
                    AVG(lag_hours) as avg_lag_hours
                FROM ingredient_exposures
                GROUP BY symptom_name
            )
            SELECT
                (SELECT COUNT(DISTINCT meal_id) FROM windowed_meals) as times_eaten,
                (SELECT ingredient_state FROM windowed_meals LIMIT 1) as ingredient_state,
                cs.symptom_name,
                cs.immediate_count,
                cs.delayed_count,
                cs.cumulative_count,
                cs.symptom_occurrences,
                cs.avg_severity,
                cs.avg_lag_hours
            FROM correlation_stats cs
            WHERE cs.symptom_occurrences >= 1
            ORDER BY cs.symptom_occurrences DESC
            """
        )

        params = {
            "user_id": str(user_id),
            "ingredient_id": ingredient_id,
            "max_occurrences": max_occurrences,
            "immediate_min": self.IMMEDIATE_LAG_MIN,
            "immediate_max": self.IMMEDIATE_LAG_MAX,
            "delayed_min": self.DELAYED_LAG_MIN,
            "delayed_max": self.DELAYED_LAG_MAX,
            "cumulative_min": self.CUMULATIVE_LAG_MIN,
            "cumulative_max": self.CUMULATIVE_LAG_MAX,
        }

        result = list(self.db.execute(query, params))

        if not result:
            return None

        # Get ingredient name
        ingredient = self.db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
        if not ingredient:
            return None

        times_eaten = result[0][0]
        ingredient_state = result[0][1]

        # Aggregate symptoms
        associated_symptoms = []
        total_symptom_occurrences = 0
        immediate_total = 0
        delayed_total = 0
        cumulative_total = 0

        for row in result:
            symptom_name = row[2]
            immediate = row[3] or 0
            delayed = row[4] or 0
            cumulative = row[5] or 0
            occurrences = row[6] or 0
            severity = float(row[7]) if row[7] else 0.0
            lag = float(row[8]) if row[8] else 0.0

            associated_symptoms.append({
                "name": symptom_name,
                "frequency": occurrences,
                "severity_avg": severity,
                "lag_hours": lag,
            })

            total_symptom_occurrences += occurrences
            immediate_total += immediate
            delayed_total += delayed
            cumulative_total += cumulative

        # Calculate confidence score
        confidence_score, confidence_level = self.calculate_confidence(
            times_eaten=times_eaten,
            associated_symptoms=associated_symptoms,
            immediate_count=immediate_total,
            delayed_count=delayed_total,
            cumulative_count=cumulative_total,
        )

        # Step 2: Get co-occurrence data for this ingredient
        cooccurrence_data = self._get_holistic_cooccurrence(user_id, ingredient_id, max_occurrences)

        return {
            "ingredient_id": ingredient_id,
            "ingredient_name": ingredient.normalized_name,
            "state": ingredient_state,
            "times_eaten": times_eaten,
            "total_symptom_occurrences": total_symptom_occurrences,
            "immediate_total": immediate_total,
            "delayed_total": delayed_total,
            "cumulative_total": cumulative_total,
            "associated_symptoms": associated_symptoms,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level,
            "cooccurrence": cooccurrence_data,
        }

    def _get_holistic_cooccurrence(
        self, user_id: str, ingredient_id: int, max_occurrences: int
    ) -> List[Dict]:
        """
        Get co-occurrence data for an ingredient using windowed meals.

        Returns list of ingredients that frequently co-occur with the target,
        along with conditional probabilities.
        """
        query = text(
            """
            WITH recent_meals AS (
                -- Get the N most recent meals containing the target ingredient
                SELECT m.id as meal_id, m.timestamp,
                       ROW_NUMBER() OVER (ORDER BY m.timestamp DESC) as rn
                FROM meals m
                JOIN meal_ingredients mi ON m.id = mi.meal_id
                WHERE m.user_id = :user_id
                  AND mi.ingredient_id = :ingredient_id
                  AND m.status = 'published'
            ),
            windowed_meals AS (
                SELECT meal_id FROM recent_meals WHERE rn <= :max_occurrences
            ),
            target_meal_count AS (
                SELECT COUNT(*) as total FROM windowed_meals
            ),
            cooccurring_ingredients AS (
                -- Find all ingredients in those meals (except the target)
                SELECT
                    i.id as other_ingredient_id,
                    i.normalized_name as other_ingredient_name,
                    COUNT(DISTINCT wm.meal_id) as cooccur_count
                FROM windowed_meals wm
                JOIN meal_ingredients mi ON wm.meal_id = mi.meal_id
                JOIN ingredients i ON mi.ingredient_id = i.id
                WHERE mi.ingredient_id != :ingredient_id
                GROUP BY i.id, i.normalized_name
            )
            SELECT
                ci.other_ingredient_id,
                ci.other_ingredient_name,
                ci.cooccur_count,
                tmc.total as target_meals,
                ROUND(ci.cooccur_count::numeric / NULLIF(tmc.total, 0), 3) as conditional_prob
            FROM cooccurring_ingredients ci
            CROSS JOIN target_meal_count tmc
            WHERE ci.cooccur_count >= 2
            ORDER BY conditional_prob DESC, ci.cooccur_count DESC
            LIMIT 10
            """
        )

        result = self.db.execute(
            query,
            {
                "user_id": str(user_id),
                "ingredient_id": ingredient_id,
                "max_occurrences": max_occurrences,
            }
        )

        cooccurrence_data = []
        for row in result:
            prob = float(row[4]) if row[4] else 0.0
            cooccurrence_data.append({
                "with_ingredient_id": row[0],
                "with_ingredient_name": row[1],
                "cooccurrence_meals": row[2],
                "conditional_probability": prob,
                # Flag high co-occurrence for classification
                "is_high_cooccurrence": prob > 0.5,
            })

        return cooccurrence_data

    def aggregate_correlations_by_ingredient(
        self, correlations: List[Dict]
    ) -> Dict[int, Dict]:
        """
        Aggregate correlation data by ingredient, combining all associated symptoms.

        Takes raw temporal correlation data and groups by ingredient_id + state,
        creating a comprehensive view of all symptoms associated with each ingredient.

        Args:
            correlations: Raw temporal correlation data from get_temporal_correlations()

        Returns:
            Dict mapping ingredient_id to aggregated data including all symptoms
        """
        print(f"DEBUG aggregate_correlations_by_ingredient: Processing {len(correlations)} correlations")
        aggregated = {}

        for idx, corr in enumerate(correlations):
            print(f"DEBUG Correlation {idx}: ingredient={corr['ingredient_name']}, state={corr['ingredient_state']}, times_eaten={corr['times_eaten']}, symptom_occurrences={corr['symptom_occurrences']}")
            ingredient_id = corr["ingredient_id"]
            state = corr["ingredient_state"]
            key = (ingredient_id, state)

            if key not in aggregated:
                aggregated[key] = {
                    "ingredient_id": ingredient_id,
                    "ingredient_name": corr["ingredient_name"],
                    "state": state,
                    "times_eaten": corr["times_eaten"],
                    "total_symptom_occurrences": 0,
                    "immediate_total": 0,
                    "delayed_total": 0,
                    "cumulative_total": 0,
                    "associated_symptoms": [],
                }

            aggregated[key]["total_symptom_occurrences"] += corr["symptom_occurrences"]
            aggregated[key]["immediate_total"] += corr["immediate_count"]
            aggregated[key]["delayed_total"] += corr["delayed_count"]
            aggregated[key]["cumulative_total"] += corr["cumulative_count"]

            aggregated[key]["associated_symptoms"].append(
                {
                    "name": corr["symptom_name"],
                    "severity_avg": corr["avg_severity"],
                    "frequency": corr["symptom_occurrences"],
                    "lag_hours": corr["avg_lag_hours"],
                }
            )

        print(f"DEBUG aggregate_correlations_by_ingredient OUTPUT: {len(aggregated)} unique ingredients")
        for key, agg in aggregated.items():
            print(f"  {agg['ingredient_name']} ({agg['state']}): times_eaten={agg['times_eaten']}, total_symptom_occurrences={agg['total_symptom_occurrences']}")

        return aggregated

    def calculate_confidence(
        self,
        times_eaten: int,
        associated_symptoms: List[Dict],
        immediate_count: int,
        delayed_count: int,
        cumulative_count: int,
    ) -> Tuple[float, str]:
        """
        Calculate confidence score and level for ingredient-symptom correlation.

        Uses per-symptom normalization to prevent scores >100%:
        - Each symptom type's correlation rate is capped at 1.0
        - Rates are aggregated as severity-weighted average across symptom types

        The final score combines:
        - Statistical confidence (50%): severity-weighted avg of per-symptom rates
        - Temporal specificity (30%): preference for concentrated temporal patterns
        - Severity weighting (20%): higher severity increases confidence

        Args:
            times_eaten: Total times ingredient was consumed
            associated_symptoms: List of symptom dicts with 'name', 'frequency', 'severity_avg'
            immediate_count: Symptoms in 0-2hr window
            delayed_count: Symptoms in 4-24hr window
            cumulative_count: Symptoms in 24hr+ window

        Returns:
            Tuple of (confidence_score, confidence_level)
            - confidence_score: 0.000-1.000
            - confidence_level: 'high', 'medium', 'low', or 'insufficient_data'
        """
        # Calculate total symptom occurrences for threshold check
        total_symptom_occurrences = sum(s.get("frequency", 0) for s in associated_symptoms)

        print(f"DEBUG calculate_confidence INPUT:")
        print(f"  times_eaten: {times_eaten}, MIN_MEALS: {self.MIN_MEALS}")
        print(f"  total_symptom_occurrences: {total_symptom_occurrences}, MIN_SYMPTOM_OCCURRENCES: {self.MIN_SYMPTOM_OCCURRENCES}")
        print(f"  associated_symptoms: {associated_symptoms}")
        print(f"  immediate: {immediate_count}, delayed: {delayed_count}, cumulative: {cumulative_count}")

        # Minimum thresholds
        if times_eaten < self.MIN_MEALS or total_symptom_occurrences < self.MIN_SYMPTOM_OCCURRENCES:
            return (0.0, "insufficient_data")

        # 1. Statistical confidence (50% weight)
        # Calculate per-symptom correlation rate, capped at 1.0, then aggregate
        if associated_symptoms:
            total_severity_weight = 0.0
            weighted_correlation_sum = 0.0

            for symptom in associated_symptoms:
                frequency = symptom.get("frequency", 0)
                severity = symptom.get("severity_avg", 1.0)

                # Per-symptom correlation rate, capped at 1.0
                symptom_rate = min(1.0, frequency / times_eaten)

                # Weight by severity (higher severity symptoms contribute more)
                severity_weight = max(0.1, severity)  # Minimum weight of 0.1
                weighted_correlation_sum += symptom_rate * severity_weight
                total_severity_weight += severity_weight

            # Severity-weighted average correlation rate
            if total_severity_weight > 0:
                correlation_strength = weighted_correlation_sum / total_severity_weight
            else:
                correlation_strength = 0.0
        else:
            correlation_strength = 0.0

        # Apply square root penalty to account for small sample size
        data_penalty = min(1.0, (times_eaten / 10) ** 0.5)
        statistical_conf = correlation_strength * data_penalty

        # 2. Temporal specificity (30% weight)
        # Higher if symptoms concentrate in one temporal window
        total_temporal = immediate_count + delayed_count + cumulative_count
        if total_temporal > 0:
            max_window = max(immediate_count, delayed_count, cumulative_count)
            temporal_specificity = max_window / total_temporal
        else:
            temporal_specificity = 0.0

        # 3. Severity weighting (20% weight)
        # Use average severity across all symptoms
        if associated_symptoms:
            avg_severity = sum(s.get("severity_avg", 0) for s in associated_symptoms) / len(associated_symptoms)
        else:
            avg_severity = 0.0
        severity_component = min(avg_severity / 10, 1.0)

        # Combined score (always 0.0-1.0)
        confidence = (
            0.5 * statistical_conf + 0.3 * temporal_specificity + 0.2 * severity_component
        )
        confidence = min(1.0, max(0.0, confidence))  # Safety clamp

        # Classify confidence level
        if confidence >= 0.7:
            level = "high"
        elif confidence >= 0.4:
            level = "medium"
        else:
            level = "low"

        print(f"DEBUG calculate_confidence OUTPUT:")
        print(f"  correlation_strength: {correlation_strength}, statistical_conf: {statistical_conf}")
        print(f"  temporal_specificity: {temporal_specificity}, severity_component: {severity_component}")
        print(f"  final confidence: {round(confidence, 3)}, level: {level}")

        return (round(confidence, 3), level)

    async def run_diagnosis(
        self,
        user_id: str,
        date_range_start: datetime,
        date_range_end: datetime,
        web_search_enabled: bool = True
    ) -> DiagnosisRun:
        """
        Run complete diagnosis analysis and store results in database.

        Orchestrates the entire diagnosis flow:
        1. Check data sufficiency
        2. Run temporal windowing queries
        3. Run symptom clustering analysis
        4. Aggregate correlations by ingredient
        5. Calculate confidence scores
        6. Call Claude API for medical grounding
        7. Store results and citations in database

        Args:
            user_id: User ID to run diagnosis for
            date_range_start: Start of analysis date range
            date_range_end: End of analysis date range
            web_search_enabled: Whether to enable Claude web search

        Returns:
            DiagnosisRun object with all results populated

        Raises:
            ValueError: If insufficient data for analysis
        """
        from app.services.ai_service import ClaudeService

        print(f"DEBUG run_diagnosis: date_range_start={date_range_start}, date_range_end={date_range_end}")

        # Step 1: Check data sufficiency
        sufficient_data, meals_count, symptoms_count = self.check_data_sufficiency(
            user_id, date_range_start, date_range_end
        )

        # Create diagnosis run record
        diagnosis_run = DiagnosisRun(
            user_id=user_id,
            run_timestamp=datetime.utcnow(),
            meals_analyzed=meals_count,
            symptoms_analyzed=symptoms_count,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            sufficient_data=sufficient_data,
            web_search_enabled=web_search_enabled,
        )
        self.db.add(diagnosis_run)
        self.db.flush()  # Get ID before continuing

        if not sufficient_data:
            self.db.commit()
            return diagnosis_run

        # Step 2: Run temporal windowing analysis
        correlations = self.get_temporal_correlations(
            user_id, date_range_start, date_range_end
        )

        if not correlations:
            # No correlations found, mark as complete
            self.db.commit()
            return diagnosis_run

        # Step 3: Run symptom clustering
        clusters = self.get_symptom_clusters(
            user_id, date_range_start, date_range_end
        )

        # Step 4: Aggregate correlations by ingredient
        aggregated = self.aggregate_correlations_by_ingredient(correlations)

        # Step 5: Calculate confidence scores
        scored_ingredients = []
        for key, data in aggregated.items():
            confidence_score, confidence_level = self.calculate_confidence(
                times_eaten=data["times_eaten"],
                associated_symptoms=data["associated_symptoms"],
                immediate_count=data["immediate_total"],
                delayed_count=data["delayed_total"],
                cumulative_count=data["cumulative_total"],
            )

            if confidence_level != "insufficient_data":
                scored_ingredients.append(
                    {
                        **data,
                        "confidence_score": confidence_score,
                        "confidence_level": confidence_level,
                    }
                )

        # Sort by confidence score descending
        scored_ingredients.sort(key=lambda x: x["confidence_score"], reverse=True)

        # If no ingredients met confidence threshold, skip Claude API call
        if not scored_ingredients:
            self.db.commit()
            return diagnosis_run

        # Step 5b: Run co-occurrence analysis
        cooccurrence_data = self.get_ingredient_cooccurrence(
            user_id, date_range_start, date_range_end
        )

        # Step 5c: Root-cause classification for ingredients with high co-occurrence
        # This step identifies confounders and separates them from true triggers
        claude_service = ClaudeService()
        confirmed_ingredients = []
        discounted_ingredients = []

        for ingredient in scored_ingredients:
            ingredient_id = ingredient["ingredient_id"]

            # Get co-occurrence data for this ingredient
            ingredient_cooccurrence = self.get_cooccurrence_for_ingredient(
                ingredient_id, cooccurrence_data
            )

            # If no high co-occurrence, keep as root cause by default
            if not ingredient_cooccurrence:
                confirmed_ingredients.append(ingredient)
                continue

            # Call Claude to classify root cause vs confounder
            try:
                classification = await claude_service.classify_root_cause(
                    ingredient_data=ingredient,
                    cooccurrence_data=ingredient_cooccurrence,
                    medical_grounding="",  # Will be fetched via web search
                    web_search_enabled=web_search_enabled
                )

                if classification.get("root_cause", True):
                    # Confirmed as root cause
                    confirmed_ingredients.append(ingredient)
                else:
                    # Discarded as confounder
                    # Find confounded_by ingredient ID
                    confounded_by_name = classification.get("confounded_by")
                    confounded_by_id = None
                    if confounded_by_name:
                        for cooc in ingredient_cooccurrence:
                            if cooc["with_ingredient_name"].lower() == confounded_by_name.lower():
                                confounded_by_id = cooc["with_ingredient_id"]
                                break

                    discounted_ingredients.append({
                        **ingredient,
                        "discard_justification": classification.get("discard_justification", ""),
                        "confounded_by_id": confounded_by_id,
                        "confounded_by_name": confounded_by_name,
                        "medical_grounding": classification.get("medical_reasoning", ""),
                        "cooccurrence": ingredient_cooccurrence[0] if ingredient_cooccurrence else None,
                    })
            except Exception as e:
                # On error, keep ingredient (err on side of showing triggers)
                print(f"Root cause classification error for {ingredient['ingredient_name']}: {e}")
                confirmed_ingredients.append(ingredient)

        # Update scored_ingredients to only confirmed ones
        scored_ingredients = confirmed_ingredients

        # If all ingredients were discounted, still show as results
        if not scored_ingredients and not discounted_ingredients:
            self.db.commit()
            return diagnosis_run

        # Step 6: Call Claude API for medical grounding (only for confirmed ingredients)
        if scored_ingredients:
            ai_analysis = await claude_service.diagnose_correlations(
                scored_ingredients, web_search_enabled=web_search_enabled
            )
        else:
            ai_analysis = {"ingredient_analyses": [], "usage_stats": {"input_tokens": 0, "cached_tokens": 0, "cache_hit": False}}

        # Update diagnosis run with Claude API stats
        diagnosis_run.claude_model = claude_service.sonnet_model
        diagnosis_run.input_tokens = ai_analysis["usage_stats"]["input_tokens"]
        diagnosis_run.cached_tokens = ai_analysis["usage_stats"]["cached_tokens"]
        diagnosis_run.cache_hit = ai_analysis["usage_stats"]["cache_hit"]

        # Step 7: Store results and citations in database
        for analysis in ai_analysis.get("ingredient_analyses", []):
            ingredient_name = analysis["ingredient_name"]

            # Find matching scored ingredient (flexible matching for "raw onion" vs "onion")
            matching = next(
                (
                    ing
                    for ing in scored_ingredients
                    if ing["ingredient_name"].lower() in ingredient_name.lower()
                    or ingredient_name.lower() in ing["ingredient_name"].lower()
                ),
                None,
            )

            if not matching:
                continue

            # Create diagnosis result
            result = DiagnosisResult(
                run_id=diagnosis_run.id,
                ingredient_id=matching["ingredient_id"],
                confidence_score=matching["confidence_score"],
                confidence_level=matching["confidence_level"],
                immediate_correlation=matching["immediate_total"],
                delayed_correlation=matching["delayed_total"],
                cumulative_correlation=matching["cumulative_total"],
                times_eaten=matching["times_eaten"],
                times_followed_by_symptoms=matching["total_symptom_occurrences"],
                state_matters=False,  # TODO: implement state significance testing
                problematic_states=[matching["state"]] if matching.get("state") else None,
                associated_symptoms=matching["associated_symptoms"],
                ai_analysis=analysis.get("medical_context", "")
                + "\n\nInterpretation: "
                + analysis.get("interpretation", "")
                + "\n\nRecommendations: "
                + analysis.get("recommendations", ""),
            )
            self.db.add(result)
            self.db.flush()  # Get result ID for citations

            # Create citations
            for citation in analysis.get("citations", []):
                citation_obj = DiagnosisCitation(
                    result_id=result.id,
                    source_url=citation.get("url", ""),
                    source_title=citation.get("title", ""),
                    source_type=citation.get("source_type", "other"),
                    snippet=citation.get("snippet", ""),
                    relevance_score=citation.get("relevance", 0.0),
                )
                self.db.add(citation_obj)

        # Step 8: Store discounted (confounded) ingredients
        for discounted in discounted_ingredients:
            cooc = discounted.get("cooccurrence", {})
            discounted_obj = DiscountedIngredient(
                run_id=diagnosis_run.id,
                ingredient_id=discounted["ingredient_id"],
                discard_justification=discounted.get("discard_justification", "Confounded by co-occurring ingredient"),
                confounded_by_ingredient_id=discounted.get("confounded_by_id"),
                # Original correlation data
                original_confidence_score=discounted.get("confidence_score"),
                original_confidence_level=discounted.get("confidence_level"),
                times_eaten=discounted.get("times_eaten"),
                times_followed_by_symptoms=discounted.get("total_symptom_occurrences"),
                immediate_correlation=discounted.get("immediate_total"),
                delayed_correlation=discounted.get("delayed_total"),
                cumulative_correlation=discounted.get("cumulative_total"),
                associated_symptoms=discounted.get("associated_symptoms"),
                # Co-occurrence data
                conditional_probability=cooc.get("conditional_probability") if cooc else None,
                reverse_probability=cooc.get("reverse_probability") if cooc else None,
                lift=cooc.get("lift") if cooc else None,
                cooccurrence_meals_count=cooc.get("cooccurrence_meals") if cooc else None,
                # Medical grounding
                medical_grounding_summary=discounted.get("medical_grounding"),
            )
            self.db.add(discounted_obj)

        # Commit all changes
        self.db.commit()
        self.db.refresh(diagnosis_run)

        return diagnosis_run
