from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

@app.get("/")
def root():
    return {"message": "API is running"}

@app.post("/signup")
def signup(user: UserSignup):
    try:
        res = supabase.auth.sign_up({"email": user.email, "password": user.password})
        uid = res.user.id
        supabase.table("users").insert({"id": uid, "name": user.name, "email": user.email}).execute()
        return {"message": "Account created", "user_id": uid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
def login(credentials: UserLogin):
    try:
        res = supabase.auth.sign_in_with_password({"email": credentials.email, "password": credentials.password})
        return {"message": "Login successful", "user_id": res.user.id, "name": res.user.email}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid email or password")

@app.get("/events")
def list_events():
    res = supabase.table("events").select("*").execute()
    return res.data


@app.post("/events/{event_id}/register")
def register(event_id: str, user_id: str):
    event = supabase.table("events").select("*").eq("id", event_id).single().execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.data["available_seats"] <= 0:
        raise HTTPException(status_code=400, detail="Event is fully booked")

    already = supabase.table("registrations").select("*").eq("event_id", event_id).eq("user_id", user_id).execute()
    if already.data:
        raise HTTPException(status_code=400, detail="Already registered")

    supabase.table("registrations").insert({"event_id": event_id, "user_id": user_id}).execute()
    supabase.table("events").update({"available_seats": event.data["available_seats"] - 1}).eq("id", event_id).execute()

    return {"message": "Registered successfully", "seats_remaining": event.data["available_seats"] - 1}

@app.get("/users/{user_id}/registrations")
def my_registrations(user_id: str):
    regs = supabase.table("registrations").select("*, events(*)").eq("user_id", user_id).execute()
    return regs.data

@app.delete("/events/{event_id}/register")
def cancel(event_id: str, user_id: str):
    supabase.table("registrations").delete().eq("event_id", event_id).eq("user_id", user_id).execute()
    event = supabase.table("events").select("available_seats").eq("id", event_id).single().execute()
    supabase.table("events").update({"available_seats": event.data["available_seats"] + 1}).eq("id", event_id).execute()
    return {"message": "Registration cancelled"}