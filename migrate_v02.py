"""Run ONCE, BEFORE pushing v0.2:   python migrate_v02.py
Adds the gray_area column and turns every "probably" item into vegan + gray area.
To migrate production, set DATABASE_URL to your Neon string first (same as when you seeded)."""
from sqlalchemy import inspect, text

from main import engine

with engine.begin() as c:
    if "gray_area" not in [x["name"] for x in inspect(c).get_columns("items")]:
        c.execute(text("ALTER TABLE items ADD COLUMN gray_area BOOLEAN DEFAULT FALSE"))
    n = c.execute(text("UPDATE items SET gray_area = TRUE, answer = 'vegan' WHERE answer = 'probably'")).rowcount
print(f"Done. Converted {n} 'probably' items to vegan + gray area.")
