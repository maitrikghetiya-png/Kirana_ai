# KiranaAI - Digital Udhaar Assistant 🏪

KiranaAI is an AI agent for Indian kirana shop owners to manage customer credit (udhaar). It accepts natural voice or text queries in Hindi/Hinglish (e.g., *"Ramesh liya 500 doodh"*, *"Kaun paisa dena hai?"*, *"Ramesh ne 300 de diye"*), executes ledger operations using tool calling via the **Strands Agents SDK**, queries foundation models on **Amazon Bedrock**, and persists balance records to **Amazon DynamoDB**.

---

## 🛠️ Tech Stack
- **AI Reasoning**: Amazon Bedrock
- **Agent Framework & Tool Calling**: Strands Agents SDK (`strands-agents`)
- **Persistence**: Amazon DynamoDB (with automatic persistent local JSON fallback for offline demo)
- **Serverless**: AWS Lambda handler (`lambda_handler.py`)
- **Web App & API**: FastAPI + Uvicorn
- **Frontend**: Mobile-friendly Chat UI (`static/index.html`)

---

## ⚡ The 4 Required Tools
KiranaAI implements strictly the 4 tools:
1. `add_transaction`: Record a credit transaction when a customer takes goods or money on udhaar.
2. `get_dues`: Show customers with pending dues and outstanding balances.
3. `record_payment`: Record a customer's payment and calculate remaining balance.
4. `send_reminder`: Identify customers with pending balances and generate polite payment reminders.

---

## 🎯 4 Core Test Flows

| # | User Input | Tool Called | Outcome |
|---|---|---|---|
| **1** | `"Ramesh liya 500 doodh"` | `add_transaction` | Records ₹500 credit for Ramesh |
| **2** | `"Kaun paisa dena hai?"` | `get_dues` | Displays Ramesh owing ₹500 |
| **3** | `"Ramesh ne 300 de diye"` | `record_payment` | Records ₹300 payment; ₹200 remaining |
| **4** | `"Reminder"` | `send_reminder` | Generates payment reminder for Ramesh (₹200) |

---

## 🚀 Getting Started

### 1. Run the Web App
```bash
cd kirana-ai
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser (or mobile simulator).

### 2. Run Automated Test Suite
```bash
cd kirana-ai
.venv/bin/python test_kirana.py
```

### 3. AWS Lambda Deployment
The function handler is located in `lambda_handler.py`:
- Function handler: `lambda_handler.lambda_handler`
- Runtime: Python 3.12
- DynamoDB Table: Set `DYNAMODB_TABLE_NAME` env var (default: `kirana_ai_udhaar`)
- Bedrock Model: Set `BEDROCK_MODEL_ID` env var (default: `amazon.nova-lite-v1:0` or Claude)
