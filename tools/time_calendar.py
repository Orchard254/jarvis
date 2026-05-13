"""
time_calendar — time & calendar sense.

Gives Jarvis a real-time clock and the ability to read/write calendar events
via Outlook (win32com) or plain .ics files.

Actions
-------
get_time        Return current date, time, timezone, weekday, ISO week.
get_events      List upcoming calendar events (next N days).
create_event    Create a new calendar event.
delete_event    Delete/cancel an event by subject + date.

Backends
--------
outlook     Uses win32com.client — zero auth, works if Outlook is installed.
            Set CALENDAR_BACKEND=outlook in .env (default).
ics         Read/write a local .ics file.
            Set CALENDAR_BACKEND=ics and ICS_CALENDAR_PATH=/path/to/cal.ics.

Notes
-----
- Google Calendar is intentionally out of scope here (needs OAuth2 browser
  flow which is awkward in a background agent).  Add it as a future backend.
- All times are returned in the local timezone unless a tzname is provided.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import settings

logger = logging.getLogger(__name__)

# ── timezone helper ───────────────────────────────────────────────────────────

def _local_tz():
    """Return the local ZoneInfo object, falling back to UTC."""
    import time as _time
    try:
        # tzlocal is optional but gives a reliable name on Windows
        import tzlocal
        return tzlocal.get_localzone()
    except ImportError:
        pass
    # stdlib fallback: ask the OS
    try:
        tz_name = datetime.now().astimezone().tzname()
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


# ── get_time ──────────────────────────────────────────────────────────────────

def _action_get_time() -> dict:
    tz = _local_tz()
    now = datetime.now(tz)
    return {
        "success": True,
        "datetime": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": str(tz),
        "utc_offset": now.strftime("%z"),
        "iso_week": now.isocalendar()[1],
        "unix_timestamp": int(now.timestamp()),
    }


# ── Outlook backend ───────────────────────────────────────────────────────────

def _outlook_get_events(days: int) -> dict:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return {"success": False, "error": "pywin32 not installed — run: pip install pywin32"}

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        cal = ns.GetDefaultFolder(9)  # olFolderCalendar = 9
        items = cal.Items
        items.IncludeRecurrences = True
        items.Sort("[Start]")

        now = datetime.now()
        end = now + timedelta(days=days)
        restriction = (
            f"[Start] >= '{now.strftime('%Y-%m-%d')}' "
            f"AND [Start] <= '{end.strftime('%Y-%m-%d')}'"
        )
        filtered = items.Restrict(restriction)

        events = []
        for item in filtered:
            try:
                events.append({
                    "subject": item.Subject,
                    "start": str(item.Start),
                    "end": str(item.End),
                    "location": item.Location or "",
                    "body": (item.Body or "")[:200],
                    "all_day": item.AllDayEvent,
                    "organizer": getattr(item, "Organizer", ""),
                })
            except Exception:
                continue

        return {"success": True, "events": events, "count": len(events)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _outlook_create_event(subject: str, start: str, end: str,
                          location: str, body: str, all_day: bool) -> dict:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return {"success": False, "error": "pywin32 not installed"}

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        appt = outlook.CreateItem(1)  # olAppointmentItem = 1
        appt.Subject = subject
        appt.Start = start
        appt.End = end
        if location:
            appt.Location = location
        if body:
            appt.Body = body
        appt.AllDayEvent = all_day
        appt.Save()
        return {"success": True, "subject": subject, "start": start, "end": end}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _outlook_delete_event(subject: str, date: str) -> dict:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return {"success": False, "error": "pywin32 not installed"}

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        cal = ns.GetDefaultFolder(9)
        items = cal.Items
        items.Sort("[Start]")
        restriction = f"[Subject] = '{subject}' AND [Start] >= '{date}'"
        filtered = items.Restrict(restriction)
        deleted = 0
        for item in filtered:
            item.Delete()
            deleted += 1
            break  # delete first match only
        if deleted:
            return {"success": True, "deleted": True, "subject": subject}
        return {"success": True, "deleted": False, "reason": "No matching event found"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── ICS backend ───────────────────────────────────────────────────────────────

def _ics_path() -> str:
    path = settings.ICS_CALENDAR_PATH
    if not path:
        import os
        path = os.path.join(os.path.expanduser("~"), "jarvis_calendar.ics")
    return path


def _ics_get_events(days: int) -> dict:
    try:
        from icalendar import Calendar  # type: ignore
        import os
        path = _ics_path()
        if not os.path.exists(path):
            return {"success": True, "events": [], "count": 0}
        with open(path, "rb") as f:
            cal = Calendar.from_ical(f.read())
        now = datetime.now()
        end = now + timedelta(days=days)
        events = []
        for comp in cal.walk():
            if comp.name != "VEVENT":
                continue
            dtstart = comp.get("DTSTART")
            if dtstart is None:
                continue
            dt = dtstart.dt
            now_local = datetime.now()
            if isinstance(dt, datetime):
                if dt.tzinfo:
                    start_dt = dt.astimezone(None).replace(tzinfo=None)
                else:
                    start_dt = dt
            else:
                from datetime import date
                start_dt = datetime.combine(dt, datetime.min.time())
            if now_local <= start_dt <= end:
                events.append({
                    "subject": str(comp.get("SUMMARY", "")),
                    "start": str(dtstart.dt),
                    "end": str(comp.get("DTEND", {}).get("dt", "") if comp.get("DTEND") else ""),
                    "location": str(comp.get("LOCATION", "")),
                    "body": str(comp.get("DESCRIPTION", ""))[:200],
                })
        events.sort(key=lambda e: e["start"])
        return {"success": True, "events": events, "count": len(events)}
    except ImportError:
        return {"success": False, "error": "icalendar not installed — run: pip install icalendar"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _ics_create_event(subject: str, start: str, end: str,
                      location: str, body: str, all_day: bool) -> dict:
    try:
        from icalendar import Calendar, Event  # type: ignore
        import os, uuid
        path = _ics_path()
        if os.path.exists(path):
            with open(path, "rb") as f:
                cal = Calendar.from_ical(f.read())
        else:
            cal = Calendar()
            cal.add("prodid", "-//JARVIS//EN")
            cal.add("version", "2.0")

        event = Event()
        event.add("summary", subject)
        event.add("uid", str(uuid.uuid4()))
        if all_day:
            from datetime import date as _date
            d = datetime.fromisoformat(start).date()
            event.add("dtstart", d)
        else:
            event.add("dtstart", datetime.fromisoformat(start))
            event.add("dtend", datetime.fromisoformat(end))
        if location:
            event.add("location", location)
        if body:
            event.add("description", body)
        cal.add_component(event)

        with open(path, "wb") as f:
            f.write(cal.to_ical())
        return {"success": True, "subject": subject, "start": start}
    except ImportError:
        return {"success": False, "error": "icalendar not installed — run: pip install icalendar"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _ics_delete_event(subject: str, date: str) -> dict:
    try:
        from icalendar import Calendar  # type: ignore
        import os
        path = _ics_path()
        if not os.path.exists(path):
            return {"success": True, "deleted": False, "reason": "Calendar file not found"}
        with open(path, "rb") as f:
            cal = Calendar.from_ical(f.read())

        new_cal = Calendar()
        for k, v in cal.items():
            new_cal.add(k, v)
        deleted = 0
        for comp in cal.walk():
            if comp.name == "VEVENT":
                if subject.lower() in str(comp.get("SUMMARY", "")).lower():
                    deleted += 1
                    continue
            if comp.name != "VCALENDAR":
                new_cal.add_component(comp)

        with open(path, "wb") as f:
            f.write(new_cal.to_ical())
        return {"success": True, "deleted": deleted > 0, "count_removed": deleted}
    except ImportError:
        return {"success": False, "error": "icalendar not installed — run: pip install icalendar"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── public API ────────────────────────────────────────────────────────────────

def time_calendar(
    action: str = "get_time",
    subject: str = "",
    start: str = "",
    end: str = "",
    location: str = "",
    body: str = "",
    all_day: bool = False,
    days: int = 7,
    date: str = "",
) -> dict:
    """
    Time awareness and calendar management.

    Parameters
    ----------
    action : str
        ``get_time`` | ``get_events`` | ``create_event`` | ``delete_event``.
    subject : str
        Event title (required for create/delete).
    start : str
        ISO datetime string e.g. ``2025-05-10T14:00:00`` (required for create).
    end : str
        ISO datetime string (required for create unless all_day).
    location : str
        Optional venue for create.
    body : str
        Optional notes/description for create.
    all_day : bool
        True to create an all-day event.
    days : int
        How many days ahead to fetch events (default 7).
    date : str
        Date filter for delete (YYYY-MM-DD).

    Returns
    -------
    dict
        Always contains ``success``.  See action docstrings for specific fields.
    """
    logger.info(f"time_calendar: action={action}")
    backend = settings.CALENDAR_BACKEND.lower()

    try:
        if action == "get_time":
            return _action_get_time()

        elif action == "get_events":
            if backend == "outlook":
                return _outlook_get_events(days)
            else:
                return _ics_get_events(days)

        elif action == "create_event":
            if not subject:
                return {"success": False, "error": "subject is required"}
            if not start:
                return {"success": False, "error": "start datetime is required"}
            if not end and not all_day:
                # Default: 1-hour event
                end = (datetime.fromisoformat(start) + timedelta(hours=1)).isoformat()
            if backend == "outlook":
                return _outlook_create_event(subject, start, end, location, body, all_day)
            else:
                return _ics_create_event(subject, start, end, location, body, all_day)

        elif action == "delete_event":
            if not subject:
                return {"success": False, "error": "subject is required for delete"}
            if backend == "outlook":
                return _outlook_delete_event(subject, date or datetime.now().strftime("%Y-%m-%d"))
            else:
                return _ics_delete_event(subject, date)

        else:
            return {"success": False, "error": f"Unknown action '{action}'"}

    except Exception as exc:
        logger.error(f"time_calendar error: {exc}")
        return {"success": False, "error": str(exc)}
