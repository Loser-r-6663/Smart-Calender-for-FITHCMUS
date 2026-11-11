from collections.abc import Mapping
from typing import Any

from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection

from Database.enums import DRLCategory


_VALID_CATEGORIES = frozenset(category.value for category in DRLCategory)


def validate_drl_scores(
    scores: Mapping[str, Any], *, require_non_empty: bool = True
) -> dict[str, int]:
    """Validate and normalize a mapping of DRL category keys to 0..100 integer points."""
    if require_non_empty and not scores:
        raise ValueError("scores cannot be empty")

    validated: dict[str, int] = {}
    for category, points in scores.items():
        if not isinstance(category, str) or category not in _VALID_CATEGORIES:
            raise ValueError(f"Unsupported DRL category: {category!r}")
        if isinstance(points, bool) or not isinstance(points, int):
            raise ValueError(f"DRL points for {category} must be an integer")
        if points < 0 or points > 100:
            raise ValueError(f"DRL points for {category} must be between 0 and 100")
        validated[category] = points
    return validated


class UserDRLRepository:
    def get_for_user(
        self, db_connection: connection, user_id: int
    ) -> list[dict[str, Any]]:
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT user_id, drl_category, points, updated_at
                FROM user_drl_scores
                WHERE user_id = %s
                ORDER BY drl_category
                """,
                (user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def upsert_scores(
        self,
        db_connection: connection,
        user_id: int,
        scores: Mapping[str, int],
    ) -> list[dict[str, Any]]:
        validated = validate_drl_scores(scores, require_non_empty=True)
        with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
            for category in sorted(validated):
                cursor.execute(
                    """
                    INSERT INTO user_drl_scores (user_id, drl_category, points, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, drl_category)
                    DO UPDATE SET
                        points = EXCLUDED.points,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, category, validated[category]),
                )
        return self.get_for_user(db_connection, user_id)

