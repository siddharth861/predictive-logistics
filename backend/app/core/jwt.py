import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt


SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "development-only-secret-key",
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(
    data: dict,
) -> str:
    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def create_refresh_token(
    data: dict,
) -> str:
    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    payload.update(
        {
            "exp": expire,
            "type": "refresh",
        }
    )

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(
    token: str,
) -> dict | None:
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except JWTError:
        return None