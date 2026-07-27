from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.characters import (
    CharacterCreate,
    CharacterOut,
    CharacterUpdate,
    LockCharacterRequest,
    PromptPreviewRequest,
    PromptPreviewResponse,
    TransitionResponse,
)
from app.services import characters as svc

router = APIRouter(prefix="/api/characters", tags=["characters"])


def _err(e: svc.CharacterServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


@router.get("", response_model=list[CharacterOut])
async def list_characters(
    include_archived: bool = False, db: AsyncSession = Depends(get_db)
):
    return await svc.list_characters(db, include_archived=include_archived)


@router.post("", response_model=CharacterOut)
async def create_character(payload: CharacterCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.create_character(db, payload)
    except svc.CharacterServiceError as e:
        raise _err(e) from e


@router.get("/{character_id}", response_model=CharacterOut)
async def get_character(character_id: str, db: AsyncSession = Depends(get_db)):
    try:
        c = await svc.get_character(db, character_id)
        return svc.character_to_out(c)
    except svc.CharacterServiceError as e:
        raise _err(e) from e


@router.patch("/{character_id}", response_model=CharacterOut)
async def update_character(
    character_id: str, payload: CharacterUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        return await svc.update_character(db, character_id, payload)
    except svc.CharacterServiceError as e:
        raise _err(e) from e


@router.post("/{character_id}/bootstrap", response_model=TransitionResponse)
async def bootstrap_character(character_id: str, db: AsyncSession = Depends(get_db)):
    try:
        character = await svc.mark_bootstrap(db, character_id)
        return TransitionResponse(
            character=character,
            message="Character marked bootstrap — seed gallery & unlocked stills allowed",
        )
    except svc.CharacterServiceError as e:
        raise _err(e) from e


@router.post("/{character_id}/lock", response_model=TransitionResponse)
async def lock_character(
    character_id: str, payload: LockCharacterRequest, db: AsyncSession = Depends(get_db)
):
    try:
        character = await svc.lock_character(db, character_id, payload)
        return TransitionResponse(
            character=character,
            message="Character locked to version — production stills use this identity",
        )
    except svc.CharacterServiceError as e:
        raise _err(e) from e


@router.post("/{character_id}/archive", response_model=CharacterOut)
async def archive_character(character_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.archive_character(db, character_id)
    except svc.CharacterServiceError as e:
        raise _err(e) from e


@router.post("/{character_id}/preview-prompt", response_model=PromptPreviewResponse)
async def preview_prompt(
    character_id: str, payload: PromptPreviewRequest, db: AsyncSession = Depends(get_db)
):
    try:
        c = await svc.get_character(db, character_id)
        return svc.preview_prompts(
            c,
            payload.theme,
            outfit_hint=payload.outfit_hint,
            pose_hint=payload.pose_hint,
            location_hint=payload.location_hint,
            extra_prompt=payload.extra_prompt,
        )
    except svc.CharacterServiceError as e:
        raise _err(e) from e
