from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import encrypt
from ..db import get_session
from ..models import Repository
from ..providers import available_providers
from .deps import current_user, flash, redirect, render

router = APIRouter(prefix="/repositories")


@router.get("")
async def list_repos(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = (
        await session.execute(select(Repository).order_by(Repository.owner, Repository.name))
    ).scalars().all()
    return render(
        request,
        "repos.html",
        user,
        repos=repos,
        providers=available_providers(),
    )


@router.post("/add")
async def add_repo(
    request: Request,
    forge_type: str = Form(...),
    base_url: str = Form(""),
    owner: str = Form(...),
    name: str = Form(...),
    token: str = Form(""),
    watch_releases: bool = Form(False),
    watch_tags: bool = Form(False),
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if not watch_releases and not watch_tags:
        watch_releases = True  # watching nothing is pointless; default to releases

    repo = Repository(
        forge_type=forge_type,
        base_url=base_url.strip().rstrip("/"),
        owner=owner.strip(),
        name=name.strip(),
        token_enc=encrypt(token.strip()) if token.strip() else None,
        watch_releases=watch_releases,
        watch_tags=watch_tags,
    )
    session.add(repo)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        flash(request, "That repository is already registered.", "error")
        return redirect("/repositories")

    flash(request, f"Now watching {repo.slug}. Baseline captured on the first poll.", "success")
    return redirect("/repositories")


@router.post("/{repo_id}/delete")
async def delete_repo(
    repo_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = await session.get(Repository, repo_id)
    if repo:
        await session.delete(repo)
        await session.commit()
        flash(request, f"Stopped watching {repo.slug}.", "success")
    return redirect("/repositories")
