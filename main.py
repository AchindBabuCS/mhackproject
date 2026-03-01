from fastapi import FastAPI, HTTPException
from database import supabase
from schemas import RegistrationCreate, EventCreate

app = FastAPI()

@app.post("/events/")
async def create_event(event: EventCreate):
    # Initialize available_seats to match total_seats
    data = supabase.table("events").insert({
        "title": event.title,
        "total_seats": event.total_seats,
        "available_seats": event.total_seats
    }).execute()
    return data.data

@app.post("/register/")
async def register_for_event(reg: RegistrationCreate):
    # 1. Check if seats are available
    event_query = supabase.table("events").select("available_seats").eq("id", reg.event_id).single().execute()
    
    if not event_query.data or event_query.data['available_seats'] <= 0:
        raise HTTPException(status_code=400, detail="Event is full or does not exist!")

    # 2. Register the user
    # In a real app, you'd get the user_id from the Supabase Auth session
    registration_data = {
        "event_id": reg.event_id,
        "user_email": reg.email
    }
    
    reg_response = supabase.table("registrations").insert(registration_data).execute()

    # 3. Decrement the seat count
    new_seat_count = event_query.data['available_seats'] - 1
    supabase.table("events").update({"available_seats": new_seat_count}).eq("id", reg.event_id).execute()

    return {"message": "Registration successful!", "data": reg_response.data}