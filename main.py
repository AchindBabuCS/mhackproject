from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
import uuid

from database import SessionLocal
from models import User, Todo
from services import hash_password

app = FastAPI()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# DB Dependency
# -----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------
# Schemas
# -----------------------------
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TodoCreate(BaseModel):
    user_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def root():
    return {"message": "hi"}

@app.post("/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):

    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        name=user.name,
        email=user.email,
        password_hash=hash_password(user.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "id": new_user.id,
        "name": new_user.name,
        "email": new_user.email
    }


@app.post("/todos")
def create_todo(todo: TodoCreate, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.id == todo.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_todo = Todo(
        user_id=todo.user_id,
        title=todo.title,
        description=todo.description
    )

    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)

    return {
        "id": new_todo.id,
        "user_id": new_todo.user_id,
        "title": new_todo.title,
        "description": new_todo.description,
        "completed": new_todo.completed,
        "created_at": new_todo.created_at
    }


@app.get("/users/{user_id}/todos")
def get_user_todos(user_id: uuid.UUID, db: Session = Depends(get_db)):

    todos = db.query(Todo).filter(Todo.user_id == user_id).all()

    return todos

@app.get("/users")
def get_users(db: Session = Depends(get_db)):

    users = db.query(User).all()

    return [
        {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "created_at": user.created_at
        }
        for user in users
    ]

@app.delete("/users/{user_id}/todos/{todo_id}")
def delete_user_todo(user_id: uuid.UUID, todo_id: uuid.UUID, db: Session = Depends(get_db)):

    todo = (
        db.query(Todo)
        .filter(Todo.id == todo_id, Todo.user_id == user_id)
        .first()
    )

    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    db.delete(todo)
    db.commit()

    return {"message": "Todo deleted successfully"}