"""
KiranaAI - Strands Agents SDK Tools
Implements exactly the 4 required tools:
1. add_transaction
2. get_dues
3. record_payment
4. send_reminder
"""

from typing import Annotated, Dict, Any, List
from strands import tool
from db import db


@tool(description="Record a new credit (udhaar) transaction when a customer takes goods or money on credit.")
def add_transaction(
    customer_name: Annotated[str, "The name of the customer taking udhaar (credit)"],
    amount: Annotated[float, "The amount in rupees (₹) of the transaction"],
    item: Annotated[str, "Optional item or reason for the credit, e.g., 'doodh', 'cheeni', 'tel'"] = ""
) -> Dict[str, Any]:
    """Record a credit transaction for a customer."""
    result = db.add_credit(customer_name=customer_name, amount=amount, item=item)
    return {
        "status": "success",
        "action": "add_transaction",
        "customer_name": result["customer_name"],
        "credit_added": result["added_amount"],
        "item": result["item"],
        "new_balance": result["total_balance"],
        "message": f"₹{result['added_amount']} credited for {result['customer_name']}. Total balance: ₹{result['total_balance']}."
    }


@tool(description="Show customers and their outstanding pending balances (udhaar).")
def get_dues(
    customer_name: Annotated[str, "Optional customer name to check dues for. Leave blank to see all customers with pending balance."] = ""
) -> Dict[str, Any]:
    """Retrieve customers with outstanding balances."""
    data = db.get_dues(customer_name=customer_name)
    if customer_name and customer_name.strip():
        return {
            "status": "success",
            "action": "get_dues",
            "customer_name": data["customer_name"],
            "outstanding_balance": data["balance"],
            "has_dues": data["has_dues"],
            "transactions_count": len(data.get("transactions", [])),
            "message": f"{data['customer_name']} owes ₹{data['balance']}." if data["has_dues"] else f"{data['customer_name']} has no pending dues."
        }

    return {
        "status": "success",
        "action": "get_dues",
        "total_outstanding": data["total_outstanding"],
        "total_customers_with_dues": data["total_customers_with_dues"],
        "customers": data["customers"],
        "message": f"Total outstanding udhaar is ₹{data['total_outstanding']} across {data['total_customers_with_dues']} customer(s)."
    }


@tool(description="Record a payment made by a customer and show the remaining balance.")
def record_payment(
    customer_name: Annotated[str, "The name of the customer making the payment"],
    amount: Annotated[float, "The amount in rupees (₹) paid by the customer"]
) -> Dict[str, Any]:
    """Record a customer's payment against their udhaar."""
    result = db.record_payment(customer_name=customer_name, amount=amount)
    return {
        "status": "success",
        "action": "record_payment",
        "customer_name": result["customer_name"],
        "paid_amount": result["paid_amount"],
        "previous_balance": result["previous_balance"],
        "remaining_balance": result["remaining_balance"],
        "message": f"Recorded payment of ₹{result['paid_amount']} from {result['customer_name']}. Remaining balance: ₹{result['remaining_balance']}."
    }


@tool(description="Identify customers with pending balances and generate reminder messages automatically.")
def send_reminder(
    customer_name: Annotated[str, "Optional specific customer to remind. Leave blank to generate reminders for all pending customers."] = ""
) -> Dict[str, Any]:
    """Identify customers with pending balances and generate a reminder automatically."""
    reminders = db.get_pending_reminders(customer_name=customer_name)
    return {
        "status": "success",
        "action": "send_reminder",
        "total_reminders": len(reminders),
        "reminders": reminders,
        "message": f"Generated {len(reminders)} payment reminder(s)." if reminders else "No customers have pending dues to remind."
    }


# Export list of tools for the agent
KIRANA_TOOLS = [add_transaction, get_dues, record_payment, send_reminder]
