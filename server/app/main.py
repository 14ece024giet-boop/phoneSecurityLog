import json
import csv
import io
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import SQLModel, Session, create_engine, select
from .models import Device, ActivityEvent
from .models import Device, ActivityEvent, ContactBackup

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR.parent}/phone_security.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

app = FastAPI(title="Phone Activity Security Cloud", version="1.0.0")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# Pydantic schema for ingestion
class EventItem(BaseModel):
    timestamp: datetime
    event_type: str
    details: dict = {}
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_level: Optional[int] = None

class BatchIngestRequest(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    events: List[EventItem]

class ContactItem(BaseModel):
    name: str
    phone_number: str
    email: Optional[str] = None

class BatchContactsRequest(BaseModel):
    device_id: str
    contacts: List[ContactItem]

def get_session():
    with Session(engine) as session:
        yield session

# --- INGESTION API ---
@app.post("/api/v1/telemetry/batch")
def ingest_events(
    payload: BatchIngestRequest,
    x_api_key: str = Header(..., alias="X-API-KEY"),
    session: Session = Depends(get_session)
):
    device = session.exec(select(Device).where(Device.device_id == payload.device_id)).first()
    if not device:
        # Register new device on first verified connection
        device = Device(
            device_id=payload.device_id,
            device_name=payload.device_name or f"Device-{payload.device_id[:6]}",
            api_key=x_api_key,
            last_seen=datetime.utcnow()
        )
        session.add(device)
    else:
        if device.api_key != x_api_key:
            raise HTTPException(status_code=401, detail="Invalid API Key for this device")
        device.last_seen = datetime.utcnow()
        if payload.device_name:
            device.device_name = payload.device_name
        session.add(device)

    # Ingest event list
    for item in payload.events:
        event = ActivityEvent(
            device_id=payload.device_id,
            event_type=item.event_type,
            timestamp=item.timestamp,
            details_json=json.dumps(item.details),
            latitude=item.latitude,
            longitude=item.longitude,
            battery_level=item.battery_level
        )
        session.add(event)

    session.commit()
    return {"status": "success", "ingested": len(payload.events)}

# --- CONTACTS BACKUP API ---
@app.post("/api/v1/backup/contacts")
def backup_contacts(
    payload: BatchContactsRequest,
    x_api_key: str = Header(..., alias="X-API-KEY"),
    session: Session = Depends(get_session)
):
    device = session.exec(select(Device).where(Device.device_id == payload.device_id)).first()
    if device and device.api_key != x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key for this device")

    # Clear existing contacts for this device to prevent duplicates upon full re-sync
    existing = session.exec(select(ContactBackup).where(ContactBackup.device_id == payload.device_id)).all()
    for c in existing:
        session.delete(c)

    # Batch insert newly backed up contacts
    for item in payload.contacts:
        if item.name.strip() or item.phone_number.strip():
            contact = ContactBackup(
                device_id=payload.device_id,
                name=item.name.strip() or "Unnamed Contact",
                phone_number=item.phone_number.strip(),
                email=item.email.strip() if item.email else None,
                synced_at=datetime.utcnow()
            )
            session.add(contact)

    session.commit()
    return {"status": "success", "backed_up": len(payload.contacts)}

@app.get("/api/v1/backup/contacts")
def get_contacts(
    device_id: Optional[str] = None,
    session: Session = Depends(get_session)
):
    stmt = select(ContactBackup).order_by(ContactBackup.name.asc())
    if device_id:
        stmt = stmt.where(ContactBackup.device_id == device_id)
    return session.exec(stmt).all()

@app.get("/api/v1/backup/contacts/csv")
def export_contacts_csv(session: Session = Depends(get_session)):
    contacts = session.exec(select(ContactBackup).order_by(ContactBackup.name.asc())).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Phone Number", "Email", "Device ID", "Backup Date"])
    for c in contacts:
        writer.writerow([c.name, c.phone_number, c.email or "", c.device_id, c.synced_at.strftime("%Y-%m-%d %H:%M:%S")])
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Phone_Contacts_Backup.csv"}
    )

# --- QUERY JSON API ---
@app.get("/api/v1/events")
def get_events(
    device_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session)
):
    statement = select(ActivityEvent).order_by(ActivityEvent.timestamp.desc())
    if device_id:
        statement = statement.where(ActivityEvent.device_id == device_id)
    if event_type:
        statement = statement.where(ActivityEvent.event_type == event_type)
    statement = statement.limit(limit)
    return session.exec(statement).all()

# --- WEB DASHBOARD ---
@app.get("/dashboard", response_class=HTMLResponse)
def view_dashboard(request: Request, session: Session = Depends(get_session)):
    events = session.exec(
        select(ActivityEvent).order_by(ActivityEvent.timestamp.desc()).limit(150)
    ).all()
    devices = session.exec(select(Device)).all()
    contacts = session.exec(
        select(ContactBackup).order_by(ContactBackup.name.asc()).limit(300)
    ).all()

    # Extract locations for mapping
    locations = [
        {
            "device_id": e.device_id,
            "lat": e.latitude,
            "lng": e.longitude,
            "event_type": e.event_type,
            "time": e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for e in events if e.latitude is not None and e.longitude is not None
    ]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "events": events,
            "devices": devices,
            "contacts": contacts,
            "total_contacts": len(contacts),
            "locations_json": json.dumps(locations),
            "total_events": len(events)
        }
    )

from fastapi.responses import HTMLResponse, FileResponse

# --- 1-CLICK APK DOWNLOAD FOR PHONE ---
@app.get("/download/app")
def download_apk():
    apk_file = Path("c:/Users/ajitc/securityphon/PhoneSecurityApp.apk")
    if not apk_file.exists():
        raise HTTPException(status_code=404, detail="APK file not found")
    return FileResponse(
        path=str(apk_file),
        filename="PhoneSecurityApp.apk",
        media_type="application/vnd.android.package-archive"
    )

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
        <head><title>Phone Security Cloud</title></head>
        <body style="font-family:sans-serif; text-align:center; padding:50px; background:#0f172a; color:#fff;">
            <h1>🛡️ Phone Activity Cloud Backend is Running</h1>
            <p><a href="/download/app" style="background:#0284c7; color:#fff; padding:12px 24px; border-radius:8px; text-decoration:none; font-weight:bold; font-size:1.1rem; display:inline-block; margin:15px 0;">📲 Download APK to Your Mobile</a></p>
            <p>Go to <a href="/dashboard" style="color:#38bdf8; font-size:1.2rem; font-weight:bold;">Security Dashboard (/dashboard)</a></p>
            <p>Interactive API Docs: <a href="/docs" style="color:#38bdf8;">/docs</a></p>
        </body>
    </html>
    """

