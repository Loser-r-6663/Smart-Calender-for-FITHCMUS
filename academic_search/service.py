"""Read-only PostgreSQL task search using the selected DatabaseManager connection."""
from typing import TYPE_CHECKING

from .postgres import compile_lookup, compile_request, task_record
from .validation import check, validate_request, validate_task_id

if TYPE_CHECKING:
    from Database.DatabaseManager import DatabaseManager


class SearchDatabaseError(RuntimeError):
    """A PostgreSQL operation or database record conversion failed."""


class SearchService:
    """Search tasks assigned to a trusted user; the caller owns transactions."""

    def __init__(self, database_manager: "DatabaseManager | None", *, user_id: int):
        check(type(user_id) is int and 1 <= user_id <= 2_147_483_647,
              "user_id must be a positive PostgreSQL integer")
        self.database_manager = database_manager
        self.user_id = user_id
        self._connection = None

    @classmethod
    def from_connection(cls, connection, *, user_id: int):
        """Borrow an explicit PostgreSQL connection; the caller owns its lifetime."""
        service = cls(None, user_id=user_id)
        service._connection = connection
        return service

    def _query(self, sql, params, *, single=False):
        try:
            # Cursor contexts close cursors only; a connection context would commit.
            connection = self.database_manager.connection if self.database_manager is not None else self._connection
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                if single:
                    row = cursor.fetchone()
                    return None if row is None else task_record(row)
                return [task_record(row) for row in cursor.fetchall()]
        except Exception as error:
            # The owner must roll back a failed shared transaction before reuse.
            raise SearchDatabaseError("PostgreSQL task search failed") from error

    def get_task_by_id(self, task_id):
        """Look up an assigned task across all statuses, returning None if absent."""
        task_id = validate_task_id(task_id)
        sql, params = compile_lookup(task_id, self.user_id)
        return self._query(sql, params, single=True)

    def search_tasks(self, request):
        """Return a stable page of matching assigned task dictionaries."""
        validated = validate_request(request)
        sql, params = compile_request(validated, self.user_id)
        return self._query(sql, params)
