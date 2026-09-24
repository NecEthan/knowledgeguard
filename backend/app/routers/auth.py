from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.base import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services.auth import (
    create_session,
    hash_password,
    invalidate_session,
    verify_password,
)

router = APIRouter(tags=["auth"])


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session = await create_session(db, user.id)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.session_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="strict",
        max_age=settings.session_max_age_hours * 3600, # 24 hours
        path="/",
    )
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await invalidate_session(db, token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="strict",
    )


@router.get("/user", response_model=UserResponse)
async def get_user(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
