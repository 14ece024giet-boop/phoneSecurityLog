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
from sqlmodel import SQLModel, Session, create_engine, select
from .models import Device, ActivityEvent, ContactBackup, CallLogBackup, SmsBackup, DeviceCommand

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

class CallLogItem(BaseModel):
    number: str
    name: Optional[str] = None
    call_type: str
    duration_seconds: int = 0
    call_timestamp: datetime

class BatchCallLogsRequest(BaseModel):
    device_id: str
    call_logs: List[CallLogItem]

class SmsItem(BaseModel):
    address: str
    body: str
    sms_type: str
    sms_timestamp: datetime

class BatchSmsRequest(BaseModel):
    device_id: str
    sms_messages: List[SmsItem]

class SendCommandRequest(BaseModel):
    device_id: str
    command_type: str

def get_session():
    with Session(engine) as session:
        yield session

# --- REMOTE COMMAND QUEUE API ---
@app.post("/api/v1/commands/send")
def send_command(payload: SendCommandRequest, session: Session = Depends(get_session)):
    cmd = DeviceCommand(device_id=payload.device_id, command_type=payload.command_type, status="PENDING")
    session.add(cmd)
    session.commit()
    return {"status": "queued", "command": payload.command_type, "device_id": payload.device_id}

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

    # Check for pending remote commands for this device
    pending_commands = session.exec(
        select(DeviceCommand).where(DeviceCommand.device_id == payload.device_id, DeviceCommand.status == "PENDING")
    ).all()
    cmd_list = [c.command_type for c in pending_commands]
    for c in pending_commands:
        c.status = "SENT"
        session.add(c)

    session.commit()
    return {"status": "success", "ingested": len(payload.events), "commands": cmd_list}


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

# --- CALL LOGS BACKUP API ---
@app.post("/api/v1/backup/call-logs")
def backup_call_logs(
    payload: BatchCallLogsRequest,
    x_api_key: str = Header(..., alias="X-API-KEY"),
    session: Session = Depends(get_session)
):
    device = session.exec(select(Device).where(Device.device_id == payload.device_id)).first()
    if device and device.api_key != x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key for this device")

    # Clear existing call logs for this device to prevent duplicates upon full re-sync
    existing = session.exec(select(CallLogBackup).where(CallLogBackup.device_id == payload.device_id)).all()
    for c in existing:
        session.delete(c)

    for item in payload.call_logs:
        if item.number.strip():
            call = CallLogBackup(
                device_id=payload.device_id,
                number=item.number.strip(),
                name=item.name.strip() if item.name else None,
                call_type=item.call_type,
                duration_seconds=item.duration_seconds,
                call_timestamp=item.call_timestamp,
                synced_at=datetime.utcnow()
            )
            session.add(call)

    session.commit()
    return {"status": "success", "backed_up": len(payload.call_logs)}

@app.get("/api/v1/backup/call-logs")
def get_call_logs(
    device_id: Optional[str] = None,
    session: Session = Depends(get_session)
):
    stmt = select(CallLogBackup).order_by(CallLogBackup.call_timestamp.desc())
    if device_id:
        stmt = stmt.where(CallLogBackup.device_id == device_id)
    return session.exec(stmt).all()

@app.get("/api/v1/backup/call-logs/csv")
def export_call_logs_csv(session: Session = Depends(get_session)):
    logs = session.exec(select(CallLogBackup).order_by(CallLogBackup.call_timestamp.desc())).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Contact Name", "Phone Number", "Call Type", "Duration (sec)", "Call Timestamp", "Device ID"])
    for l in logs:
        writer.writerow([l.name or "Unknown", l.number, l.call_type, l.duration_seconds, l.call_timestamp.strftime("%Y-%m-%d %H:%M:%S"), l.device_id])
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Call_Logs_Backup.csv"}
    )

# --- SMS MESSAGES BACKUP API ---
@app.post("/api/v1/backup/sms")
def backup_sms(
    payload: BatchSmsRequest,
    x_api_key: str = Header(..., alias="X-API-KEY"),
    session: Session = Depends(get_session)
):
    device = session.exec(select(Device).where(Device.device_id == payload.device_id)).first()
    if device and device.api_key != x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key for this device")

    # Clear existing SMS records for this device to prevent duplicates upon full re-sync
    existing = session.exec(select(SmsBackup).where(SmsBackup.device_id == payload.device_id)).all()
    for s in existing:
        session.delete(s)

    for item in payload.sms_messages:
        if item.address.strip() or item.body.strip():
            sms = SmsBackup(
                device_id=payload.device_id,
                address=item.address.strip(),
                body=item.body.strip(),
                sms_type=item.sms_type,
                sms_timestamp=item.sms_timestamp,
                synced_at=datetime.utcnow()
            )
            session.add(sms)

    session.commit()
    return {"status": "success", "backed_up": len(payload.sms_messages)}

@app.get("/api/v1/backup/sms")
def get_sms(
    device_id: Optional[str] = None,
    session: Session = Depends(get_session)
):
    stmt = select(SmsBackup).order_by(SmsBackup.sms_timestamp.desc())
    if device_id:
        stmt = stmt.where(SmsBackup.device_id == device_id)
    return session.exec(stmt).all()

@app.get("/api/v1/backup/sms/csv")
def export_sms_csv(session: Session = Depends(get_session)):
    sms_list = session.exec(select(SmsBackup).order_by(SmsBackup.sms_timestamp.desc())).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Address / Number", "Message Text", "Type", "Timestamp", "Device ID"])
    for s in sms_list:
        writer.writerow([s.address, s.body, s.sms_type, s.sms_timestamp.strftime("%Y-%m-%d %H:%M:%S"), s.device_id])
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=SMS_Messages_Backup.csv"}
    )

