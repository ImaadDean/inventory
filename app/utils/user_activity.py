"""
User activity tracking and online status utilities
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..config.database import get_database
from .timezone import now_kampala, kampala_to_utc, utc_to_kampala, format_kampala_time, format_kampala_date
from bson import ObjectId


async def update_user_activity(user_id: str) -> bool:
    """Update user's last activity timestamp"""
    try:
        db = await get_database()
        current_time = kampala_to_utc(now_kampala())
        
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_activity": current_time}}
        )
        
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating user activity: {e}")
        return False


def get_user_status(last_login: Optional[datetime], last_activity: Optional[datetime]) -> Dict[str, Any]:
    """
    Determine user online status and format display text

    Returns:
    - status: 'online', 'recent', 'away', 'offline'
    - display_text: Text to show in UI
    - is_online: Boolean for online indicator
    """
    now = now_kampala()

    # Use the most recent activity (login or general activity)
    most_recent = None
    if last_login and last_activity:
        # Convert both to Kampala timezone for comparison
        login_kampala = utc_to_kampala(last_login)
        activity_kampala = utc_to_kampala(last_activity)
        most_recent = max(login_kampala, activity_kampala)
    elif last_login:
        most_recent = utc_to_kampala(last_login)
    elif last_activity:
        most_recent = utc_to_kampala(last_activity)

    if not most_recent:
        return {
            "status": "offline",
            "display_text": "Never",
            "is_online": False,
            "css_class": "text-gray-500"
        }
    
    time_diff = now - most_recent
    
    # Online: Active within last 5 minutes
    if time_diff <= timedelta(minutes=5):
        return {
            "status": "online",
            "display_text": "Online",
            "is_online": True,
            "css_class": "text-green-600 font-semibold"
        }
    
    # Recent: Active within last 24 hours - show time
    elif time_diff <= timedelta(hours=24):
        time_str = format_kampala_time(most_recent, "%H:%M")
        return {
            "status": "recent",
            "display_text": time_str,
            "is_online": False,
            "css_class": "text-blue-600"
        }
    
    # This week: Show day name
    elif time_diff <= timedelta(days=7):
        day_name = format_kampala_date(most_recent, "%a")  # Mon, Tue, etc.
        return {
            "status": "away",
            "display_text": day_name,
            "is_online": False,
            "css_class": "text-yellow-600"
        }
    
    # Older: Show date
    else:
        date_str = format_kampala_date(most_recent, "%d/%m/%Y")
        return {
            "status": "offline",
            "display_text": date_str,
            "is_online": False,
            "css_class": "text-gray-500"
        }


def get_detailed_user_status(last_login: Optional[datetime], last_activity: Optional[datetime]) -> Dict[str, Any]:
    """
    Get detailed user status information for tooltips or detailed views
    """
    now = now_kampala()
    status_info = get_user_status(last_login, last_activity)
    
    # Use the most recent activity
    most_recent = None
    activity_type = "activity"
    
    if last_login and last_activity:
        login_kampala = utc_to_kampala(last_login)
        activity_kampala = utc_to_kampala(last_activity)
        if login_kampala >= activity_kampala:
            most_recent = login_kampala
            activity_type = "login"
        else:
            most_recent = activity_kampala
            activity_type = "activity"
    elif last_login:
        most_recent = utc_to_kampala(last_login)
        activity_type = "login"
    elif last_activity:
        most_recent = utc_to_kampala(last_activity)
        activity_type = "activity"
    
    if not most_recent:
        return {
            **status_info,
            "tooltip": "User has never logged in",
            "last_seen_full": "Never",
            "activity_type": "none"
        }
    
    time_diff = now - most_recent
    
    # Create detailed tooltip
    if time_diff <= timedelta(minutes=5):
        tooltip = f"Online now (last {activity_type} {time_diff.seconds // 60} min ago)"
    elif time_diff <= timedelta(hours=1):
        minutes = time_diff.seconds // 60
        tooltip = f"Last {activity_type}: {minutes} minutes ago"
    elif time_diff <= timedelta(hours=24):
        hours = time_diff.seconds // 3600
        tooltip = f"Last {activity_type}: {hours} hours ago"
    elif time_diff <= timedelta(days=7):
        days = time_diff.days
        tooltip = f"Last {activity_type}: {days} day{'s' if days > 1 else ''} ago"
    else:
        days = time_diff.days
        if days < 30:
            tooltip = f"Last {activity_type}: {days} days ago"
        elif days < 365:
            months = days // 30
            tooltip = f"Last {activity_type}: {months} month{'s' if months > 1 else ''} ago"
        else:
            years = days // 365
            tooltip = f"Last {activity_type}: {years} year{'s' if years > 1 else ''} ago"
    
    # Full timestamp for detailed view
    last_seen_full = format_kampala_date(most_recent, "%d/%m/%Y") + " at " + format_kampala_time(most_recent, "%H:%M")
    
    return {
        **status_info,
        "tooltip": tooltip,
        "last_seen_full": last_seen_full,
        "activity_type": activity_type
    }


def get_online_users_count(users_data: list) -> Dict[str, int]:
    """
    Count users by their online status
    """
    counts = {
        "online": 0,
        "recent": 0,
        "away": 0,
        "offline": 0,
        "total": len(users_data)
    }
    
    for user in users_data:
        last_login = user.get("last_login")
        last_activity = user.get("last_activity")
        status_info = get_user_status(last_login, last_activity)
        counts[status_info["status"]] += 1
    
    return counts


async def cleanup_old_activities():
    """
    Clean up old activity records (optional maintenance function)
    Remove activity records older than 30 days to keep database clean
    """
    try:
        db = await get_database()
        cutoff_date = kampala_to_utc(now_kampala() - timedelta(days=30))
        
        # We don't actually delete the records, just for reference
        # This could be used to clean up a separate activity log table if implemented
        
        return True
    except Exception as e:
        print(f"Error cleaning up old activities: {e}")
        return False


def format_user_activity_summary(users_data: list) -> str:
    """
    Create a summary string of user activity for admin dashboard
    """
    counts = get_online_users_count(users_data)
    
    summary_parts = []
    if counts["online"] > 0:
        summary_parts.append(f"{counts['online']} online")
    if counts["recent"] > 0:
        summary_parts.append(f"{counts['recent']} recent")
    if counts["away"] > 0:
        summary_parts.append(f"{counts['away']} away")
    if counts["offline"] > 0:
        summary_parts.append(f"{counts['offline']} offline")
    
    if not summary_parts:
        return "No users"
    
    return f"{counts['total']} users: " + ", ".join(summary_parts)
