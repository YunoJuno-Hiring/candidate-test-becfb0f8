import random
from datetime import datetime, timedelta

# Retry n waits DELAYS[n - 1]; from retry 7 it stays at the 8h cap.
DELAYS = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=2),
    timedelta(hours=4),
    timedelta(hours=8),
]
GIVE_UP_AFTER = timedelta(days=7)
EMAIL_AFTER_RETRY = 4  # admins hear about a failing endpoint once its 4th retry fails (about 1h20m in)


def retry_delay(retry: int, jitter: bool = True) -> timedelta:
    delay = DELAYS[min(retry, len(DELAYS)) - 1]
    # ±10%, so retries to a destination that's just recovered don't all arrive at once.
    return delay * random.uniform(0.9, 1.1) if jitter else delay  # noqa: S311 - timing, not security


def next_attempt_at(
    first_attempt_at: datetime, previous_attempt_at: datetime, retry: int, jitter: bool = True
) -> datetime | None:
    """When retry should run, or None once it would fall more than 7 days after the first attempt."""
    later = previous_attempt_at + retry_delay(retry, jitter)
    return later if later - first_attempt_at <= GIVE_UP_AFTER else None
