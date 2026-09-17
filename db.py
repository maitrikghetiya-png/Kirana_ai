"""
KiranaAI - Persistent DynamoDB Ledger Storage Layer
Supports Amazon DynamoDB with automatic local file-backed persistence fallback.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from decimal import Decimal

logger = logging.getLogger("kirana_ai.db")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "kirana_ai_udhaar")
LOCAL_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOCAL_DB_FILE = os.path.join(LOCAL_DATA_DIR, "dynamodb_records.json")


def _json_serial(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


class DynamoDBStore:
    def __init__(self, table_name: str = TABLE_NAME):
        self.table_name = table_name
        self.dynamodb_client = None
        self.table = None
        self.is_aws_connected = False

        self._init_backend()

    def _init_backend(self):
        """Attempts to connect to Amazon DynamoDB; falls back to local persistent store if unavailable."""
        try:
            import boto3
            session = boto3.Session()
            creds = session.get_credentials()
            if creds:
                region = session.region_name or os.environ.get("AWS_REGION", "us-east-1")
                dynamodb = boto3.resource("dynamodb", region_name=region)
                table = dynamodb.Table(self.table_name)
                # Verify access by inspecting table status
                table.load()
                self.table = table
                self.is_aws_connected = True
                logger.info("Connected to Amazon DynamoDB table: %s", self.table_name)
                return
        except Exception as e:
            logger.info("Using persistent local DynamoDB store (AWS not configured or unavailable: %s)", e)

        os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
        if not os.path.exists(LOCAL_DB_FILE):
            with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _load_local_records(self) -> Dict[str, Any]:
        os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
        if not os.path.exists(LOCAL_DB_FILE):
            return {}
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_local_records(self, data: Dict[str, Any]):
        os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=_json_serial)

    def add_credit(self, customer_name: str, amount: float, item: str = "") -> Dict[str, Any]:
        """Record credit / udhaar taken by customer."""
        clean_name = customer_name.strip()
        key_name = clean_name.lower()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.is_aws_connected:
            try:
                # AWS DynamoDB get and update
                res = self.table.get_item(Key={"customer_name": clean_name})
                item_data = res.get("Item", {
                    "customer_name": clean_name,
                    "balance": Decimal("0"),
                    "transactions": []
                })
                current_balance = float(item_data.get("balance", 0))
                new_balance = current_balance + float(amount)
                txs = item_data.get("transactions", [])
                txs.append({
                    "type": "credit",
                    "amount": Decimal(str(amount)),
                    "item": item or "General Udhaar",
                    "timestamp": now_str
                })
                self.table.put_item(Item={
                    "customer_name": clean_name,
                    "balance": Decimal(str(new_balance)),
                    "transactions": txs,
                    "last_updated": now_str
                })
                return {
                    "customer_name": clean_name,
                    "added_amount": float(amount),
                    "item": item or "General Udhaar",
                    "total_balance": new_balance,
                    "timestamp": now_str
                }
            except Exception as e:
                logger.error("DynamoDB add_credit error: %s, falling back to local store", e)

        # Local Persistent store
        records = self._load_local_records()
        record = records.get(key_name, {
            "customer_name": clean_name,
            "balance": 0.0,
            "transactions": []
        })
        record["customer_name"] = clean_name  # Preserve case
        record["balance"] = round(record["balance"] + float(amount), 2)
        record["transactions"].append({
            "type": "credit",
            "amount": float(amount),
            "item": item or "General Udhaar",
            "timestamp": now_str
        })
        record["last_updated"] = now_str
        records[key_name] = record
        self._save_local_records(records)

        return {
            "customer_name": clean_name,
            "added_amount": float(amount),
            "item": item or "General Udhaar",
            "total_balance": record["balance"],
            "timestamp": now_str
        }

    def record_payment(self, customer_name: str, amount: float) -> Dict[str, Any]:
        """Record a payment towards customer udhaar."""
        clean_name = customer_name.strip()
        key_name = clean_name.lower()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.is_aws_connected:
            try:
                res = self.table.get_item(Key={"customer_name": clean_name})
                item_data = res.get("Item", {
                    "customer_name": clean_name,
                    "balance": Decimal("0"),
                    "transactions": []
                })
                current_balance = float(item_data.get("balance", 0))
                new_balance = max(0.0, current_balance - float(amount))
                txs = item_data.get("transactions", [])
                txs.append({
                    "type": "payment",
                    "amount": Decimal(str(amount)),
                    "timestamp": now_str
                })
                self.table.put_item(Item={
                    "customer_name": clean_name,
                    "balance": Decimal(str(new_balance)),
                    "transactions": txs,
                    "last_updated": now_str
                })
                return {
                    "customer_name": clean_name,
                    "paid_amount": float(amount),
                    "previous_balance": current_balance,
                    "remaining_balance": new_balance,
                    "timestamp": now_str
                }
            except Exception as e:
                logger.error("DynamoDB record_payment error: %s", e)

        records = self._load_local_records()
        record = records.get(key_name, {
            "customer_name": clean_name,
            "balance": 0.0,
            "transactions": []
        })
        current_balance = record["balance"]
        new_balance = max(0.0, round(current_balance - float(amount), 2))
        record["customer_name"] = clean_name
        record["balance"] = new_balance
        record["transactions"].append({
            "type": "payment",
            "amount": float(amount),
            "timestamp": now_str
        })
        record["last_updated"] = now_str
        records[key_name] = record
        self._save_local_records(records)

        return {
            "customer_name": clean_name,
            "paid_amount": float(amount),
            "previous_balance": current_balance,
            "remaining_balance": new_balance,
            "timestamp": now_str
        }

    def get_dues(self, customer_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetch pending dues for all customers or a specific customer."""
        if customer_name and customer_name.strip():
            target = customer_name.strip()
            key_name = target.lower()

            if self.is_aws_connected:
                try:
                    res = self.table.get_item(Key={"customer_name": target})
                    item = res.get("Item")
                    if item:
                        bal = float(item.get("balance", 0))
                        return {
                            "customer_name": item.get("customer_name", target),
                            "balance": bal,
                            "transactions": item.get("transactions", []),
                            "has_dues": bal > 0
                        }
                except Exception as e:
                    logger.error("DynamoDB get_dues error: %s", e)

            records = self._load_local_records()
            record = records.get(key_name)
            if record:
                return {
                    "customer_name": record.get("customer_name", target),
                    "balance": record.get("balance", 0.0),
                    "transactions": record.get("transactions", []),
                    "has_dues": record.get("balance", 0.0) > 0
                }
            return {
                "customer_name": target,
                "balance": 0.0,
                "transactions": [],
                "has_dues": False
            }

        # Fetch all customers with pending dues
        all_customers = []
        total_outstanding = 0.0

        if self.is_aws_connected:
            try:
                res = self.table.scan()
                items = res.get("Items", [])
                for it in items:
                    bal = float(it.get("balance", 0))
                    if bal > 0:
                        all_customers.append({
                            "customer_name": it.get("customer_name"),
                            "balance": bal,
                            "last_updated": it.get("last_updated", "")
                        })
                        total_outstanding += bal
                return {
                    "total_outstanding": round(total_outstanding, 2),
                    "total_customers_with_dues": len(all_customers),
                    "customers": all_customers
                }
            except Exception as e:
                logger.error("DynamoDB scan error: %s", e)

        records = self._load_local_records()
        for _, rec in records.items():
            bal = rec.get("balance", 0.0)
            if bal > 0:
                all_customers.append({
                    "customer_name": rec.get("customer_name"),
                    "balance": bal,
                    "last_updated": rec.get("last_updated", "")
                })
                total_outstanding += bal

        all_customers.sort(key=lambda x: x["balance"], reverse=True)
        return {
            "total_outstanding": round(total_outstanding, 2),
            "total_customers_with_dues": len(all_customers),
            "customers": all_customers
        }

    def get_pending_reminders(self, customer_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Identify customers with pending balances and generate reminder text with WhatsApp sharing link."""
        import urllib.parse
        dues_info = self.get_dues(customer_name)
        reminders = []

        if customer_name and customer_name.strip():
            bal = dues_info.get("balance", 0.0)
            c_name = dues_info.get("customer_name", customer_name.strip())
            if bal > 0:
                msg = (
                    f"Namaste {c_name} ji, Kirana Store se aapka ₹{int(bal) if bal.is_integer() else bal} "
                    f"ka udhaar baaki hai. Kripya samay par chukta karein. Dhanyawaad!"
                )
                wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}"
                reminders.append({
                    "customer_name": c_name,
                    "balance": bal,
                    "message": msg,
                    "whatsapp_url": wa_url
                })
            return reminders

        for cust in dues_info.get("customers", []):
            bal = cust["balance"]
            c_name = cust["customer_name"]
            msg = (
                f"Namaste {c_name} ji, Kirana Store se aapka ₹{int(bal) if bal.is_integer() else bal} "
                f"ka udhaar baaki hai. Kripya samay par chukta karein. Dhanyawaad!"
            )
            wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}"
            reminders.append({
                "customer_name": c_name,
                "balance": bal,
                "message": msg,
                "whatsapp_url": wa_url
            })

        return reminders

    def reset_db(self):
        """Clears records for testing purposes."""
        if self.is_aws_connected and self.table:
            try:
                res = self.table.scan()
                for item in res.get("Items", []):
                    self.table.delete_item(Key={"customer_name": item["customer_name"]})
            except Exception as e:
                logger.error("Error clearing DynamoDB table: %s", e)

        self._save_local_records({})


# Shared singleton instance
db = DynamoDBStore()
