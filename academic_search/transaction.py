"""Task search using the integration manager's transaction provider."""
from typing import TYPE_CHECKING

from .interpretation import _prepare_interpreted_request
from .service import SearchDatabaseError, SearchService
from .validation import validate_request, validate_task_id, validate_user_id

if TYPE_CHECKING:
    from Database.database_manager import DatabaseManager


class TransactionalSearch:
    """Search tasks assigned to a trusted user in one transaction per operation."""

    def __init__(self, database_manager: "DatabaseManager", *, user_id: int):
        self._user_id = validate_user_id(user_id)
        self._manager = database_manager

    def get_task_by_id(self, task_id):
        """Look up an assigned task across all statuses, returning None if absent."""
        return self._run(SearchService._get_task_by_id, validate_task_id(task_id))

    def search_tasks(self, request):
        """Return a stable page of matching assigned task dictionaries."""
        return self._run(SearchService._search_tasks, validate_request(request))

    def interpret_and_search(self, request):
        """Return point-expression metadata and matching assigned tasks."""
        return self._run(SearchService._interpret_and_search, *_prepare_interpreted_request(request))

    def _run(self, operation, *args):
        try:
            with self._manager.database.transaction() as connection:
                search = SearchService.from_connection(connection, user_id=self._user_id)
                result = operation(search, *args)
        except SearchDatabaseError:
            raise
        except Exception as error:
            raise SearchDatabaseError("PostgreSQL search transaction failed") from error
        return result
