from datetime import datetime

from Backend.Regulation.BaseTask import BaseTask, Location, DayTime


class RawTask(BaseTask):
    title: str | None = None                  # Title of the post
    type: str | None = None                   # Type of the post (e.g., SHCD-SV đầu năm, HỌC BỔNG TÀI TRỢ)
    description: str | None = None            # Description or brief summary of the post
    create_date: str | None = None            # Creation date of the post
    start_time: DayTime | None = None         # Start time of the event or task
    end_time: DayTime | None = None           # End time of the event or task
    deadline: datetime | None = None          # Assignment deadline
    course: str | None = None                 # Course associated with the post
    location: Location | None = None          # Location of the event or task
    content: str | None = None                # Full content of the post
    link: str | None = None                   # Link to the original post
    platform: str | None = None               # Platform from which the post was crawled
    updated_at: datetime | None = None        # Timestamp of when the data was extracted
