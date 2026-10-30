"""The single stable datetime policy shared by data-processing boundaries."""

from datetime import datetime, timedelta, timezone


GMT_PLUS_7 = timezone(timedelta(hours=7), name="GMT+07:00")


def normalize_datetime(value: datetime) -> datetime:
    """Return ``value`` represented in GMT+7.

    Naive values are defined to already represent local GMT+7 clock time, so
    the timezone is attached without changing the wall-clock fields. Aware
    values are converted to the same zone.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=GMT_PLUS_7)
    return value.astimezone(GMT_PLUS_7)
