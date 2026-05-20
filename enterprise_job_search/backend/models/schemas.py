from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    
    class Config:
        from_attributes = True

# We'll add Resume and Job schemas later as needed
