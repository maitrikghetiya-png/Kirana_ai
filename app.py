"""
KiranaAI - Web Application Server
FastAPI server serving the mobile-friendly chat UI and KiranaAI Agent API.
Includes autonomous EventBridge reminder runner and scheduler trigger.
"""

import os
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from agent import kirana_agent
from tools import send_reminder
from db import db

app = FastAPI(title="KiranaAI - Digital Udhaar Assistant")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    ledger: dict
    status: str = "success"


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "KiranaAI API is running. UI index.html not found."}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        agent_result = kirana_agent(user_msg)
        response_text = str(agent_result)
        current_ledger = db.get_dues()

        return ChatResponse(
            response=response_text,
            ledger=current_ledger,
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/autonomous-reminder")
async def run_autonomous_reminder_endpoint():
    """
    Autonomous EventBridge Scheduler / Cron Trigger.
    Directly checks DynamoDB for outstanding balances and executes send_reminder
    without requiring any chat input.
    """
    try:
        reminder_result = send_reminder()
        current_ledger = db.get_dues()
        total_reminders = reminder_result.get("total_reminders", 0)

        return {
            "status": "success",
            "trigger": "EventBridge_Scheduler",
            "mode": "autonomous",
            "total_reminders": total_reminders,
            "reminders": reminder_result.get("reminders", []),
            "ledger": current_ledger,
            "message": f"Autonomous EventBridge run generated {total_reminders} reminder(s)." if total_reminders else "All customer balances are clear; no reminders needed."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ledger")
async def get_ledger_endpoint(customer_name: Optional[str] = None):
    return db.get_dues(customer_name=customer_name)


@app.get("/api/reminders")
async def get_reminders_endpoint(customer_name: Optional[str] = None):
    return db.get_pending_reminders(customer_name=customer_name)


@app.post("/api/reset")
async def reset_endpoint():
    db.reset_db()
    return {"status": "success", "message": "Database cleared successfully."}


# Mount static directory for CSS / JS / Assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
