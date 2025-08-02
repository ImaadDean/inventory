"""
Template filters for Jinja2 templates with Kampala timezone support
"""

from datetime import datetime
from typing import Optional
from .timezone import (
    format_kampala_datetime, 
    format_kampala_date, 
    format_kampala_time,
    format_relative_time,
    now_kampala,
    utc_to_kampala
)


def kampala_datetime(value: Optional[datetime], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime in Kampala timezone"""
    if not value:
        return ""
    return format_kampala_datetime(value, format_str)


def kampala_date(value: Optional[datetime], format_str: str = "%Y-%m-%d") -> str:
    """Format date in Kampala timezone"""
    if not value:
        return ""
    return format_kampala_date(value, format_str)


def kampala_time(value: Optional[datetime], format_str: str = "%H:%M:%S") -> str:
    """Format time in Kampala timezone"""
    if not value:
        return ""
    return format_kampala_time(value, format_str)


def kampala_date_friendly(value: Optional[datetime]) -> str:
    """Format date in friendly format (e.g., 'Jan 15, 2024')"""
    if not value:
        return ""
    return format_kampala_date(value, "%b %d, %Y")


def kampala_datetime_friendly(value: Optional[datetime]) -> str:
    """Format datetime in friendly format (e.g., 'Jan 15, 2024 at 2:30 PM')"""
    if not value:
        return ""
    return format_kampala_datetime(value, "%b %d, %Y at %I:%M %p")


def kampala_time_friendly(value: Optional[datetime]) -> str:
    """Format time in friendly format (e.g., '2:30 PM')"""
    if not value:
        return ""
    return format_kampala_time(value, "%I:%M %p")


def relative_time(value: Optional[datetime]) -> str:
    """Format datetime as relative time (e.g., '2 hours ago')"""
    if not value:
        return ""
    return format_relative_time(value)


def kampala_day_name(value: Optional[datetime]) -> str:
    """Get day name in Kampala timezone (e.g., 'Monday')"""
    if not value:
        return ""
    return format_kampala_date(value, "%A")


def kampala_month_name(value: Optional[datetime]) -> str:
    """Get month name in Kampala timezone (e.g., 'January')"""
    if not value:
        return ""
    return format_kampala_date(value, "%B")


def kampala_short_date(value: Optional[datetime]) -> str:
    """Format date in short format (e.g., '15/01/24')"""
    if not value:
        return ""
    return format_kampala_date(value, "%d/%m/%y")


def kampala_iso_date(value: Optional[datetime]) -> str:
    """Format date in ISO format (e.g., '2024-01-15')"""
    if not value:
        return ""
    return format_kampala_date(value, "%Y-%m-%d")


def kampala_iso_datetime(value: Optional[datetime]) -> str:
    """Format datetime in ISO format (e.g., '2024-01-15T14:30:00')"""
    if not value:
        return ""
    return format_kampala_datetime(value, "%Y-%m-%dT%H:%M:%S")


def is_today(value: Optional[datetime]) -> bool:
    """Check if date is today in Kampala timezone"""
    if not value:
        return False
    
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    
    kampala_dt = utc_to_kampala(value)
    today = now_kampala()
    
    return (kampala_dt.year == today.year and 
            kampala_dt.month == today.month and 
            kampala_dt.day == today.day)


def is_yesterday(value: Optional[datetime]) -> bool:
    """Check if date is yesterday in Kampala timezone"""
    if not value:
        return False
    
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    
    kampala_dt = utc_to_kampala(value)
    today = now_kampala()
    yesterday = today.replace(day=today.day - 1)
    
    return (kampala_dt.year == yesterday.year and 
            kampala_dt.month == yesterday.month and 
            kampala_dt.day == yesterday.day)


def smart_date(value: Optional[datetime]) -> str:
    """Smart date formatting - shows relative time for recent dates, full date for older ones"""
    if not value:
        return ""
    
    if is_today(value):
        return f"Today at {kampala_time_friendly(value)}"
    elif is_yesterday(value):
        return f"Yesterday at {kampala_time_friendly(value)}"
    else:
        # Check if it's within the last week
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        
        kampala_dt = utc_to_kampala(value)
        today = now_kampala()
        days_diff = (today - kampala_dt).days
        
        if days_diff <= 7:
            return f"{kampala_day_name(value)} at {kampala_time_friendly(value)}"
        else:
            return kampala_datetime_friendly(value)


# Dictionary of all filters for easy registration
TEMPLATE_FILTERS = {
    'kampala_datetime': kampala_datetime,
    'kampala_date': kampala_date,
    'kampala_time': kampala_time,
    'kampala_date_friendly': kampala_date_friendly,
    'kampala_datetime_friendly': kampala_datetime_friendly,
    'kampala_time_friendly': kampala_time_friendly,
    'relative_time': relative_time,
    'kampala_day_name': kampala_day_name,
    'kampala_month_name': kampala_month_name,
    'kampala_short_date': kampala_short_date,
    'kampala_iso_date': kampala_iso_date,
    'kampala_iso_datetime': kampala_iso_datetime,
    'is_today': is_today,
    'is_yesterday': is_yesterday,
    'smart_date': smart_date,
}
