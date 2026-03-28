"""Working hours utility functions for the Team Records Bot."""
import pytz
from datetime import datetime, timedelta
from typing import Tuple
from config import config


def get_current_time_in_timezone() -> datetime:
    """Get current time in the configured timezone."""
    tz = pytz.timezone(config.bot.timezone)
    return datetime.now(tz)


def is_working_hours(check_time: datetime = None) -> bool:
    """
    Check if the given time (or current time) falls within working hours.

    Args:
        check_time: Time to check. If None, uses current time.

    Returns:
        True if within working hours, False otherwise.
    """
    if check_time is None:
        check_time = get_current_time_in_timezone()

    # Convert to timezone if not already timezone-aware
    if check_time.tzinfo is None:
        tz = pytz.timezone(config.bot.timezone)
        check_time = tz.localize(check_time)
    else:
        # Convert to configured timezone
        tz = pytz.timezone(config.bot.timezone)
        check_time = check_time.astimezone(tz)

    hour = check_time.hour
    return config.bot.work_start_hour <= hour < config.bot.work_end_hour


def next_working_hour_start(from_time: datetime = None) -> datetime:
    """
    Get the next time working hours start.

    Args:
        from_time: Time to calculate from. If None, uses current time.

    Returns:
        Datetime when working hours next begin.
    """
    if from_time is None:
        from_time = get_current_time_in_timezone()

    # Convert to timezone if not already timezone-aware
    if from_time.tzinfo is None:
        tz = pytz.timezone(config.bot.timezone)
        from_time = tz.localize(from_time)
    else:
        # Convert to configured timezone
        tz = pytz.timezone(config.bot.timezone)
        from_time = from_time.astimezone(tz)

    # If already in working hours, return start of next day's working hours
    if is_working_hours(from_time):
        next_day = from_time + timedelta(days=1)
        return next_day.replace(
            hour=config.bot.work_start_hour,
            minute=0,
            second=0,
            microsecond=0
        )

    # If before working hours today, return today's start time
    current_hour = from_time.hour
    if current_hour < config.bot.work_start_hour:
        return from_time.replace(
            hour=config.bot.work_start_hour,
            minute=0,
            second=0,
            microsecond=0
        )

    # If after working hours today, return tomorrow's start time
    next_day = from_time + timedelta(days=1)
    return next_day.replace(
        hour=config.bot.work_start_hour,
        minute=0,
        second=0,
        microsecond=0
    )


def get_working_hours_info() -> Tuple[str, int, int]:
    """
    Get working hours configuration info.

    Returns:
        Tuple of (timezone, start_hour, end_hour)
    """
    return (
        config.bot.timezone,
        config.bot.work_start_hour,
        config.bot.work_end_hour
    )


def format_working_hours() -> str:
    """
    Format working hours as human-readable string.

    Returns:
        Formatted string like "10:00-22:00 (Europe/Paris)"
    """
    return f"{config.bot.work_start_hour:02d}:00-{config.bot.work_end_hour:02d}:00 ({config.bot.timezone})"


def time_until_next_working_hours(from_time: datetime = None) -> timedelta:
    """
    Get time remaining until next working hours start.

    Args:
        from_time: Time to calculate from. If None, uses current time.

    Returns:
        Timedelta until working hours start.
    """
    if from_time is None:
        from_time = get_current_time_in_timezone()

    if is_working_hours(from_time):
        return timedelta(0)  # Already in working hours

    next_start = next_working_hour_start(from_time)
    return next_start - from_time