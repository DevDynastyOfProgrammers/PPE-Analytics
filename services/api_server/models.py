# api_server/models.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from database import Base

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    rtsp_url = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    # created_at = Column(DateTime(timezone=True), server_default=func.now())

class ViolationZone(Base):
    __tablename__ = "violation_zones"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    name = Column(String)
    # Полигон храним как список точек: [[x1, y1], [x2, y2], ...]
    polygon_coordinates = Column(JSON) 

class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    violation_type = Column(String) # "no_helmet", "no_vest", "no_ppe", "zone_intrusion"
    status = Column(String, default="new") # "new", "confirmed", "rejected"
    media_url = Column(String) # Путь к картинке/видео
    
    comment = Column(String, nullable=True) # Комментарий диспетчера