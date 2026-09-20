from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.products import ProductUpdate
from app.services import products as product_svc

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("")
async def list_products(db: AsyncSession = Depends(get_db)):
    return await product_svc.list_products(db)


@router.get("/placements")
async def list_placements():
    from instantimpact_prompts.product import PRODUCT_PLACEMENTS

    return {
        "placements": [
            {"id": k, "label": k.replace("_", " "), "prompt": v}
            for k, v in PRODUCT_PLACEMENTS.items()
        ]
    }


@router.get("/{product_id}")
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    try:
        p = await product_svc.get_product(db, product_id)
    except product_svc.ProductServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    return product_svc.product_to_out(p)


@router.post("")
async def create_product(
    name: str = Form(...),
    description: str | None = Form(None),
    brand: str | None = Form(None),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await product_svc.create_product(
            db,
            name=name,
            upload=image,
            description=description,
            brand=brand,
        )
    except product_svc.ProductServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.patch("/{product_id}")
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await product_svc.update_product(
            db,
            product_id,
            name=payload.name,
            description=payload.description,
            brand=payload.brand,
        )
    except product_svc.ProductServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.delete("/{product_id}")
async def delete_product(product_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await product_svc.delete_product(db, product_id)
    except product_svc.ProductServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
