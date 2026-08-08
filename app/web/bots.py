from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import encrypt
from ..db import get_session
from ..models import TelegramBot
from .deps import current_user, flash, redirect, render, require_admin

router = APIRouter(prefix="/bots")


@router.get("")
async def list_bots(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    bots = (await session.execute(select(TelegramBot).order_by(TelegramBot.name))).scalars().all()
    return render(request, "bots.html", user, bots=bots)


@router.post("/add")
async def add_bot(
    request: Request,
    name: str = Form(...),
    token: str = Form(...),
    default_chat_id: str = Form(""),
    user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    bot = TelegramBot(
        name=name.strip(),
        token_enc=encrypt(token.strip()),
        default_chat_id=default_chat_id.strip() or None,
    )
    session.add(bot)
    await session.commit()
    flash(request, f"Added bot “{bot.name}”.", "success")
    return redirect("/bots")


@router.post("/{bot_id}/delete")
async def delete_bot(
    bot_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    bot = await session.get(TelegramBot, bot_id)
    if bot:
        await session.delete(bot)
        await session.commit()
        flash(request, f"Removed bot “{bot.name}”.", "success")
    return redirect("/bots")
