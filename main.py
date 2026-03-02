from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from supabase import create_client
from dotenv import load_dotenv
from typing import Optional
import os
import random
import string

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

app = FastAPI(title="EventArc API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[str] = "user"  # "user" or "admin"

class LoginRequest(BaseModel):
    username: str
    password: str

class EventCreate(BaseModel):
    title: str
    category: str
    price: str
    date: str
    time: str
    location: str
    total_seats: int
    description: str

class EventUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    price: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    total_seats: Optional[int] = None
    description: Optional[str] = None

class ProfileUpdate(BaseModel):
    user_id: str
    display_name: str
    email: str

class RatingSubmit(BaseModel):
    user_id: str
    event_id: str
    rating: int

class AdjustSeats(BaseModel):
    delta: int


# ─────────────────────────────────────────
# ROOT
# ─────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "EventArc API is running"}


# ─────────────────────────────────────────
# AUTH — SIGNUP
# ─────────────────────────────────────────

@app.post("/signup")
def signup(data: SignupRequest):
    existing_user = supabase.table("users").select("id").eq("username", data.username).execute()
    if existing_user.data:
        raise HTTPException(status_code=400, detail="Username already taken")

    existing_email = supabase.table("users").select("id").eq("email", data.email).execute()
    if existing_email.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        auth_res = supabase.auth.sign_up({"email": data.email, "password": data.password})
        uid = auth_res.user.id
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Auth error: {str(e)}")

    safe_role = data.role if data.role in ["user", "admin"] else "user"

    supabase.table("users").insert({
        "id": uid,
        "username": data.username,
        "email": data.email,
        "display_name": data.username,
        "role": safe_role
    }).execute()

    return {
        "message": "Account created successfully",
        "user_id": uid,
        "username": data.username,
        "role": safe_role
    }


# ─────────────────────────────────────────
# AUTH — LOGIN
# ─────────────────────────────────────────

@app.post("/login")
def login(data: LoginRequest):
    user_res = supabase.table("users").select("*").eq("username", data.username).execute()
    if not user_res.data:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user = user_res.data[0]

    try:
        supabase.auth.sign_in_with_password({
            "email": user["email"],
            "password": data.password
        })
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {
        "message": "Login successful",
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "email": user["email"],
        "role": user.get("role", "user")
    }


# ─────────────────────────────────────────
# EVENTS — LIST ALL
# ─────────────────────────────────────────

@app.get("/events")
def list_events():
    res = supabase.table("events").select("*").order("created_at", desc=False).execute()
    return res.data


# ─────────────────────────────────────────
# EVENTS — CREATE
# ─────────────────────────────────────────

@app.post("/events")
def create_event(event: EventCreate):
    res = supabase.table("events").insert({
        "title": event.title,
        "category": event.category,
        "price": event.price,
        "date": event.date,
        "time": event.time,
        "location": event.location,
        "total_seats": event.total_seats,
        "available_seats": event.total_seats,
        "description": event.description
    }).execute()
    return {"message": "Event created", "data": res.data[0]}


# ─────────────────────────────────────────
# EVENTS — EDIT
# ─────────────────────────────────────────

@app.put("/events/{event_id}")
def update_event(event_id: str, event: EventUpdate):
    current = supabase.table("events").select("*").eq("id", event_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Event not found")

    update_data = {k: v for k, v in event.dict().items() if v is not None}

    if "total_seats" in update_data:
        old_total = current.data["total_seats"]
        old_available = current.data["available_seats"]
        taken = old_total - old_available
        new_available = max(0, update_data["total_seats"] - taken)
        update_data["available_seats"] = new_available

    res = supabase.table("events").update(update_data).eq("id", event_id).execute()
    return {"message": "Event updated", "data": res.data[0]}


# ─────────────────────────────────────────
# EVENTS — DELETE
# ─────────────────────────────────────────

@app.delete("/events/{event_id}")
def delete_event(event_id: str):
    supabase.table("registrations").delete().eq("event_id", event_id).execute()
    supabase.table("waitlist").delete().eq("event_id", event_id).execute()
    supabase.table("events").delete().eq("id", event_id).execute()
    return {"message": "Event deleted"}


# ─────────────────────────────────────────
# EVENTS — ADJUST SEATS
# ─────────────────────────────────────────

@app.post("/events/{event_id}/adjust-seats")
def adjust_seats(event_id: str, body: AdjustSeats):
    event = supabase.table("events").select("*").eq("id", event_id).single().execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    e = event.data
    new_available = e["available_seats"] + body.delta

    if new_available < 0:
        raise HTTPException(status_code=400, detail="Cannot go below 0 seats")
    if new_available > e["total_seats"]:
        raise HTTPException(status_code=400, detail="Cannot exceed total seats")

    supabase.table("events").update({"available_seats": new_available}).eq("id", event_id).execute()
    return {"message": "Seats updated", "available_seats": new_available}


# ─────────────────────────────────────────
# REGISTER FOR EVENT
# ─────────────────────────────────────────

@app.post("/events/{event_id}/register")
def register(event_id: str, user_id: str):
    event = supabase.table("events").select("*").eq("id", event_id).single().execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    e = event.data

    already = supabase.table("registrations").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
    if already.data:
        raise HTTPException(status_code=400, detail="Already registered for this event")

    if e["available_seats"] <= 0:
        raise HTTPException(status_code=400, detail="No seats available")

    ticket_id = "EVT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))

    supabase.table("registrations").insert({
        "event_id": event_id,
        "user_id": user_id,
        "ticket_id": ticket_id
    }).execute()

    supabase.table("events").update({
        "available_seats": e["available_seats"] - 1
    }).eq("id", event_id).execute()

    return {
        "message": "Registration successful",
        "ticket_id": ticket_id,
        "seats_remaining": e["available_seats"] - 1
    }


# ─────────────────────────────────────────
# CANCEL REGISTRATION
# ─────────────────────────────────────────

@app.delete("/events/{event_id}/register")
def cancel_registration(event_id: str, user_id: str):
    reg = supabase.table("registrations").select("*").eq("event_id", event_id).eq("user_id", user_id).execute()
    if not reg.data:
        raise HTTPException(status_code=404, detail="Registration not found")

    supabase.table("registrations").delete().eq("event_id", event_id).eq("user_id", user_id).execute()

    event = supabase.table("events").select("available_seats").eq("id", event_id).single().execute()
    new_available = event.data["available_seats"] + 1
    supabase.table("events").update({"available_seats": new_available}).eq("id", event_id).execute()

    # Promote first person on waitlist if any
    waitlist = supabase.table("waitlist").select("*").eq("event_id", event_id).order("created_at").limit(1).execute()
    if waitlist.data:
        next_user = waitlist.data[0]
        new_ticket = "EVT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        supabase.table("registrations").insert({
            "event_id": event_id,
            "user_id": next_user["user_id"],
            "ticket_id": new_ticket
        }).execute()
        supabase.table("waitlist").delete().eq("id", next_user["id"]).execute()
        supabase.table("events").update({"available_seats": new_available - 1}).eq("id", event_id).execute()
        return {"message": "Cancelled. Next waitlist person was promoted.", "promoted_user_id": next_user["user_id"]}

    return {"message": "Registration cancelled"}


