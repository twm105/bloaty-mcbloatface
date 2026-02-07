"""Diagnosis service for analyzing ingredient-symptom correlations."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text, and_, func
from sqlalchemy.orm import Session

from app.models import (
    DiagnosisRun,
    DiagnosisResult,
    DiagnosisCitation,
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
        symptom_occurrences: int,
        immediate_count: int,
        delayed_count: int,
        cumulative_count: int,
        avg_severity: float,
    ) -> Tuple[float, str]:
        """
        Calculate confidence score and level for ingredient-symptom correlation.

        Uses a weighted formula combining:
        - Statistical confidence (50%): correlation strength with data volume penalty
        - Temporal specificity (30%): preference for concentrated temporal patterns
        - Severity weighting (20%): higher severity increases confidence

        Args:
            times_eaten: Total times ingredient was consumed
            symptom_occurrences: Number of times symptoms followed consumption
            immediate_count: Symptoms in 0-2hr window
            delayed_count: Symptoms in 4-24hr window
            cumulative_count: Symptoms in 24hr+ window
            avg_severity: Average severity rating of symptoms (0-10 scale)

        Returns:
            Tuple of (confidence_score, confidence_level)
            - confidence_score: 0.000-1.000
            - confidence_level: 'high', 'medium', 'low', or 'insufficient_data'
        """
        print(f"DEBUG calculate_confidence INPUT:")
        print(f"  times_eaten: {times_eaten}, MIN_MEALS: {self.MIN_MEALS}")
        print(f"  symptom_occurrences: {symptom_occurrences}, MIN_SYMPTOM_OCCURRENCES: {self.MIN_SYMPTOM_OCCURRENCES}")
        print(f"  immediate: {immediate_count}, delayed: {delayed_count}, cumulative: {cumulative_count}")
        print(f"  avg_severity: {avg_severity}")

        # Minimum thresholds
        if times_eaten < self.MIN_MEALS or symptom_occurrences < self.MIN_SYMPTOM_OCCURRENCES:
            return (0.0, "insufficient_data")

        # 1. Statistical confidence (50% weight)
        correlation_strength = symptom_occurrences / times_eaten
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
        # Normalize avg_severity to 0-1 scale (assuming 0-10 input scale)
        severity_weight = min(avg_severity / 10, 1.0)

        # Combined score
        confidence = (
            0.5 * statistical_conf + 0.3 * temporal_specificity + 0.2 * severity_weight
        )

        # Classify confidence level
        if confidence >= 0.7:
            level = "high"
        elif confidence >= 0.4:
            level = "medium"
        else:
            level = "low"

        print(f"DEBUG calculate_confidence OUTPUT:")
        print(f"  statistical_conf: {statistical_conf}, temporal_specificity: {temporal_specificity}, severity_weight: {severity_weight}")
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
                symptom_occurrences=data["total_symptom_occurrences"],
                immediate_count=data["immediate_total"],
                delayed_count=data["delayed_total"],
                cumulative_count=data["cumulative_total"],
                avg_severity=sum(s["severity_avg"] for s in data["associated_symptoms"])
                / len(data["associated_symptoms"])
                if data["associated_symptoms"]
                else 0,
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

        # Step 6: Call Claude API for medical grounding
        claude_service = ClaudeService()
        ai_analysis = await claude_service.diagnose_correlations(
            scored_ingredients, web_search_enabled=web_search_enabled
        )

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

        # Commit all changes
        self.db.commit()
        self.db.refresh(diagnosis_run)

        return diagnosis_run
