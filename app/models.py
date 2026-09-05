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

class CallLogBackup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    number: str = Field(index=True)
    name: Optional[str] = None
    call_type: str # INCOMING, OUTGOING, MISSED, REJECTED
    duration_seconds: int = 0
    call_timestamp: datetime = Field(index=True)
    synced_at: datetime = Field(default_factory=datetime.utcnow)

class SmsBackup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    address: str = Field(index=True) # Sender or Recipient number
    body: str # Message text
    sms_type: str # INBOX, SENT, DRAFT
    sms_timestamp: datetime = Field(index=True)
    synced_at: datetime = Field(default_factory=datetime.utcnow)

class DeviceCommand(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    command_type: str = Field(index=True) # 'FORCE_BACKUP', etc.
    status: str = Field(default="PENDING") # 'PENDING', 'SENT', 'EXECUTED'
    created_at: datetime = Field(default_factory=datetime.utcnow)




