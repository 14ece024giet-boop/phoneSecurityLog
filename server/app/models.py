from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True, unique=True)
    device_name: str
    api_key: str = Field(index=True)
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen: Optional[datetime] = None

class ActivityEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    event_type: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    details_json: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_level: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ContactBackup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    name: str = Field(index=True)
    phone_number: str
    email: Optional[str] = None
    synced_at: datetime = Field(default_factory=datetime.utcnow)


