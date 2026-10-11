"""Load starter items. They go in as DRAFTS so you review each one in the admin.
For local testing only:  python seed.py --approve
"""
import sys

from main import Item, SessionLocal

V, P, N = "vegan", "probably", "not"

ITEMS = [
    ("Oreo cookies", "The classic chocolate sandwich cookie with creme filling (US version).", "🍪", P,
     "No animal ingredients in the US recipe, but they're made on shared lines with milk, and US sugar may be filtered through bone char."),
    ("Gummy bears", "Chewy, fruity, bear-shaped candies from a standard candy aisle.", "🧸", N,
     "Most gummies are set with gelatin, which is made from animal collagen (skin and bones)."),
    ("Classic potato chips", "Plain salted chips: potatoes, vegetable oil and salt.", "🥔", V,
     "Just potatoes, oil and salt. The flavored varieties are where milk powder and other animal ingredients sneak in."),
    ("Red wine", "A typical bottle of red wine from the supermarket.", "🍷", P,
     "Wine itself is grapes, but fining agents like egg whites, casein (milk) or isinglass (fish bladder) may be used and aren't listed on the label."),
    ("Honey", "Golden and sweet, straight from the jar.", "🍯", N,
     "Honey is made by bees, so it's an animal product and isn't considered vegan."),
    ("White granulated sugar", "A bag of plain white sugar for baking.", "🍚", P,
     "Sugar has no animal ingredients, but some cane sugar is refined with bone char. Beet sugar never is."),
    ("Natural peanut butter", "Ingredients: peanuts, salt.", "🥜", V,
     "Nothing but peanuts and salt. (Some brands add honey, so always check the label.)"),
    ("Worcestershire sauce", "The dark, tangy sauce for steaks, Bloody Marys and Caesar dressing.", "🍶", N,
     "The traditional recipe contains fermented anchovies. Vegan versions exist, but they're labeled as such."),
    ("Dried spaghetti", "A box of dried durum wheat pasta.", "🍝", V,
     "Dried pasta is typically just durum wheat and water. Fresh egg pasta is the one to watch."),
    ("Marshmallows", "Big, fluffy, store-bought campfire marshmallows.", "☁️", N,
     "Standard marshmallows are made with gelatin, an animal-derived gelling agent."),
    ("Store-bought naan", "Soft, pillowy flatbread from the bakery aisle.", "🫓", N,
     "Most naan is made with yogurt or milk, and often brushed with ghee."),
    ("Dark chocolate bar (70%)", "A dark chocolate bar. Ingredients: cocoa mass, sugar, cocoa butter, natural flavor.", "🍫", P,
     "No milk in the recipe, but many are made on shared equipment, the sugar may be bone-char filtered, and 'natural flavor' isn't specific."),
]

with SessionLocal() as db:
    status = "approved" if "--approve" in sys.argv else "draft"
    for name, desc, emoji, answer, why in ITEMS:
        db.add(Item(name=name, description=desc, emoji=emoji, answer=answer, explanation=why, status=status))
    db.commit()
    print(f"Added {len(ITEMS)} items as {status}.")
