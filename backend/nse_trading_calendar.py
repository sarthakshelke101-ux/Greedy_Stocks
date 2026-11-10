
import argparse

from datetime import datetime, date


# Official NSE Capital Market (Equity) holidays for 2026.
# Source: NSE Circular NSE/CMTR/71775, December 12, 2025.

NSE_HOLIDAYS = {
    2026: {
        "2026-01-15": "Municipal Corporation Election - Maharashtra",
        "2026-01-26": "Republic Day",
        "2026-03-03": "Holi",
        "2026-03-26": "Shri Ram Navami",
        "2026-03-31": "Shri Mahavir Jayanti",
        "2026-04-03": "Good Friday",
        "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2026-05-01": "Maharashtra Day",
        "2026-05-28": "Bakri Id",
        "2026-06-26": "Muharram",
        "2026-09-14": "Ganesh Chaturthi",
        "2026-10-02": "Mahatma Gandhi Jayanti",
        "2026-10-20": "Dussehra",
        "2026-11-10": "Diwali-Balipratipada",
        "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
        "2026-12-25": "Christmas",
    }
}


# Special trading sessions are recorded separately.
# They are NOT automatically treated as normal daily sessions.
SPECIAL_SESSIONS = {
    "2026-11-08": "Diwali Laxmi Pujan - Muhurat Trading"
}


def get_session_status(target_date):
    """
    Return the NSE Capital Market session status for a date.

    Possible results:
    REGULAR_SESSION
    WEEKEND_CLOSED
    NSE_HOLIDAY
    SPECIAL_SESSION_REQUIRES_CONFIRMATION
    CALENDAR_NOT_CONFIGURED
    """

    if isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)

    year = target_date.year
    date_text = target_date.isoformat()

    # Never assume holidays for an unconfigured year.
    if year not in NSE_HOLIDAYS:
        return {
            "status": "CALENDAR_NOT_CONFIGURED",
            "date": date_text,
            "reason": (
                f"Official NSE holiday calendar for {year} "
                "has not been configured."
            ),
        }

    # Special sessions need separate confirmation.
    if date_text in SPECIAL_SESSIONS:
        return {
            "status": "SPECIAL_SESSION_REQUIRES_CONFIRMATION",
            "date": date_text,
            "reason": SPECIAL_SESSIONS[date_text],
        }

    # Saturday and Sunday are normally closed.
    if target_date.weekday() >= 5:
        return {
            "status": "WEEKEND_CLOSED",
            "date": date_text,
            "reason": "NSE Capital Market normally remains closed.",
        }

    # Official NSE holidays.
    if date_text in NSE_HOLIDAYS[year]:
        return {
            "status": "NSE_HOLIDAY",
            "date": date_text,
            "reason": NSE_HOLIDAYS[year][date_text],
        }

    return {
        "status": "REGULAR_SESSION",
        "date": date_text,
        "reason": "Regular NSE Capital Market trading day.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="GREEDY STOCKS - NSE Trading Calendar"
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Date in YYYYMMDD format.",
    )

    args = parser.parse_args()

    try:
        target_date = datetime.strptime(
            args.date,
            "%Y%m%d",
        ).date()

    except ValueError:
        parser.error("Date must be a valid YYYYMMDD date.")

    result = get_session_status(target_date)

    print("=" * 60)
    print("GREEDY STOCKS - NSE TRADING CALENDAR")
    print("=" * 60)
    print("Date:", result["date"])
    print("Status:", result["status"])
    print("Reason:", result["reason"])
    print("=" * 60)

    if result["status"] == "CALENDAR_NOT_CONFIGURED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