# --- COMPLETE 1-CLICK DISASTER RECOVERY ZIP ARCHIVE ---
import zipfile

@app.get("/api/v1/export/full-backup.zip")
def export_full_backup_zip(session: Session = Depends(get_session)):
    contacts = session.exec(select(ContactBackup).order_by(ContactBackup.name.asc())).all()
    events = session.exec(select(ActivityEvent).order_by(ActivityEvent.timestamp.desc())).all()
    call_logs = session.exec(select(CallLogBackup).order_by(CallLogBackup.call_timestamp.desc())).all()
    sms_list = session.exec(select(SmsBackup).order_by(SmsBackup.sms_timestamp.desc())).all()
    devices = session.exec(select(Device)).all()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Contacts CSV
        c_csv = io.StringIO()
        cw = csv.writer(c_csv)
        cw.writerow(["Name", "Phone Number", "Email", "Device ID", "Backup Date"])
        for c in contacts:
            cw.writerow([c.name, c.phone_number, c.email or "", c.device_id, c.synced_at.strftime("%Y-%m-%d %H:%M:%S")])
        zf.writestr("contacts_backup.csv", c_csv.getvalue())

        # 2. Contacts VCF (vCard for 1-click restore on new phone)
        vcf_lines = []
        for c in contacts:
            vcf_lines.append("BEGIN:VCARD")
            vcf_lines.append("VERSION:3.0")
            vcf_lines.append(f"FN:{c.name}")
            vcf_lines.append(f"TEL;TYPE=CELL:{c.phone_number}")
            if c.email:
                vcf_lines.append(f"EMAIL:{c.email}")
            vcf_lines.append("END:VCARD")
        zf.writestr("contacts_restore.vcf", "\r\n".join(vcf_lines))

        # 3. Call Logs CSV
        cl_csv = io.StringIO()
        clw = csv.writer(cl_csv)
        clw.writerow(["Contact Name", "Phone Number", "Call Type", "Duration (sec)", "Call Timestamp", "Device ID"])
        for l in call_logs:
            clw.writerow([l.name or "Unknown", l.number, l.call_type, l.duration_seconds, l.call_timestamp.strftime("%Y-%m-%d %H:%M:%S"), l.device_id])
        zf.writestr("call_logs_backup.csv", cl_csv.getvalue())

        # 4. SMS Messages CSV
        s_csv = io.StringIO()
        sw = csv.writer(s_csv)
        sw.writerow(["Address / Number", "Message Text", "Type", "Timestamp", "Device ID"])
        for s in sms_list:
            sw.writerow([s.address, s.body, s.sms_type, s.sms_timestamp.strftime("%Y-%m-%d %H:%M:%S"), s.device_id])
        zf.writestr("sms_messages_backup.csv", s_csv.getvalue())

        # 5. Activity Logs CSV
        e_csv = io.StringIO()
        ew = csv.writer(e_csv)
        ew.writerow(["Timestamp", "Device ID", "Event Type", "Battery %", "Latitude", "Longitude", "Details JSON"])
        for e in events:
            ew.writerow([e.timestamp.strftime("%Y-%m-%d %H:%M:%S"), e.device_id, e.event_type, e.battery_level or "", e.latitude or "", e.longitude or "", e.details_json])
        zf.writestr("activity_logs.csv", e_csv.getvalue())

        # 6. Complete JSON snapshot
        complete_json = {
            "exported_at": datetime.utcnow().isoformat(),
            "devices": [d.dict() for d in devices],
            "contacts_count": len(contacts),
            "contacts": [c.dict() for c in contacts],
            "call_logs_count": len(call_logs),
            "call_logs": [cl.dict() for cl in call_logs],
            "sms_count": len(sms_list),
            "sms_messages": [sm.dict() for sm in sms_list],
            "events_count": len(events),
            "events": [e.dict() for e in events]
        }
        zf.writestr("complete_telemetry_and_backups.json", json.dumps(complete_json, default=str, indent=2))

        # 7. Raw SQLite database if present
        db_path = Path(BASE_DIR.parent / "phone_security.db")
        if db_path.exists():
            zf.write(db_path, arcname="phone_security_raw_database.sqlite")

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=Phone_Security_Complete_Backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"}
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
    call_logs = session.exec(
        select(CallLogBackup).order_by(CallLogBackup.call_timestamp.desc()).limit(200)
    ).all()
    sms_messages = session.exec(
        select(SmsBackup).order_by(SmsBackup.sms_timestamp.desc()).limit(200)
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
            "call_logs": call_logs,
            "total_calls": len(call_logs),
            "sms_messages": sms_messages,
            "total_sms": len(sms_messages),
            "locations_json": json.dumps(locations),
            "total_events": len(events)
        }
    )


from fastapi.responses import HTMLResponse, FileResponse

# --- 1-CLICK APK DOWNLOAD FOR PHONE ---
@app.get("/download/app")
def download_apk():
    possible_paths = [
        BASE_DIR / "static" / "PhoneSecurityApp.apk",
        BASE_DIR.parent / "PhoneSecurityApp.apk",
        Path("c:/Users/ajitc/securityphon/server/app/static/PhoneSecurityApp.apk"),
        Path("c:/Users/ajitc/securityphon/PhoneSecurityApp.apk"),
    ]
    for p in possible_paths:
        if p.exists():
            return FileResponse(
                path=str(p),
                filename="PhoneSecurityApp.apk",
                media_type="application/vnd.android.package-archive"
            )
    raise HTTPException(status_code=404, detail="APK file not found on server")


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

