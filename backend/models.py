from pydantic import BaseModel
from typing import Optional

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class LifeGoalCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: Optional[int] = 5
    stress: Optional[int] = 5
    status: Optional[str] = "active"

class UserStateCreate(BaseModel):
    food: Optional[str] = ""
    exercise: Optional[str] = ""
    sleep: Optional[str] = ""
    energy: Optional[int] = 5
    soreness: Optional[int] = 1
    sickness: Optional[int] = 1
    notes: Optional[str] = ""

class OneTimeTaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None
    estimated_minutes: Optional[int] = None
    cognitive_load: Optional[int] = 5
    life_goal_ids: Optional[list[int]] = []

class RecurringTaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    interval_days: Optional[int] = 7
    estimated_minutes: Optional[int] = None
    cognitive_load: Optional[int] = 5
    life_goal_ids: Optional[list[int]] = []

class DataUpdate(BaseModel):
    data: dict

class ApiKeyUpdate(BaseModel):
    openai_api_key: Optional[str] = None

class HelpArticleCreate(BaseModel):
    slug: str
    title: str
    body: str
    category: Optional[str] = "general"
    order: Optional[int] = 0
