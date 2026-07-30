from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    rtsp_url = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)


class ViolationZone(Base):
    __tablename__ = "violation_zones"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    name = Column(String)
    polygon_coordinates = Column(JSON)


class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    violation_type = Column(String)
    status = Column(String, default="new")
    media_url = Column(String)
    comment = Column(String, nullable=True)