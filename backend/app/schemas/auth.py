from pydantic import BaseModel, EmailStr, Field

from app.schemas.business import BusinessRead
from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    businesses: list[BusinessRead]


class MeResponse(BaseModel):
    user: UserRead
    businesses: list[BusinessRead]
