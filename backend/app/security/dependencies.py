import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import BusinessRole
from app.models.user import User
from app.security.jwt import TokenError, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolves the authenticated user from a Bearer JWT. This is the ONLY
    place a request establishes identity — every downstream authorization
    check (business membership, role) is derived from this, never from a
    client-supplied user id.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    return user


async def get_current_membership(
    x_business_id: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessMember:
    """Resolves the caller's role for the business named by the X-Business-Id
    header. The business id always comes from an authenticated, server-side
    membership lookup — never trusted as "this user has this role" from the
    client. Returns 403 (not 404) on a non-member business id so an
    unauthorized caller cannot distinguish "doesn't exist" from "not yours."
    """
    if not x_business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="X-Business-Id header is required"
        )
    try:
        business_id = uuid.UUID(x_business_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="X-Business-Id is not a valid UUID"
        ) from exc

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this business",
        )
    return membership


def require_role(*allowed_roles: BusinessRole) -> Callable:
    """Dependency factory: 403s unless the caller's role for the active
    business is one of allowed_roles. Role is read from the server-resolved
    membership row, never from a request body/header.
    """

    async def _check(membership: BusinessMember = Depends(get_current_membership)) -> BusinessMember:
        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return membership

    return _check
