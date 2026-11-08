from enum import Enum


class TaskType(str, Enum):
    CLASS = "class"
    ASSIGNMENT = "assignment"
    EXAM = "exam"
    EVENT = "event"
    PERSONAL = "personal"
    TUITION = "tuition"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class DRLCategory(str, Enum):
    DIEU_1 = "dieu_1"
    DIEU_2 = "dieu_2"
    DIEU_3 = "dieu_3"
    DIEU_4 = "dieu_4"
    DIEU_5 = "dieu_5"


class SourcePlatform(str, Enum):
    MOODLE = "moodle"
    PORTAL = "portal"
    FACEBOOK = "facebook"
    CUSTOM = "custom"
