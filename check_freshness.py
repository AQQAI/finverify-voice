"""
Which facts expire soon? Run before a demo or daily (cron / CI).
  python check_freshness.py          # warn about facts expiring within 30 days
  python check_freshness.py 60       # custom window
Exit code 1 if any fact has already expired, so CI can block a deploy.
"""
import datetime as dt
import sys

import engine


def main(days: int = 30) -> int:
    today = engine.today()
    rows = [(f["id"], f["valid_until"], f.get("confidence", ""),
             any(s.get("type") == "primary" for s in f["sources"])) for f in engine.STORE["facts"]]
    rows.append(("tax_calculator", engine.STORE["tax_calculator"]["valid_until"], "", False))
    expired = 0
    for fid, until, conf, primary in sorted(rows, key=lambda r: r[1]):
        left = (dt.date.fromisoformat(until) - today).days
        if left < 0:
            state, expired = "EXPIRED", expired + 1
        elif left <= days:
            state = f"expires in {left} days"
        else:
            state = "ok"
        flag = "  (single source: confirm)" if conf == "single-source" else ("" if primary else "  (no official source yet)")
        print(f"{state:<20} {until}  {fid}{flag}")
    print(f"\nToday: {today}. {expired} expired.")
    return 1 if expired else 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
