"""
KiranaAI database layer.

- Uses Amazon DynamoDB when valid AWS credentials + an existing table are available.
- Automatically falls back to data/dynamodb_records.json for local development.

Required DynamoDB table:
    Table name: kirana_ai_udhaar
    Partition key: customer_name (String)

Environment:
    DYNAMODB_TABLE_NAME=kirana_ai_udhaar
    AWS_REGION=ap-south-1
"""

import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kirana_ai.db")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOCAL_DB_FILE = os.path.join(DATA_DIR, "dynamodb_records.json")

TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "kirana_ai_udhaar")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Unsupported type: {type(value)}")


class DynamoDBStore:
    def __init__(self, table_name: str = TABLE_NAME):
        self.table_name = table_name
        self.table = None
        self.is_aws_connected = False
        self._init_backend()

    def _init_backend(self):
        os.makedirs(DATA_DIR, exist_ok=True)

        if not os.path.exists(LOCAL_DB_FILE):
            self._save_local_records({})

        try:
            import boto3

            session = boto3.Session(region_name=AWS_REGION)
            credentials = session.get_credentials()

            if credentials is None:
                return

            dynamodb = session.resource("dynamodb")
            table = dynamodb.Table(self.table_name)

            # Do not fail application startup if the table does not exist.
            table.load()

            self.table = table
            self.is_aws_connected = True
            logger.info("Using DynamoDB table: %s", self.table_name)

        except Exception as exc:
            logger.info("Using local JSON database: %s", exc)
            self.table = None
            self.is_aws_connected = False

    def _load_local_records(self) -> Dict[str, Any]:
        os.makedirs(DATA_DIR, exist_ok=True)

        if not os.path.exists(LOCAL_DB_FILE):
            return {}

        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_local_records(self, records: Dict[str, Any]):
        os.makedirs(DATA_DIR, exist_ok=True)

        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as file:
            json.dump(records, file, indent=2, ensure_ascii=False, default=_json_default)

    @staticmethod
    def _clean_name(customer_name: str) -> str:
        name = (customer_name or "").strip()
        return name if name else "Customer"

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def add_credit(self, customer_name: str, amount: float, item: str = "") -> Dict[str, Any]:
        name = self._clean_name(customer_name)
        amount = round(float(amount), 2)
        item = (item or "").strip()
        timestamp = self._now()

        if amount <= 0:
            raise ValueError("Amount must be greater than 0.")

        if self.is_aws_connected:
            try:
                response = self.table.get_item(Key={"customer_name": name})
                record = response.get("Item", {
                    "customer_name": name,
                    "balance": Decimal("0"),
                    "transactions": [],
                })

                old_balance = float(record.get("balance", 0))
                transactions = record.get("transactions", [])
                transactions.append({
                    "type": "credit",
                    "amount": Decimal(str(amount)),
                    "item": item or "General Udhaar",
                    "timestamp": timestamp,
                })

                new_balance = round(old_balance + amount, 2)

                self.table.put_item(Item={
                    "customer_name": name,
                    "balance": Decimal(str(new_balance)),
                    "transactions": transactions,
                    "last_updated": timestamp,
                })

                return {
                    "customer_name": name,
                    "added_amount": amount,
                    "item": item or "General Udhaar",
                    "total_balance": new_balance,
                    "timestamp": timestamp,
                }
            except Exception as exc:
                logger.warning("DynamoDB write failed; using local store: %s", exc)

        records = self._load_local_records()
        key = name.lower()

        record = records.get(key, {
            "customer_name": name,
            "balance": 0.0,
            "transactions": [],
        })

        new_balance = round(float(record.get("balance", 0)) + amount, 2)

        record["customer_name"] = name
        record["balance"] = new_balance
        record.setdefault("transactions", []).append({
            "type": "credit",
            "amount": amount,
            "item": item or "General Udhaar",
            "timestamp": timestamp,
        })
        record["last_updated"] = timestamp

        records[key] = record
        self._save_local_records(records)

        return {
            "customer_name": name,
            "added_amount": amount,
            "item": item or "General Udhaar",
            "total_balance": new_balance,
            "timestamp": timestamp,
        }

    def record_payment(self, customer_name: str, amount: float) -> Dict[str, Any]:
        name = self._clean_name(customer_name)
        amount = round(float(amount), 2)
        timestamp = self._now()

        if amount <= 0:
            raise ValueError("Payment amount must be greater than 0.")

        if self.is_aws_connected:
            try:
                response = self.table.get_item(Key={"customer_name": name})
                record = response.get("Item", {
                    "customer_name": name,
                    "balance": Decimal("0"),
                    "transactions": [],
                })

                previous = float(record.get("balance", 0))
                remaining = max(0.0, round(previous - amount, 2))
                transactions = record.get("transactions", [])
                transactions.append({
                    "type": "payment",
                    "amount": Decimal(str(amount)),
                    "timestamp": timestamp,
                })

                self.table.put_item(Item={
                    "customer_name": name,
                    "balance": Decimal(str(remaining)),
                    "transactions": transactions,
                    "last_updated": timestamp,
                })

                return {
                    "customer_name": name,
                    "paid_amount": amount,
                    "previous_balance": previous,
                    "remaining_balance": remaining,
                    "timestamp": timestamp,
                }
            except Exception as exc:
                logger.warning("DynamoDB payment failed; using local store: %s", exc)

        records = self._load_local_records()
        key = name.lower()

        record = records.get(key, {
            "customer_name": name,
            "balance": 0.0,
            "transactions": [],
        })

        previous = float(record.get("balance", 0))
        remaining = max(0.0, round(previous - amount, 2))

        record["customer_name"] = name
        record["balance"] = remaining
        record.setdefault("transactions", []).append({
            "type": "payment",
            "amount": amount,
            "timestamp": timestamp,
        })
        record["last_updated"] = timestamp

        records[key] = record
        self._save_local_records(records)

        return {
            "customer_name": name,
            "paid_amount": amount,
            "previous_balance": previous,
            "remaining_balance": remaining,
            "timestamp": timestamp,
        }

    def get_dues(self, customer_name: Optional[str] = None) -> Dict[str, Any]:
        if customer_name and customer_name.strip():
            name = customer_name.strip()

            if self.is_aws_connected:
                try:
                    response = self.table.get_item(Key={"customer_name": name})
                    item = response.get("Item")

                    if item:
                        balance = float(item.get("balance", 0))
                        return {
                            "customer_name": item.get("customer_name", name),
                            "balance": balance,
                            "transactions": item.get("transactions", []),
                            "has_dues": balance > 0,
                        }
                except Exception as exc:
                    logger.warning("DynamoDB read failed; using local store: %s", exc)

            records = self._load_local_records()
            record = records.get(name.lower())

            if record:
                balance = float(record.get("balance", 0))
                return {
                    "customer_name": record.get("customer_name", name),
                    "balance": balance,
                    "transactions": record.get("transactions", []),
                    "has_dues": balance > 0,
                }

            return {
                "customer_name": name,
                "balance": 0.0,
                "transactions": [],
                "has_dues": False,
            }

        customers = []
        total = 0.0

        if self.is_aws_connected:
            try:
                response = self.table.scan()
                for item in response.get("Items", []):
                    balance = float(item.get("balance", 0))
                    if balance > 0:
                        customers.append({
                            "customer_name": item.get("customer_name", "Customer"),
                            "balance": balance,
                            "last_updated": item.get("last_updated", ""),
                        })
                        total += balance

                customers.sort(key=lambda x: x["balance"], reverse=True)
                return {
                    "total_outstanding": round(total, 2),
                    "total_customers_with_dues": len(customers),
                    "customers": customers,
                }
            except Exception as exc:
                logger.warning("DynamoDB scan failed; using local store: %s", exc)

        records = self._load_local_records()

        for record in records.values():
            balance = float(record.get("balance", 0))
            if balance > 0:
                customers.append({
                    "customer_name": record.get("customer_name", "Customer"),
                    "balance": balance,
                    "last_updated": record.get("last_updated", ""),
                })
                total += balance

        customers.sort(key=lambda x: x["balance"], reverse=True)

        return {
            "total_outstanding": round(total, 2),
            "total_customers_with_dues": len(customers),
            "customers": customers,
        }

    def get_pending_reminders(self, customer_name: Optional[str] = None) -> List[Dict[str, Any]]:
        import urllib.parse

        dues = self.get_dues(customer_name)
        reminders = []

        if customer_name and customer_name.strip():
            candidates = [{
                "customer_name": dues["customer_name"],
                "balance": dues["balance"],
            }] if dues.get("balance", 0) > 0 else []
        else:
            candidates = dues.get("customers", [])

        for customer in candidates:
            name = customer["customer_name"]
            balance = float(customer["balance"])

            amount_text = (
                str(int(balance))
                if balance.is_integer()
                else str(balance)
            )

            message = (
                f"Namaste {name} ji, Kirana Store se aapka "
                f"₹{amount_text} ka udhaar baaki hai. "
                f"Kripya samay par chukta karein. Dhanyawaad!"
            )

            reminders.append({
                "customer_name": name,
                "balance": balance,
                "message": message,
                "whatsapp_url": (
                    "https://api.whatsapp.com/send?text="
                    + urllib.parse.quote(message)
                ),
            })

        return reminders

    def reset_db(self):
        if self.is_aws_connected and self.table:
            try:
                response = self.table.scan()
                for item in response.get("Items", []):
                    self.table.delete_item(
                        Key={"customer_name": item["customer_name"]}
                    )
            except Exception as exc:
                logger.warning("DynamoDB reset failed: %s", exc)

        self._save_local_records({})


db = DynamoDBStore()
