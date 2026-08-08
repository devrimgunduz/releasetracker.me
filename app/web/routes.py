from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..csrf import verify_csrf
from ..db import get_session
from ..models import NotificationRoute, Repository, TelegramBot
from .deps import current_user, flash, redirect, render

router = APIRouter(prefix="/routes")


@router.get("")
async def list_routes(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    routes = (
        await session.execute(
            select(NotificationRoute, Repository, TelegramBot)
            .join(Repository, NotificationRoute.repository_id == Repository.id)
            .outerjoin(TelegramBot, NotificationRoute.bot_id == TelegramBot.id)
            .order_by(Repository.owner, Repository.name)
        )
    ).all()
    repos = (
        await session.execute(select(Repository).order_by(Repository.owner, Repository.name))
    ).scalars().all()
    bots = (await session.execute(select(TelegramBot).order_by(TelegramBot.name))).scalars().all()
    return render(request, "routes.html", user, routes=routes, repos=repos, bots=bots)


@router.post("/add")
async def add_route(
    request: Request,
    repository_id: int = Form(...),
    channel_type: str = Form(...),
    bot_id: str = Form(""),
    chat_id: str = Form(""),
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    if channel_type == "telegram" and not bot_id:
        flash(request, "Pick a bot for a Telegram route.", "error")
        return redirect("/routes")

    route = NotificationRoute(
        repository_id=repository_id,
        channel_type=channel_type,
        bot_id=int(bot_id) if (channel_type == "telegram" and bot_id) else None,
        chat_id=chat_id.strip() or None if channel_type == "telegram" else None,
        enabled=True,
    )
    session.add(route)
    await session.commit()
    flash(request, "Notification route added.", "success")
    return redirect("/routes")


@router.post("/{route_id}/toggle")
async def toggle_route(
    route_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    route = await session.get(NotificationRoute, route_id)
    if route:
        route.enabled = not route.enabled
        await session.commit()
    return redirect("/routes")


@router.post("/{route_id}/delete")
async def delete_route(
    route_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    route = await session.get(NotificationRoute, route_id)
    if route:
        await session.delete(route)
        await session.commit()
        flash(request, "Route removed.", "success")
    return redirect("/routes")