# ─────────────────────────────────────────
# WAITLIST — JOIN
# ─────────────────────────────────────────

@app.post("/events/{event_id}/waitlist")
def join_waitlist(event_id: str, user_id: str):
    event = supabase.table("events").select("id").eq("id", event_id).single().execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    already_reg = supabase.table("registrations").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
    if already_reg.data:
        raise HTTPException(status_code=400, detail="You are already registered")

    already_wl = supabase.table("waitlist").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
    if already_wl.data:
        raise HTTPException(status_code=400, detail="Already on waitlist")

    wl_id = "WL-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    supabase.table("waitlist").insert({
        "event_id": event_id,
        "user_id": user_id,
        "ticket_id": wl_id
    }).execute()

    return {"message": "Added to waitlist", "waitlist_ticket_id": wl_id}


# ─────────────────────────────────────────
# WAITLIST — LEAVE
# ─────────────────────────────────────────

@app.delete("/events/{event_id}/waitlist")
def leave_waitlist(event_id: str, user_id: str):
    wl = supabase.table("waitlist").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
    if not wl.data:
        raise HTTPException(status_code=404, detail="Not on waitlist")

    supabase.table("waitlist").delete().eq("event_id", event_id).eq("user_id", user_id).execute()
    return {"message": "Removed from waitlist"}


