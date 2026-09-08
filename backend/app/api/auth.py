from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.business import BusinessRead
from app.schemas.user import UserRead
from app.security.dependencies import get_current_user
from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password
from app.security.rate_limit import rate_limit
from app.services.errors import BusinessRuleError
from app.services.refresh_token_service import (
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    # Best-effort client IP for the refresh-token audit row. Behind a proxy
    # this would read X-Forwarded-For (trusted proxies only); locally the
    # direct peer is fine.
    return request.client.host if request.client else None


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
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(limit=10, window_seconds=60)),
) -> TokenResponse:
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

    access = create_access_token(user.id)
    refresh, _ = await issue_refresh_token(db, user_id=user.id, created_ip=_client_ip(request))
    await db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserRead.model_validate(user),
        businesses=[],
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(limit=10, window_seconds=60)),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Constant-shape response whether the email doesn't exist or the password
    # is wrong, so login can't be used to enumerate registered emails.
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )

    access = create_access_token(user.id)
    refresh, _ = await issue_refresh_token(db, user_id=user.id, created_ip=_client_ip(request))
    await db.commit()
    businesses = await _businesses_for_user(db, user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserRead.model_validate(user),
        businesses=businesses,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(limit=30, window_seconds=60)),
) -> RefreshResponse:
    """Rotate a refresh token: validate + revoke the presented token, issue a
    replacement and a fresh access token. Rotation means a replayed/leaked
    refresh token is rejected on its second use.
    """
    try:
        new_refresh, _, user_id = await rotate_refresh_token(
            db, token=payload.refresh_token, created_ip=_client_ip(request)
        )
    except BusinessRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await db.commit()
    return RefreshResponse(
        access_token=create_access_token(user_id),
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> None:
    """Revoke a refresh token (idempotent). The access token remains valid
    until it expires (short-lived by design); the refresh token is dead.
    """
    await revoke_refresh_token(db, token=payload.refresh_token)
    await db.commit()


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    businesses = await _businesses_for_user(db, current_user.id)
    return MeResponse(user=UserRead.model_validate(current_user), businesses=businesses)
