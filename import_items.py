"""Bulk-import items from a JSON file.

    python import_items.py items_batch1.json             # loads as drafts
    python import_items.py items_batch1.json --approve   # loads as approved

Names already in the database are skipped, so it's safe to run twice.
"""
import json
import sys

from sqlalchemy import select

from main import Item, SessionLocal

REQUIRED = ("name", "description", "answer", "explanation")
status = "approved" if "--approve" in sys.argv else "draft"
rows = json.load(open(sys.argv[1], encoding="utf-8"))

with SessionLocal() as db:
    have = {n.lower() for n in db.scalars(select(Item.name))}
    added = skipped = 0
    for r in rows:
        if any(not r.get(k) for k in REQUIRED) or r["answer"] not in ("vegan", "probably", "not"):
            print("Skipping invalid entry:", r.get("name", r))
            continue
        if r["name"].lower() in have:
            skipped += 1
            continue
        db.add(Item(name=r["name"], description=r["description"], emoji=r.get("emoji", "🍽️"),
                    image_url=r.get("image_url", ""), image_credit=r.get("image_credit", ""),
                    answer=r["answer"], explanation=r["explanation"], status=status))
        have.add(r["name"].lower())
        added += 1
    db.commit()
    print(f"Added {added} as {status}, skipped {skipped} duplicates.")
