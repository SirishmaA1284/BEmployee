import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import BusinessRole


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    currency: str = Field(default="INR", min_length=1, max_length=8)


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    currency: str
    role: BusinessRole


class BusinessMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: BusinessRole


class BusinessMemberInvite(BaseModel):
    email: EmailStr
    role: BusinessRole = BusinessRole.EMPLOYEE
