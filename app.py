"""
KiranaAI - FastAPI application.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os
import re
from typing import Optional, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import db

app = FastAPI(
    title="KiranaAI",
    version="1.0.0",
    description="AI-powered digital udhaar ledger for kirana stores",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    ledger: dict
    status: str = "success"


def _agent_response_to_text(result: Any) -> str:
    """Extract useful text from Strands AgentResult or a normal Python value."""
    if result is None:
        return ""

    output = getattr(result, "output", None)
    if output is not None:
        return str(output)

    return str(result)


def _simple_fallback(message: str) -> str:
    """
    Small local fallback so the web app remains usable even if
    the Strands/B edrock agent cannot be imported or invoked.
    """
    text = message.strip()
    lower = text.lower()

    # Payment
    payment_words = [
        "paid", "pay", "payment", "jama", "diya", "de diya",
        "chuka", "chukaya", "wapas", "received", "mila"
    ]

    amount_match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)", lower)
    amount = float(amount_match.group(1)) if amount_match else None

    if any(w in lower for w in ["kaun", "kisko", "dues", "balance", "baki", "udhaar list", "hisaab"]):
        data = db.get_dues()
        if not data["customers"]:
            return "Abhi kisi customer ka udhaar pending nahi hai."
        lines = ["📋 Pending Udhaar:"]
        for c in data["customers"]:
            lines.append(f"• {c['customer_name']}: ₹{c['balance']}")
        lines.append(f"\nTotal: ₹{data['total_outstanding']}")
        return "\n".join(lines)

    if amount is not None:
        words = re.findall(r"[A-Za-zÀ-ÿ]+", text)
        stop = {
            "ne", "ka", "ki", "ke", "ko", "se", "liye", "liya", "li",
            "aur", "me", "mein", "ka", "udhaar", "udhar", "credit",
            "rs", "inr", "rupaye", "rupees", "diya", "de", "paid",
            "pay", "jama", "chuka", "hai", "tha"
        }
        name = next((w for w in words if w.lower() not in stop), "Customer")
        if any(w in lower for w in payment_words):
            result = db.record_payment(name, amount)
            return (
                f"✅ {result['customer_name']} ne ₹{result['paid_amount']} jama kiye.\n"
                f"Remaining udhaar: ₹{result['remaining_balance']}"
            )

        item = ""
        common_items = ["doodh", "milk", "biscuit", "atta", "cheeni", "sugar",
                        "tel", "oil", "chai", "tea", "rice", "chawal", "dal"]
        for item_name in common_items:
            if item_name in lower:
                item = item_name
                break

        result = db.add_credit(name, amount, item)
        return (
            f"✅ {result['customer_name']} ke khaate me ₹{result['added_amount']} "
            f"({result['item'] or 'udhaar'}) add kiya.\n"
            f"Total udhaar: ₹{result['total_balance']}"
        )

    return (
        "Namaste Sethji! Example:\n"
        "• Ramesh ne 500 ka doodh aur biscuit liya\n"
        "• Raju ne 200 jama kiya\n"
        "• Kaun paisa dena hai?"
    )


def process_message(message: str) -> str:
    """Use the existing Strands agent first; fallback to the local ledger parser."""
    try:
        from agent import kirana_agent

        result = kirana_agent(message)
        text = _agent_response_to_text(result)
        if text and "AgentResult" not in text:
            return text
    except Exception:
        pass

    return _simple_fallback(message)


@app.get("/")
async def root():
    if not os.path.exists(INDEX_FILE):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(INDEX_FILE)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "database": "dynamodb" if db.is_aws_connected else "local-json",
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    message = payload.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        response_text = process_message(message)
        ledger = db.get_dues()
        return ChatResponse(response=response_text, ledger=ledger)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/ledger")
async def ledger_endpoint(customer_name: Optional[str] = None):
    return db.get_dues(customer_name=customer_name)


@app.get("/api/reminders")
async def reminders_endpoint(customer_name: Optional[str] = None):
    return db.get_pending_reminders(customer_name=customer_name)


@app.post("/api/autonomous-reminder")
async def autonomous_reminder_endpoint():
    reminders = db.get_pending_reminders()
    return {
        "status": "success",
        "mode": "autonomous",
        "total_reminders": len(reminders),
        "reminders": reminders,
    }


@app.post("/api/reset")
async def reset_endpoint():
    db.reset_db()
    return {"status": "success", "message": "Database cleared successfully."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
