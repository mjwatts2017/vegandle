import os
import random
import hmac
import secrets
import time
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

# ---------- config (all overridable with environment variables) ----------
DB_URL = os.getenv("DATABASE_URL", "sqlite:///vegandle.db").replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg2://", 1)
TZ = ZoneInfo(os.getenv("GAME_TZ", "America/New_York"))  # one "midnight" for everyone
LAUNCH = date.fromisoformat(os.getenv("LAUNCH_DATE", "2026-10-06"))  # puzzle #1
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me").strip().strip("\"'")  # ignore stray spaces/quotes
PROD = os.getenv("APP_ENV", "dev") == "production"  # set APP_ENV=production when deployed
ADMIN_PATH = "/" + os.getenv("ADMIN_PATH", "/admin").strip("/")  # change it to hide it further
SESSION_HOURS, MAX_FAILS, LOCKOUT_SECONDS = 12, 5, 15 * 60
print(f"startup check: prod={PROD} password_set={'ADMIN_PASSWORD' in os.environ} "
      f"password_length={len(ADMIN_PASSWORD)}", flush=True)  # never prints the password itself
if PROD and ADMIN_PASSWORD == "change-me":
    raise RuntimeError("Set ADMIN_PASSWORD before running in production")
ROUNDS = 5
Answer = Literal["vegan", "probably", "not"]


# ---------- database ----------
class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    emoji: Mapped[str] = mapped_column(default="🍽️")  # fallback when there's no image
    image_url: Mapped[str] = mapped_column(default="")
    image_credit: Mapped[str] = mapped_column(default="")
    answer: Mapped[str]  # vegan | probably | not
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="draft")  # draft | approved


class Day(Base):
    __tablename__ = "days"
    date: Mapped[str] = mapped_column(primary_key=True)  # YYYY-MM-DD
    item_ids: Mapped[str]  # "3,9,1,4,7" (order = round order)


engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
Base.metadata.create_all(engine)


def get_db():
    with SessionLocal() as db:
        yield db


def today() -> date:
    return datetime.now(TZ).date()


# ---------- scheduler: fills upcoming days from APPROVED items ----------
def ensure_schedule(db: Session, days: int = 14) -> None:
    """Fill any empty upcoming days. Picks the least-recently-used approved items,
    so the bank rotates evenly. Days you've edited by hand are never overwritten."""
    approved = [i.id for i in db.scalars(select(Item).where(Item.status == "approved"))]
    if len(approved) < ROUNDS:
        return
    last_used: dict[int, str] = {}
    for d in db.scalars(select(Day)):
        for i in d.item_ids.split(","):
            last_used[int(i)] = max(last_used.get(int(i), ""), d.date)
    for n in range(days):
        d = (today() + timedelta(n)).isoformat()
        if db.get(Day, d):
            continue
        pool = sorted(approved, key=lambda i: (last_used.get(i, ""), random.random()))[:ROUNDS]
        random.shuffle(pool)
        db.add(Day(date=d, item_ids=",".join(map(str, pool))))
        for i in pool:
            last_used[i] = d
    db.commit()


# ---------- app ----------
app = FastAPI(title="Vegandle", redoc_url=None,
              docs_url=None if PROD else "/docs", openapi_url=None if PROD else "/openapi.json")

# Game front end on another domain (Netlify) may call the PUBLIC game API only.
# The admin page is served from this same server, so it needs no CORS.
ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], allow_credentials=False)


class Guess(BaseModel):
    round: int
    guess: Answer


@app.get("/api/puzzle/today")
def get_today(db: Session = Depends(get_db)):
    ensure_schedule(db)
    d = today()
    day = db.get(Day, d.isoformat())
    if not day:
        raise HTTPException(503, "No puzzle scheduled yet")
    items = [db.get(Item, int(i)) for i in day.item_ids.split(",")]
    return {
        "date": d.isoformat(),
        "number": (d - LAUNCH).days + 1,
        # answers are deliberately NOT included; they're revealed one round at a time
        "items": [
            {"name": i.name, "description": i.description, "emoji": i.emoji,
             "image_url": i.image_url, "image_credit": i.image_credit}
            for i in items
        ],
    }


@app.post("/api/puzzle/{day}/check")
def check(day: str, body: Guess, db: Session = Depends(get_db)):
    if day != today().isoformat():  # no peeking at other days
        raise HTTPException(400, "Only today's puzzle can be played")
    row = db.get(Day, day)
    ids = row.item_ids.split(",") if row else []
    if not 0 <= body.round < len(ids):
        raise HTTPException(400, "Bad round")
    item = db.get(Item, int(ids[body.round]))
    return {"correct": body.guess == item.answer, "answer": item.answer, "explanation": item.explanation}


# ---------- admin (send the password in an X-Admin-Password header) ----------
FAILS: dict[str, list[float]] = {}  # ip -> recent failed login times (in memory)


