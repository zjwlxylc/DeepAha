"""Calendar-month terms; no 60/365-day approximation."""
from calendar import monthrange
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
SHANGHAI = ZoneInfo('Asia/Shanghai')


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware datetime required')
    return value.astimezone(UTC)


def now() -> datetime:
    return datetime.now(UTC)


def stamp(value: datetime) -> str:
    return aware(value).isoformat(timespec='microseconds')


def parse(value: str) -> datetime:
    return aware(datetime.fromisoformat(value))


def add_months(value: datetime, months: int) -> datetime:
    if type(months) is not int or not 1 <= months <= 36:
        raise ValueError('Term must be 1 to 36 calendar months')
    local = aware(value).astimezone(SHANGHAI)
    index = local.year * 12 + local.month - 1 + months
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    return local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1])).astimezone(UTC)