# ─────────────────────────────────────────
# MY REGISTRATIONS
# ─────────────────────────────────────────

@app.get("/users/{user_id}/registrations")
def my_registrations(user_id: str):
    regs = supabase.table("registrations").select("*, events(*)").eq("user_id", user_id).execute()
    return regs.data


# ─────────────────────────────────────────
# MY WAITLIST
# ─────────────────────────────────────────

@app.get("/users/{user_id}/waitlist")
def my_waitlist(user_id: str):
    wl = supabase.table("waitlist").select("*, events(*)").eq("user_id", user_id).execute()
    return wl.data


# ─────────────────────────────────────────
# RATINGS — SUBMIT
# ─────────────────────────────────────────

@app.post("/ratings")
def submit_rating(data: RatingSubmit):
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    existing = supabase.table("ratings").select("id").eq("user_id", data.user_id).eq("event_id", data.event_id).execute()
    if existing.data:
        supabase.table("ratings").update({"rating": data.rating}).eq("user_id", data.user_id).eq("event_id", data.event_id).execute()
        return {"message": "Rating updated"}

    supabase.table("ratings").insert({
        "user_id": data.user_id,
        "event_id": data.event_id,
        "rating": data.rating
    }).execute()
    return {"message": "Rating submitted"}


# ─────────────────────────────────────────
# RATINGS — GET USER'S RATINGS
# ─────────────────────────────────────────

@app.get("/users/{user_id}/ratings")
def get_ratings(user_id: str):
    res = supabase.table("ratings").select("*").eq("user_id", user_id).execute()
    return res.data


# ─────────────────────────────────────────
# PROFILE — UPDATE
# ─────────────────────────────────────────

@app.put("/users/{user_id}/profile")
def update_profile(user_id: str, data: ProfileUpdate):
    conflict = supabase.table("users").select("id").eq("email", data.email).neq("id", user_id).execute()
    if conflict.data:
        raise HTTPException(status_code=400, detail="Email already used by another account")

    supabase.table("users").update({
        "display_name": data.display_name,
        "email": data.email
    }).eq("id", user_id).execute()

    return {"message": "Profile updated"}


# ─────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────

@app.get("/analytics")
def get_analytics():
    events = supabase.table("events").select("*").execute().data
    registrations = supabase.table("registrations").select("event_id").execute().data

    total_events = len(events)
    total_registrations = len(registrations)
    full_events = sum(1 for e in events if e["available_seats"] == 0)
    total_seats_taken = sum(e["total_seats"] - e["available_seats"] for e in events)

    revenue = 0
    for e in events:
        taken = e["total_seats"] - e["available_seats"]
        price_str = e.get("price", "Free")
        if price_str != "Free":
            try:
                price = int("".join(filter(str.isdigit, price_str)))
                revenue += price * taken
            except:
                pass

    cat_counts = {}
    for e in events:
        cat = e.get("category", "Other")
        taken = e["total_seats"] - e["available_seats"]
        cat_counts[cat] = cat_counts.get(cat, 0) + taken

    event_stats = []
    for e in events:
        taken = e["total_seats"] - e["available_seats"]
        fill_pct = round((taken / e["total_seats"]) * 100) if e["total_seats"] > 0 else 0
        event_stats.append({
            "id": e["id"],
            "title": e["title"],
            "total_seats": e["total_seats"],
            "available_seats": e["available_seats"],
            "registrations": taken,
            "fill_percent": fill_pct
        })

    return {
        "total_events": total_events,
        "total_registrations": total_registrations,
        "full_events": full_events,
        "total_seats_taken": total_seats_taken,
        "revenue": revenue,
        "category_breakdown": cat_counts,
        "event_stats": event_stats
    }