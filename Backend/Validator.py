import unicodedata
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

from Backend.Regulation.ExtractedTask import ExtractedTask

VN_TZ = timezone(timedelta(hours=7))


class Validator:
    '''Class to deduplicate ExtractedTask instances based on specific criteria.'''
    def __init__(self):
        self.TEXT_SIMILARITY_THRESHOLD = 0.75
        self.TASK_FIELDS = (
            "start_time", "end_time", "deadline", "registration_start", "registration_end", "type"
        )
    
    @staticmethod
    def _to_vn_time(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        # Nếu là naive datetime (như từ Moodle), gán tzinfo là VN_TZ
        if dt.tzinfo is None:
            return dt.replace(tzinfo=VN_TZ)
        # Nếu đã có timezone khác, chuyển về VN_TZ
        return dt.astimezone(VN_TZ)
    
    @staticmethod
    def _clean_text(value: str):
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    
    def _has_similar_title(self, task: ExtractedTask, previous: ExtractedTask):
        """Return whether the titles and available descriptions are similar enough."""
        title = self._clean_text(task.title)
        prior_title = self._clean_text(previous.title)
        
        # The titles must meet the configured similarity threshold.
        return SequenceMatcher(a=title, b=prior_title).ratio() >= self.TEXT_SIMILARITY_THRESHOLD
    
    def _is_duplicate(self, task: ExtractedTask, previous: ExtractedTask):
        if all(getattr(task, field) == getattr(previous, field) for field in self.TASK_FIELDS):
            return self._has_similar_title(task, previous)
        else:
            return False
    
    def deduplicate_task(self, tasks: list[ExtractedTask], retained: list[ExtractedTask]):
        """Return new tasks not duplicated by retained or earlier new tasks."""
        retained = retained.copy()
        for task in tasks:
            if not any(self._is_duplicate(task, previous) for previous in retained):
                retained.append(task)
        return retained

    def filter_expired_tasks(self, tasks: list[ExtractedTask]):
        """Return tasks that have expired as of reference_time (defaults to now)."""
        now = datetime.now(tz=VN_TZ)
        expired: list[ExtractedTask] = []
        for task in tasks:
            if isinstance(task.deadline, datetime) and self._to_vn_time(task.deadline) < now:
                expired.append(task)
            elif isinstance(task.registration_end, datetime) and self._to_vn_time(task.registration_end) < now:
                expired.append(task)
            elif isinstance(task.end_time, datetime) and self._to_vn_time(task.end_time) < now:
                expired.append(task)
        return expired
