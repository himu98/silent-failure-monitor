import csv, random, sys
from datetime import datetime, timedelta

random.seed(7)
# anchored to the real current date so Make's "last 8 hours" filter finds data
NOW = datetime(2026, 7, 28, 16, 0)   # Tuesday 4pm

def generate(path, break_hours_ago=None):
    rows = []
    d = NOW - timedelta(days=63)
    while d < NOW:
        if d.weekday() < 5 and 9 <= d.hour < 18:
            base = 1.6 if d.hour in (10, 11, 14, 15) else 0.9
            for _ in range(max(0, int(random.gauss(base, 0.7)))):
                ts = d + timedelta(minutes=random.randint(0, 59))
                if break_hours_ago and ts > NOW - timedelta(hours=break_hours_ago):
                    continue
                rows.append(ts)
        d += timedelta(hours=1)
    rows.sort()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "source", "name"])
        for i, ts in enumerate(rows):
            w.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), "website_contact_form", f"Lead {i+1}"])
    print(f"{path}: {len(rows)} events, last = {rows[-1]}")

generate("sample_data/form_submissions_healthy.csv")
generate("sample_data/form_submissions_broken.csv", break_hours_ago=30)
