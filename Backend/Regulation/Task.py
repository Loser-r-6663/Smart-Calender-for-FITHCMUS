from pydantic import BaseModel
from datetime import datetime


class BaseTask(BaseModel):
    def update(self, **kwargs):
        """Update the attributes of the RawTask instance with the provided keyword arguments."""
        for key, value in kwargs.items():
            if key in self.model_fields: setattr(self, key, value)
        return self
    
    def __repr__(self):
        fields = "\n".join(f"\t{k}: {v!r}" for k, v in self)
        return f"\n{self.__class__.__name__}(\n{fields}\n)"
    
    __str__ = __repr__


class RawTask(BaseTask):
    Title: str = "N/A"           # Title of the post
    Type: str = "N/A"            # Type of the post (e.g., SHCD-SV đầu năm, HỌC BỔNG TÀI TRỢ)
    Description: str = "N/A"     # Description or brief summary of the post
    CreateDate: str = "N/A"      # Creation date of the post
    Duration: str = "N/A"        # Duration of the task or event
    Deadline: str = "N/A"        # Assignment deadline
    Course: str = "N/A"          # Course associated with the post
    Location: str = "N/A"        # Location of the event or task
    Content: str = "N/A"         # Full content of the post
    Link: str = "N/A"            # Link to the original post
    Platform: str = "N/A"        # Platform from which the post was crawled (e.g., Portal, Facebook)


class ExtractedTask(BaseTask):
    title: str
    type: str | None = None
    course: str | None = None
    description: str | None = None
    target_audience: str | None = None
    location: str | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    estimated_hours: float | None = None
    training_points: int | None = None
    training_point_category: str | None = None
    source_url: str | None = None
    source_platform: str | None = None
    updated_at: datetime | None = None