def same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode(), b.encode())


def sign(exp: str) -> str:
    # signed with the password, so changing ADMIN_PASSWORD logs everyone out
    return hmac.new(f"vegandle-session:{ADMIN_PASSWORD}".encode(), exp.encode(), "sha256").hexdigest()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[-1].strip() or (request.client.host if request.client else "?")


def admin(request: Request, x_admin_password: str = Header("")):
    exp, _, sig = request.cookies.get("vg_admin", "").partition(".")
    if sig and exp.isdigit() and int(exp) > time.time() and same(sig, sign(exp)):
        return
    # header login only exists for local /docs testing; it is off in production
    if not PROD and x_admin_password and same(x_admin_password, ADMIN_PASSWORD):
        return
    raise HTTPException(401, "Not logged in")


class Login(BaseModel):
    password: str


@app.post("/api/admin/login")
def login(body: Login, request: Request, response: Response):
    ip, now = client_ip(request), time.time()
    recent = [t for t in FAILS.get(ip, []) if now - t < LOCKOUT_SECONDS]
    if len(recent) >= MAX_FAILS:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    if not same(body.password.strip(), ADMIN_PASSWORD):
        FAILS[ip] = recent + [now]
        raise HTTPException(401, "Wrong password")
    FAILS.pop(ip, None)
    exp = str(int(now) + SESSION_HOURS * 3600)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie("vg_admin", f"{exp}.{sign(exp)}", max_age=SESSION_HOURS * 3600,
                        httponly=True, samesite="strict", secure=secure)
    return {"ok": True}


@app.post("/api/admin/logout")
def logout(response: Response):
    response.delete_cookie("vg_admin")
    return {"ok": True}


@app.get("/api/admin/me", dependencies=[Depends(admin)])
def me():
    return {"ok": True}


@app.delete("/api/admin/items/{item_id}", dependencies=[Depends(admin)])
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "No such item")
    for d in db.scalars(select(Day).where(Day.date >= today().isoformat())):
        if str(item_id) in d.item_ids.split(","):
            raise HTTPException(409, f"Scheduled on {d.date}. Swap or re-roll that day first.")
    db.delete(item)
    db.commit()
    return {"ok": True}


class ItemIn(BaseModel):
    name: str
    description: str
    answer: Answer
    explanation: str
    emoji: str = "🍽️"
    image_url: str = ""
    image_credit: str = ""
    status: Literal["draft", "approved"] = "draft"


class ItemPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    answer: Optional[Answer] = None
    explanation: Optional[str] = None
    emoji: Optional[str] = None
    image_url: Optional[str] = None
    image_credit: Optional[str] = None
    status: Optional[Literal["draft", "approved"]] = None


class DayIn(BaseModel):
    item_ids: list[int]


@app.get("/api/admin/items", dependencies=[Depends(admin)])
def list_items(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(Item).order_by(Item.id)
    if status:
        q = q.where(Item.status == status)
    return [{c.name: getattr(i, c.name) for c in Item.__table__.columns} for i in db.scalars(q)]


@app.post("/api/admin/items", dependencies=[Depends(admin)])
def add_item(body: ItemIn, db: Session = Depends(get_db)):
    item = Item(**body.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id}


@app.patch("/api/admin/items/{item_id}", dependencies=[Depends(admin)])
def edit_item(item_id: int, body: ItemPatch, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "No such item")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    return {"ok": True}


@app.get("/api/admin/schedule", dependencies=[Depends(admin)])
def get_schedule(db: Session = Depends(get_db)):
    ensure_schedule(db)
    out = []
    for d in db.scalars(select(Day).where(Day.date >= today().isoformat()).order_by(Day.date)):
        items = [db.get(Item, int(i)) for i in d.item_ids.split(",")]
        out.append({"date": d.date, "items": [{"id": i.id, "name": i.name} for i in items]})
    return out


@app.put("/api/admin/schedule/{day}", dependencies=[Depends(admin)])
def set_day(day: str, body: DayIn, db: Session = Depends(get_db)):
    """Swap in specific items for a date (exactly 5 distinct, existing items)."""
    date.fromisoformat(day)
    if len(set(body.item_ids)) != ROUNDS or any(not db.get(Item, i) for i in body.item_ids):
        raise HTTPException(400, f"Need {ROUNDS} distinct, existing item ids")
    db.merge(Day(date=day, item_ids=",".join(map(str, body.item_ids))))
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/schedule/{day}", dependencies=[Depends(admin)])
def clear_day(day: str, db: Session = Depends(get_db)):
    """Clear a day so the scheduler re-fills it automatically."""
    row = db.get(Day, day)
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


# the admin page: not linked anywhere, not indexed, and useless without the password
@app.get(ADMIN_PATH, include_in_schema=False)
def admin_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "admin", "index.html"),
                        headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})


# the game itself (must be mounted last so /api routes win)
FRONTEND = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True))
