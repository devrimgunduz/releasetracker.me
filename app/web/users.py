from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import User
from ..security import hash_password
from .deps import current_user, flash, redirect, render, require_admin

router = APIRouter(prefix="/users")


@router.get("")
async def list_users(
    request: Request,
    user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    users = (await session.execute(select(User).order_by(User.username))).scalars().all()
    return render(request, "users.html", user, users=users)


@router.post("/add")
async def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if len(password) < 8:
        flash(request, "Password must be at least 8 characters.", "error")
        return redirect("/users")

    session.add(
        User(
            username=username.strip(),
            password_hash=hash_password(password),
            role="admin" if role == "admin" else "user",
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        flash(request, "That username is taken.", "error")
        return redirect("/users")

    flash(request, f"Created user “{username.strip()}”.", "success")
    return redirect("/users")


@router.post("/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if user_id == admin.id:
        flash(request, "You can't delete your own account.", "error")
        return redirect("/users")
    target = await session.get(User, user_id)
    if target:
        await session.delete(target)
        await session.commit()
        flash(request, f"Deleted “{target.username}”.", "success")
    return redirect("/users")
