import unicodedata
from difflib import SequenceMatcher

from Backend.Regulation.ExtractedTask import ExtractedTask


class Validation:
    '''Class to deduplicate ExtractedTask instances based on specific criteria.'''
    def __init__(self):
        self.TEXT_SIMILARITY_THRESHOLD = 0.75
        self.TASK_FIELDS = (
            "start_time", "end_time", "deadline", "registration_start", "registration_end", "type"
        )
    
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
