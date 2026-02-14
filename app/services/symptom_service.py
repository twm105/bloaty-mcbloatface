"""Business logic for symptom management."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.symptom import Symptom


class SymptomService:
    """Service for symptom-related operations."""

    @staticmethod
    def create_symptom(
        db: Session,
        user_id: UUID,
        raw_description: str,
        structured_type: Optional[str] = None,
        severity: Optional[int] = None,
        notes: Optional[str] = None,
        clarification_history: Optional[list] = None,
        timestamp: Optional[datetime] = None,
    ) -> Symptom:
        """
        Create a new symptom entry.

        Args:
            db: Database session
            user_id: User ID
            raw_description: User's original symptom description
            structured_type: Categorized symptom type (e.g., "bloating", "nausea")
            severity: Severity rating 1-10
            notes: Additional notes
            clarification_history: Q&A history from AI clarification
            timestamp: Symptom timestamp (defaults to now)

        Returns:
            Created Symptom object
        """
        symptom = Symptom(
            user_id=user_id,
            raw_description=raw_description,
            structured_type=structured_type,
            severity=severity,
            notes=notes,
            clarification_history=clarification_history or [],
            timestamp=timestamp or datetime.utcnow(),
        )
        db.add(symptom)
        db.commit()
        db.refresh(symptom)
        return symptom

    @staticmethod
    def get_symptom(db: Session, symptom_id: int) -> Optional[Symptom]:
        """Get a symptom by ID."""
        return db.query(Symptom).filter(Symptom.id == symptom_id).first()

    @staticmethod
    def get_user_symptoms(
        db: Session, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[Symptom]:
        """Get all symptoms for a user, ordered by timestamp descending."""
        return (
            db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .order_by(Symptom.timestamp.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    @staticmethod
    def update_symptom(
        db: Session,
        symptom_id: int,
        raw_description: Optional[str] = None,
        structured_type: Optional[str] = None,
        severity: Optional[int] = None,
        notes: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Symptom]:
        """
        Update symptom details.

        Args:
            db: Database session
            symptom_id: Symptom ID
            raw_description: Updated description
            structured_type: Updated type
            severity: Updated severity
            notes: Updated notes
            timestamp: Updated timestamp

        Returns:
            Updated Symptom object or None if not found
        """
        symptom = db.query(Symptom).filter(Symptom.id == symptom_id).first()
        if not symptom:
            return None

        if raw_description is not None:
            symptom.raw_description = raw_description
        if structured_type is not None:
            symptom.structured_type = structured_type
        if severity is not None:
            symptom.severity = severity
        if notes is not None:
            symptom.notes = notes
        if timestamp is not None:
            symptom.timestamp = timestamp

        db.commit()
        db.refresh(symptom)
        return symptom

    @staticmethod
    def delete_symptom(db: Session, symptom_id: int) -> bool:
        """
        Delete a symptom.

        Args:
            db: Database session
            symptom_id: Symptom ID

        Returns:
            True if deleted, False if not found
        """
        symptom = db.query(Symptom).filter(Symptom.id == symptom_id).first()
        if symptom:
            db.delete(symptom)
            db.commit()
            return True
        return False

    @staticmethod
    def get_common_symptom_types() -> List[str]:
        """
        Get list of common gastro symptom types for dropdown.

        Returns:
            List of common symptom type strings
        """
        return [
            "Bloating",
            "Gas",
            "Stomach Pain",
            "Abdominal Cramps",
            "Nausea",
            "Diarrhea",
            "Constipation",
            "Heartburn",
            "Acid Reflux",
            "Indigestion",
            "Vomiting",
            "Loss of Appetite",
            "Other",
        ]

    @staticmethod
    def get_most_recent_symptom_tags(
        db: Session, user_id: UUID, limit: int = 3
    ) -> List[Dict]:
        """
        Get most recently used symptom tags for a user.

        Args:
            db: Database session
            user_id: User ID
            limit: Number of recent tags to return

        Returns:
            List of {"name": str, "last_used": datetime, "avg_severity": float}
        """
        # Get unique tags ordered by most recent usage
        result = db.execute(
            text("""
            SELECT DISTINCT ON (LOWER(tag->>'name'))
                LOWER(tag->>'name') as tag_name,
                MAX(start_time) as last_used,
                ROUND(AVG((tag->>'severity')::numeric), 1) as avg_severity
            FROM symptoms,
                 jsonb_array_elements(tags) as tag
            WHERE user_id = :user_id
              AND tags IS NOT NULL
            GROUP BY LOWER(tag->>'name')
            ORDER BY LOWER(tag->>'name'), last_used DESC
            LIMIT :limit
            """),
            {"user_id": str(user_id), "limit": limit},
        )

        return [
            {"name": row[0], "last_used": row[1], "avg_severity": float(row[2])}
            for row in result
        ]

    @staticmethod
    def get_most_common_symptom_tags(
        db: Session, user_id: UUID, limit: int = 3
    ) -> List[Dict]:
        """
        Get most frequently used symptom tags for a user.

        Args:
            db: Database session
            user_id: User ID
            limit: Number of top tags to return

        Returns:
            List of {"name": str, "count": int, "avg_severity": float}
        """
        # Query to extract tags from JSONB and count frequency
        # PostgreSQL jsonb_array_elements expands array to rows
        result = db.execute(
            text("""
            SELECT
                LOWER(tag->>'name') as tag_name,
                COUNT(*) as count,
                ROUND(AVG((tag->>'severity')::numeric), 1) as avg_severity
            FROM symptoms,
                 jsonb_array_elements(tags) as tag
            WHERE user_id = :user_id
              AND tags IS NOT NULL
            GROUP BY LOWER(tag->>'name')
            ORDER BY count DESC, avg_severity DESC
            LIMIT :limit
            """),
            {"user_id": str(user_id), "limit": limit},
        )

        return [
            {"name": row[0], "count": row[1], "avg_severity": float(row[2])}
            for row in result
        ]

    @staticmethod
    def search_symptom_tags(
        db: Session, user_id: UUID, query: str, limit: int = 10
    ) -> List[str]:
        """
        Autocomplete search for symptom tags.

        Searches user's historical tags + common symptom types.

        Args:
            db: Database session
            user_id: User ID
            query: Search query string
            limit: Max suggestions to return

        Returns:
            List of matching tag names (lowercase)
        """
        query_lower = query.lower()

        # Get user's unique tags matching query
        user_tags_result = db.execute(
            text("""
            SELECT DISTINCT LOWER(tag->>'name') as tag_name,
                   COUNT(*) as frequency
            FROM symptoms,
                 jsonb_array_elements(tags) as tag
            WHERE user_id = :user_id
              AND tags IS NOT NULL
              AND LOWER(tag->>'name') LIKE :query
            GROUP BY LOWER(tag->>'name')
            ORDER BY frequency DESC
            LIMIT :limit
            """),
            {"user_id": str(user_id), "query": f"%{query_lower}%", "limit": limit},
        )

        user_tags = [row[0] for row in user_tags_result]

        # Add common symptom types that match
        common_types = SymptomService.get_common_symptom_types()
        matching_common = [
            t.lower()
            for t in common_types
            if query_lower in t.lower() and t.lower() not in user_tags
        ]

        # Combine: user tags first, then common types
        results = user_tags + matching_common
        return results[:limit]

    @staticmethod
    def detect_ongoing_symptom_by_name(
        db: Session, user_id: UUID, symptom_name: str, lookback_hours: int = 72
    ) -> Optional[Symptom]:
        """
        Find most recent symptom matching a specific name within lookback window.

        Args:
            db: Database session
            user_id: User ID
            symptom_name: Symptom name to search for
            lookback_hours: How far back to search (default 72h = 3 days)

        Returns:
            Most recent matching Symptom or None
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)

        # Search for symptom with matching tag name
        symptom = db.execute(
            text("""
            SELECT DISTINCT ON (s.id) s.id
            FROM symptoms s,
                 jsonb_array_elements(s.tags) as tag
            WHERE s.user_id = :user_id
              AND s.tags IS NOT NULL
              AND (s.start_time >= :cutoff_time OR s.timestamp >= :cutoff_time)
              AND LOWER(tag->>'name') = :symptom_name
            ORDER BY s.id, COALESCE(s.start_time, s.timestamp) DESC
            LIMIT 1
            """),
            {
                "user_id": str(user_id),
                "cutoff_time": cutoff_time,
                "symptom_name": symptom_name.lower(),
            },
        ).first()

        if symptom:
            return db.query(Symptom).filter(Symptom.id == symptom[0]).first()

        return None

    @staticmethod
    def detect_similar_recent_symptoms(
        db: Session, user_id: UUID, tags: List[Dict], lookback_hours: int = 48
    ) -> Optional[Symptom]:
        """
        Detect if similar symptoms logged recently (potential episode continuation).

        Args:
            db: Database session
            user_id: User ID
            tags: List of {"name": str, "severity": int} for current symptom
            lookback_hours: How far back to search (default 48 hours)

        Returns:
            Most recent matching Symptom or None
        """
        if not tags:
            return None

        # Extract tag names for comparison
        tag_names = [t["name"].lower() for t in tags]

        # Get recent symptoms
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)

        # Find symptoms with overlapping tags
        # Note: This uses PostgreSQL JSONB operators
        # ?| checks if any of the tag names exist in the JSONB array
        recent_symptoms = db.execute(
            text("""
            SELECT s.id, s.tags, s.timestamp, s.start_time
            FROM symptoms s,
                 jsonb_array_elements(s.tags) as tag
            WHERE s.user_id = :user_id
              AND s.tags IS NOT NULL
              AND (s.start_time >= :cutoff_time OR s.timestamp >= :cutoff_time)
              AND LOWER(tag->>'name') = ANY(:tag_names)
            ORDER BY COALESCE(s.start_time, s.timestamp) DESC
            LIMIT 1
            """),
            {
                "user_id": str(user_id),
                "cutoff_time": cutoff_time,
                "tag_names": tag_names,
            },
        ).first()

        if recent_symptoms:
            return db.query(Symptom).filter(Symptom.id == recent_symptoms[0]).first()

        return None

    @staticmethod
    def create_symptom_with_tags(
        db: Session,
        user_id: UUID,
        tags: List[Dict],
        ai_generated_text: Optional[str] = None,
        final_notes: Optional[str] = None,
    ) -> Symptom:
        """
        Create symptom with tag-based schema (now supports per-symptom times).

        Args:
            db: Database session
            user_id: User ID
            tags: List of {"name": str, "severity": int, "start_time": str?, "end_time": str?, "episode_id": int?}
            ai_generated_text: Original unedited AI response (or None)
            final_notes: User-edited final text (or same as AI if not edited, or None)

        Returns:
            Created Symptom object
        """
        # Validate tags format
        if not tags:
            raise ValueError("At least one tag is required")

        for tag in tags:
            if "name" not in tag or "severity" not in tag:
                raise ValueError("Each tag must have 'name' and 'severity' fields")
            if not isinstance(tag["severity"], int) or not 1 <= tag["severity"] <= 10:
                raise ValueError("Severity must be an integer between 1 and 10")

        # Determine global start/end from first tag with times set
        global_start_time = None
        global_end_time = None
        episode_id = None

        for tag in tags:
            if tag.get("start_time") and not global_start_time:
                global_start_time = datetime.fromisoformat(tag["start_time"])
            if tag.get("end_time") and not global_end_time:
                global_end_time = datetime.fromisoformat(tag["end_time"])
            if tag.get("episode_id") and not episode_id:
                episode_id = tag["episode_id"]

        # Fallback to current time if no times specified
        if not global_start_time:
            global_start_time = datetime.utcnow()

        # Populate backward-compatible fields
        # structured_type = most severe tag name
        # severity = highest severity value
        sorted_tags = sorted(tags, key=lambda t: t["severity"], reverse=True)
        most_severe_tag = sorted_tags[0]

        structured_type = most_severe_tag["name"].lower()
        severity = most_severe_tag["severity"]

        # Generate description from tags if final_notes is empty
        if not final_notes and tags:
            tag_descriptions = [f"{t['name']} ({t['severity']}/10)" for t in tags]
            raw_description = ", ".join(tag_descriptions)
        else:
            raw_description = final_notes or ""

        # Set deprecated fields for backward compatibility
        ai_elaborated = ai_generated_text is not None
        user_edited = (
            ai_generated_text is not None
            and final_notes is not None
            and ai_generated_text != final_notes
        )

        symptom = Symptom(
            user_id=user_id,
            raw_description=raw_description,
            structured_type=structured_type,
            severity=severity,
            notes=final_notes,  # backward compat: notes = final_notes
            tags=tags,  # Store with per-symptom times
            start_time=global_start_time,
            end_time=global_end_time,
            episode_id=episode_id,
            # New fields
            ai_generated_text=ai_generated_text,
            final_notes=final_notes,
            # Deprecated fields (for backward compatibility)
            ai_elaborated=ai_elaborated,
            ai_elaboration_response=ai_generated_text,
            user_edited_elaboration=user_edited,
            timestamp=global_start_time,
        )

        db.add(symptom)
        db.commit()
        db.refresh(symptom)
        return symptom

    @staticmethod
    def link_episode(db: Session, symptom_id: int, previous_symptom_id: int) -> bool:
        """
        Link a symptom to a previous symptom as episode continuation.

        Args:
            db: Database session
            symptom_id: Current symptom ID
            previous_symptom_id: Previous symptom ID to link to

        Returns:
            True if linked successfully, False if symptom not found
        """
        symptom = db.query(Symptom).filter(Symptom.id == symptom_id).first()
        if not symptom:
            return False

        symptom.episode_id = previous_symptom_id
        db.commit()
        return True


# Singleton instance
symptom_service = SymptomService()
