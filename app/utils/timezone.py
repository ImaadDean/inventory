"""
Timezone utilities for Kampala, Uganda (East Africa Time)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz

# East Africa Time (UTC+3) - Kampala, Uganda timezone
EAT = timezone(timedelta(hours=3))
KAMPALA_TZ = pytz.timezone('Africa/Kampala')


def now_kampala() -> datetime:
    """Get current datetime in Kampala, Uganda timezone"""
    return datetime.now(KAMPALA_TZ)


def utc_to_kampala(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to Kampala timezone"""
    if utc_dt.tzinfo is None:
        # Assume UTC if no timezone info
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(KAMPALA_TZ)


def kampala_to_utc(kampala_dt: datetime) -> datetime:
    """Convert Kampala timezone datetime to UTC"""
    if kampala_dt.tzinfo is None:
        # Assume Kampala timezone if no timezone info
        kampala_dt = KAMPALA_TZ.localize(kampala_dt)
    return kampala_dt.astimezone(timezone.utc)


def format_kampala_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime in Kampala timezone"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    kampala_dt = dt.astimezone(KAMPALA_TZ)
    return kampala_dt.strftime(format_str)


def format_kampala_date(dt: datetime, format_str: str = "%Y-%m-%d") -> str:
    """Format date in Kampala timezone"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    kampala_dt = dt.astimezone(KAMPALA_TZ)
    return kampala_dt.strftime(format_str)


def format_kampala_time(dt: datetime, format_str: str = "%H:%M:%S") -> str:
    """Format time in Kampala timezone"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    kampala_dt = dt.astimezone(KAMPALA_TZ)
    return kampala_dt.strftime(format_str)


def get_kampala_date_range(days_back: int = 7) -> tuple[datetime, datetime]:
    """Get date range in Kampala timezone"""
    end_date = now_kampala()
    start_date = end_date - timedelta(days=days_back)
    return start_date, end_date


def is_business_hours(dt: Optional[datetime] = None) -> bool:
    """Check if datetime is within business hours in Kampala (8 AM - 6 PM)"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    # Business hours: 8 AM to 6 PM
    return 8 <= dt.hour < 18


def get_business_day_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of business day (8 AM) in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    return dt.replace(hour=8, minute=0, second=0, microsecond=0)


def get_business_day_end(dt: Optional[datetime] = None) -> datetime:
    """Get end of business day (6 PM) in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    return dt.replace(hour=18, minute=0, second=0, microsecond=0)


def get_day_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of day (midnight) in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_day_end(dt: Optional[datetime] = None) -> datetime:
    """Get end of day (23:59:59) in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_week_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of week (Monday) in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    days_since_monday = dt.weekday()
    monday = dt - timedelta(days=days_since_monday)
    return get_day_start(monday)


def get_month_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of month in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_year_start(dt: Optional[datetime] = None) -> datetime:
    """Get start of year in Kampala timezone"""
    if dt is None:
        dt = now_kampala()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KAMPALA_TZ)
    
    return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., '2 hours ago', 'yesterday')"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = now_kampala()
    dt_kampala = dt.astimezone(KAMPALA_TZ)
    
    diff = now - dt_kampala
    
    if diff.days > 0:
        if diff.days == 1:
            return "yesterday"
        elif diff.days < 7:
            return f"{diff.days} days ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif diff.days < 365:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
    
    seconds = diff.total_seconds()
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"


def get_timezone_info() -> dict:
    """Get timezone information for Kampala, Uganda"""
    now = now_kampala()
    return {
        "timezone": "Africa/Kampala",
        "name": "East Africa Time",
        "abbreviation": "EAT",
        "utc_offset": "+03:00",
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "is_dst": False,  # East Africa Time doesn't observe DST
        "country": "Uganda",
        "city": "Kampala"
    }


def now_eat() -> datetime:
    """Get current datetime in East Africa Time (EAT) - alias for now_kampala()"""
    return now_kampala()


def eat_to_utc(eat_dt: datetime) -> datetime:
    """Convert East Africa Time datetime to UTC - alias for kampala_to_utc()"""
    return kampala_to_utc(eat_dt)


def utc_to_eat(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to East Africa Time - alias for utc_to_kampala()"""
    return utc_to_kampala(utc_dt)


def format_eat_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime in East Africa Time - alias for format_kampala_datetime()"""
    return format_kampala_datetime(dt, format_str)


def format_eat_date(dt: datetime, format_str: str = "%Y-%m-%d") -> str:
    """Format date in East Africa Time - alias for format_kampala_date()"""
    return format_kampala_date(dt, format_str)


def format_eat_time(dt: datetime, format_str: str = "%H:%M:%S") -> str:
    """Format time in East Africa Time - alias for format_kampala_time()"""
    return format_kampala_time(dt, format_str)


def get_today_start_utc() -> datetime:
    """Get the start of today (midnight) in UTC, based on Kampala's current date."""
    now_in_kampala = now_kampala()
    today_start_kampala = now_in_kampala.replace(hour=0, minute=0, second=0, microsecond=0)
    return kampala_to_utc(today_start_kampala)

def get_today_end_utc() -> datetime:
    """Get the end of today (23:59:59.999999) in UTC, based on Kampala's current date."""
    now_in_kampala = now_kampala()
    today_end_kampala = now_in_kampala.replace(hour=23, minute=59, second=59, microsecond=999999)
    return kampala_to_utc(today_end_kampala)
