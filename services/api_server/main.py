from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from pydantic import BaseModel 
from sqlalchemy import update

import models, schemas
from database import engine, get_db, Base

from fastapi.staticfiles import StaticFiles
import os

# --- Lifespan (Жизненный цикл) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. ЛОГИКА ЗАПУСКА (STARTUP)
    print("--- Start up: Creating database tables ---")
    async with engine.begin() as conn:
        # Создаем таблицы, если их нет
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # 2. ЛОГИКА ЗАВЕРШЕНИЯ
    print("--- Shut down: Closing database connection ---")
    await engine.dispose()

# --- Инициализация приложения ---
app = FastAPI(title="PPE Violation Detection API", lifespan=lifespan)

class StatusUpdate(BaseModel):
    status: str  # Ожидаем "confirmed" или "rejected"
    comment: Optional[str] = None

# Создаем директорию, если её нет (на случай, если volume пуст)
os.makedirs("event_data", exist_ok=True)

# Монтируем папку /app/event_data по URL /static
app.mount("/static", StaticFiles(directory="event_data"), name="static")

@app.post("/cameras/", response_model=schemas.CameraResponse)
async def create_camera(camera: schemas.CameraCreate, db: AsyncSession = Depends(get_db)):
    new_camera = models.Camera(name=camera.name, rtsp_url=camera.rtsp_url, is_active=camera.is_active)
    db.add(new_camera)
    await db.commit()
    await db.refresh(new_camera)
    return new_camera

@app.get("/cameras/", response_model=List[schemas.CameraResponse])
async def read_cameras(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Camera).offset(skip).limit(limit))
    cameras = result.scalars().all()
    return cameras

# --- Endpoints для Зон ---

@app.post("/zones/", response_model=schemas.ZoneResponse)
async def create_zone(zone: schemas.ZoneCreate, db: AsyncSession = Depends(get_db)):
    # Проверяем, существует ли камера
    result = await db.execute(select(models.Camera).filter(models.Camera.id == zone.camera_id))
    camera = result.scalars().first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    new_zone = models.ViolationZone(
        name=zone.name, 
        camera_id=zone.camera_id, 
        polygon_coordinates=zone.polygon_coordinates
    )
    db.add(new_zone)
    await db.commit()
    await db.refresh(new_zone)
    return new_zone

@app.get("/cameras/{camera_id}/zones", response_model=List[schemas.ZoneResponse])
async def read_zones(camera_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ViolationZone).filter(models.ViolationZone.camera_id == camera_id))
    zones = result.scalars().all()
    return zones

@app.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    # 1. Сначала удаляем все зоны этой камеры (чтобы не было ошибок связей)
    await db.execute(delete(models.ViolationZone).where(models.ViolationZone.camera_id == camera_id))
    
    # 2. Ищем саму камеру
    result = await db.execute(select(models.Camera).filter(models.Camera.id == camera_id))
    camera = result.scalars().first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # 3. Удаляем камеру
    await db.delete(camera)
    await db.commit()
    return {"status": "deleted", "id": camera_id}

@app.delete("/zones/{zone_id}")
async def delete_zone(zone_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ViolationZone).filter(models.ViolationZone.id == zone_id))
    zone = result.scalars().first()
    
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    await db.delete(zone)
    await db.commit()
    return {"status": "deleted", "id": zone_id}

@app.put("/events/{event_id}/status")
async def update_event_status(event_id: int, status_data: StatusUpdate, db: AsyncSession = Depends(get_db)):
    """
    Изменение статуса нарушения.
    Принимает JSON: {"status": "confirmed", "comment": "..."}
    """
    # 1. Ищем событие по ID
    stmt = select(models.ViolationEvent).where(models.ViolationEvent.id == event_id)
    result = await db.execute(stmt)
    event = result.scalars().first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # 2. Обновляем поля
    event.status = status_data.status
    if status_data.comment:
        event.comment = status_data.comment
    
    # 3. Сохраняем
    await db.commit()
    await db.refresh(event)
    
    return {"id": event_id, "status": event.status, "comment": event.comment}