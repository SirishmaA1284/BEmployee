from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.schemas.business import BusinessRead
from app.schemas.user import UserRead
from app.security.dependencies import get_current_user
from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _businesses_for_user(db: AsyncSession, user_id) -> list[BusinessRead]:
    result = await db.execute(
        select(Business, BusinessMember.role)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == user_id)
    )
    return [
        BusinessRead(id=b.id, name=b.name, currency=b.currency, role=role)
        for b, role in result.all()
    ]


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        )

    try:
        hashed = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    user = User(email=payload.email, hashed_password=hashed, full_name=payload.full_name)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserRead.model_validate(user), businesses=[])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Constant-shape response whether the email doesn't exist or the password
    # is wrong, so login can't be used to enumerate registered emails.
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )

    token = create_access_token(user.id)
    businesses = await _businesses_for_user(db, user.id)
    return TokenResponse(access_token=token, user=UserRead.model_validate(user), businesses=businesses)


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    businesses = await _businesses_for_user(db, current_user.id)
    return MeResponse(user=UserRead.model_validate(current_user), businesses=businesses)
