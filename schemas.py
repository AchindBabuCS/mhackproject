from pydantic import BaseModel, EmailStr

class EventCreate(BaseModel):
    title: str
    total_seats: int

class RegistrationCreate(BaseModel):
    event_id: str
    email: EmailStr