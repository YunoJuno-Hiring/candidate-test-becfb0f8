import random
from datetime import datetime, timedelta

from django.conf import settings


def retry_delay(retry: int, jitter: bool = True) -> timedelta:
    delays = settings.WEBHOOK_RETRY_DELAYS
    delay = delays[min(retry, len(delays)) - 1]
    spread = settings.WEBHOOK_RETRY_JITTER
    return delay * random.uniform(1 - spread, 1 + spread) if jitter else delay  # noqa: S311 - timing, not security


def next_attempt_at(
    first_attempt_at: datetime, previous_attempt_at: datetime, retry: int, jitter: bool = True
) -> datetime | None:
    """When retry should run, or None once it would fall more than 7 days after the first attempt."""
    later = previous_attempt_at + retry_delay(retry, jitter)
    return later if later - first_attempt_at <= settings.WEBHOOK_GIVE_UP_AFTER else None
