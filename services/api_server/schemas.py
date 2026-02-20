# api_server/schemas.py

from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

# --- Camera Schemas ---
class CameraBase(BaseModel):
    name: str
    rtsp_url: str
    is_active: bool = True

class CameraCreate(CameraBase):
    pass

class CameraResponse(CameraBase):
    id: int
    class Config:
        from_attributes = True # Позволяет читать данные прямо из SQLAlchemy моделей

# --- Zone Schemas ---
class ZoneBase(BaseModel):
    name: str
    polygon_coordinates: List[List[int]] # Пример: [[0,0], [100,0], [100,100]]

class ZoneCreate(ZoneBase):
    camera_id: int

class ZoneResponse(ZoneBase):
    id: int
    camera_id: int
    class Config:
        from_attributes = True

# --- Event Schemas ---
class EventResponse(BaseModel):
    id: int
    camera_id: int
    violation_type: str
    status: str
    timestamp: datetime
    media_url: Optional[str] = None
    comment: Optional[str] = None
    
    class Config:
        from_attributes = True