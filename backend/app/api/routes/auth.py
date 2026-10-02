from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    require_role,
)
from app.core.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.security import (
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.db.dependencies import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


REFRESH_TOKEN_EXPIRE_DAYS = 7


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(
        select(User).where(User.email == request.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "User registered successfully",
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role.value,
    }


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.email == request.email)
    )

    if not user or not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )

    db.add(refresh_token_record)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    payload = decode_token(request.refresh_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    stored_tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()

    matching_token = None

    for stored_token in stored_tokens:
        if verify_refresh_token(
            request.refresh_token,
            stored_token.token_hash,
        ):
            matching_token = stored_token
            break

    if not matching_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked or is invalid",
        )

    if matching_token.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    user = db.get(User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable",
        )

    matching_token.revoked_at = datetime.now(timezone.utc)

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    }

    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    new_refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )

    db.add(new_refresh_token_record)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout")
def logout(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    payload = decode_token(request.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")

    stored_tokens = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()

    for stored_token in stored_tokens:
        if verify_refresh_token(
            request.refresh_token,
            stored_token.token_hash,
        ):
            stored_token.revoked_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "message": "Logged out successfully",
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token is invalid or already revoked",
    )


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "is_active": current_user.is_active,
    }


@router.get("/admin-check")
def admin_check(
    current_user: User = Depends(
        require_role(UserRole.DATA_ADMIN)
    ),
):
    return {
        "message": "DATA_ADMIN access granted",
        "user": current_user.email,
        "role": current_user.role.value,
    }