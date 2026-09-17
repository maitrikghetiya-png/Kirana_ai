"""
KiranaAI - Strands Agent with Amazon Bedrock Integration
Orchestrates AI reasoning and tool calling using Strands Agents SDK.
"""

import os
import re
import json
import logging
from typing import AsyncGenerator, Any, Optional
from strands import Agent
from strands.models.model import Model
from strands.models.bedrock import BedrockModel
from strands.types.streaming import StreamEvent

from tools import KIRANA_TOOLS, add_transaction, get_dues, record_payment, send_reminder

logger = logging.getLogger("kirana_ai.agent")

SYSTEM_PROMPT = """You are KiranaAI, a dedicated, polite, and smart AI assistant for Indian kirana shop owners.
Your job is to help shopkeepers manage their customer udhaar (credit ledger).
Shopkeepers may speak in Hinglish, Hindi, or English.

You have access to 4 specific tools:
1. add_transaction: Call when a customer takes goods or money on credit/udhaar (e.g., 'Ramesh liya 500 doodh', 'Mohan 300', 'Pappu ko 150 udhaar diya').
2. get_dues: Call when the shopkeeper asks who owes money or checks outstanding balances (e.g., 'Kaun paisa dena hai?', 'Kis-kis ka udhaar baaki hai?', 'Sonu ka kitna baki hai').
3. record_payment: Call when a customer makes a payment towards their udhaar (e.g., 'Ramesh ne 300 de diye', 'Suresh paid 150', 'Raju ne 500 diya').
4. send_reminder: Call when the shopkeeper wants to send or generate payment reminders for customers with pending balances (e.g., 'Reminder', 'Sabko reminder bhejo', 'Reminder Mohan').

Guidelines:
- Always call the right tool with extracted parameters.
- Respond in warm, concise Kirana Hinglish or Hindi.
- Always mention the customer name and exact amounts clearly in rupees (₹).
"""

HINDI_NUMS = {'०': '0', '१': '1', '२': '2', '३': '3', '४': '4', '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'}

STOP_WORDS = {
    'liya', 'lia', 'le', 'gaya', 'gayi', 'gaye', 'ne', 'ko', 'se', 'ka', 'ki', 'ke', 'me', 'mein',
    'pe', 'par', 'hai', 'hain', 'tha', 'thi', 'the', 'bhi', 'aur', 'rupaye', 'rs', 'inr', 'rupee',
    'rupees', 'karo', 'karna', 'lena', 'dena', 'de', 'diya', 'diye', 'paid', 'pay', 'kiya', 'jama',
    'udhaar', 'udhar', 'credit', 'add', 'baki', 'baaki', 'bhejo', 'please', 'ji', 'kripya', 'total',
    'aaya', 'aaye', 'mila', 'mile', 'chuka', 'chukaye', 'chutka', 'khatabook', 'khata', 'hisab',
    'hisaab', 'likho', 'chadao', 'chadhayo', 'baat', 'kuch', 'kitna', 'kitne', 'kaun', 'kis',
    'kisko', 'kiska', 'kisne', 'who', 'owes', 'dues', 'balance', 'pending', 'all', 'sabko', 'sabka',
    'paisa', 'paise', 'rupiya', 'rupiye', 'cash', 'money', 'batao', 'dikhao', 'show', 'list',
    # Hindi Devanagari stop words
    'ने', 'को', 'से', 'का', 'की', 'के', 'में', 'पर', 'है', 'हैं', 'था', 'थी', 'थे', 'भी', 'और',
    'रुपये', 'रुपए', 'रुपया', 'पैसा', 'पैसे', 'कैश', 'दी', 'दिया', 'दिए', 'दिये', 'लिया', 'ली',
    'उधार', 'खाता', 'हिसाब', 'कौन', 'किस', 'किसका', 'किसने', 'किसको', 'कितना', 'कितने', 'बाकी',
    'भेजो', 'कृपया', 'जी', 'कुल', 'जमा', 'दिखाओ', 'बताओ'
}

COMMON_ITEMS = {
    'doodh', 'cheeni', 'tel', 'chai', 'patti', 'dal', 'atta', 'chawal', 'biscuit', 'soap', 'sabun',
    'namak', 'masala', 'ghee', 'bread', 'butter', 'colgate', 'surf', 'detergent', 'paneer', 'dahi',
    'milk', 'sugar', 'oil', 'tea', 'rice', 'flour', 'salt', 'shampoo', 'paste', 'chips', 'chocolate',
    'दूध', 'चीनी', 'तेल', 'चाय', 'दाल', 'आटा', 'चावल', 'साबुन', 'नमक', 'मसाला', 'घी', 'दही', 'पनीर', 'बिस्कुट'
}


def normalize_text(text: str) -> str:
    t = text.strip()
    for h, d in HINDI_NUMS.items():
        t = t.replace(h, d)
    return t


class KiranaModel(Model):
    """
    Strands Model provider that leverages Amazon Bedrock when AWS credentials are valid,
    and includes an intelligent, universal Kirana NLU parser to ensure seamless execution
    for any customer name, item, or colloquial phrasing.
    """

    def __init__(self, model_id: Optional[str] = None, region_name: Optional[str] = None):
        self.model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self.bedrock_model = None
        self.use_bedrock = False

        self._init_bedrock()

    def _init_bedrock(self):
        try:
            import boto3
            session = boto3.Session()
            creds = session.get_credentials()
            if creds:
                self.bedrock_model = BedrockModel(
                    model_id=self.model_id,
                    region_name=self.region_name
                )
                self.use_bedrock = True
                logger.info("BedrockModel initialized successfully with %s in %s", self.model_id, self.region_name)
            else:
                logger.info("No AWS credentials detected; using intelligent local Kirana inference engine.")
        except Exception as e:
            logger.info("BedrockModel init error: %s; using intelligent local Kirana inference engine.", e)
            self.bedrock_model = None
            self.use_bedrock = False

    def update_config(self, **model_config: Any) -> None:
        if self.bedrock_model:
            self.bedrock_model.update_config(**model_config)

    def get_config(self) -> Any:
        return {"context_window_limit": 100000, "model_id": self.model_id}

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        if self.bedrock_model:
            async for chunk in self.bedrock_model.structured_output(*args, **kwargs):
                yield chunk

    def _extract_user_prompt(self, messages) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", [])
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        return block["text"]
                    elif isinstance(block, str):
                        return block
        return ""

    def _check_tool_result(self, messages) -> Optional[dict]:
        last_msg = messages[-1] if messages else None
        if not last_msg:
            return None
        content = last_msg.get("content", [])
        for block in content:
            if isinstance(block, dict) and "toolResult" in block:
                tr = block["toolResult"]
                c_list = tr.get("content", [])
                for item in c_list:
                    if isinstance(item, dict) and "text" in item:
                        try:
                            return json.loads(item["text"])
                        except Exception:
                            return {"text": item["text"]}
        return None

    def _classify_intent(self, raw_text: str) -> Optional[tuple[str, dict]]:
        """
        Universal intent & entity parser for kirana queries supporting English, Hinglish, and Hindi (Devanagari).
        Works for ANY customer name, item, or phrasing.
        """
        text = normalize_text(raw_text)
        lower = text.lower()

        # 1. REMINDERS
        if any(w in lower for w in ['reminder', 'remind', 'yaad dilao', 'tagada', 'taqaza', 'bhejo reminder', 'याद', 'तगादा']):
            words = re.findall(r'[\w\u0900-\u097F]+', text)
            cand_name = ''
            for w in words:
                wl = w.lower()
                if wl not in STOP_WORDS and wl not in ['reminder', 'remind', 'taqaza', 'tagada', 'याद']:
                    cand_name = w.capitalize()
                    break
            return ('send_reminder', {'customer_name': cand_name})

        # Extract all numbers/amounts
        num_matches = re.findall(r'(\d+(?:\.\d+)?)', text)
        amount = float(num_matches[0]) if num_matches else None
        words = re.findall(r'[\w\u0900-\u097F]+', text)

        # 2. DUES QUERY (Who owes? / Outstanding balances)
        is_dues_query = any(w in lower for w in [
            'kaun', 'kisko', 'kiska', 'kisne', 'kis-kis', 'who', 'dues', 'balance',
            'kitna baki', 'kitna udhaar', 'udhaar kitna', 'hisaab', 'hisab', 'baki kitna',
            'paisa dena', 'kaun paisa', 'kis kiska', 'कौन', 'किसका', 'किसको', 'बाकी'
        ])

        if is_dues_query and (amount is None or 'kitna' in lower or 'kaun' in lower or 'कौन' in lower or 'कितना' in lower):
            cand_name = ''
            for w in words:
                wl = w.lower()
                if wl not in STOP_WORDS and not wl.replace('.', '').isdigit():
                    cand_name = w.capitalize()
                    break
            return ('get_dues', {'customer_name': cand_name})

        # 3. IF AMOUNT IS PRESENT: Either PAYMENT or CREDIT (ADD_TRANSACTION)
        if amount is not None:
            payment_triggers = [
                'de diye', 'de diya', 'paid', 'pay kiya', 'pay kar', 'jama', 'chuka',
                'lautaye', 'wapas kiye', 'aaye', 'aaya', 'mila', 'mile', 'received',
                'दिए', 'दिये', 'दिया', 'जमा', 'चुकाए', 'लौटाए', 'मिले', 'आए'
            ]
            is_payment = False
            if any(p in lower for p in payment_triggers):
                is_payment = True
            elif ('diya' in lower or 'दिया' in lower) and 'udhaar' not in lower and 'udhar' not in lower and 'उधार' not in lower and 'credit' not in lower and 'ko' not in lower and 'को' not in lower:
                is_payment = True

            # Extract customer name and item
            cand_name = ''
            cand_item = ''

            # Check known common items
            for w in words:
                wl = w.lower()
                if wl in COMMON_ITEMS:
                    cand_item = wl

            # Candidate name: first word not in stop words, not a number, not an item
            for w in words:
                wl = w.lower()
                if wl.replace('.', '').isdigit():
                    continue
                if wl in STOP_WORDS:
                    continue
                if wl == cand_item:
                    continue
                if not cand_name:
                    cand_name = w.capitalize()
                elif not cand_item and wl not in STOP_WORDS:
                    cand_item = wl

            if not cand_name:
                cand_name = 'Customer'

            if is_payment:
                return ('record_payment', {'customer_name': cand_name, 'amount': amount})
            else:
                return ('add_transaction', {'customer_name': cand_name, 'amount': amount, 'item': cand_item})

        # Default fallback dues or help
        if any(w in lower for w in ['dues', 'list', 'hisaab', 'batao', 'show']):
            return ('get_dues', {'customer_name': ''})

        return None

    async def stream(
        self,
        messages,
        tool_specs=None,
        system_prompt=None,
        **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        # If Bedrock is connected, try Bedrock first
        if self.use_bedrock and self.bedrock_model:
            try:
                async for event in self.bedrock_model.stream(messages, tool_specs, system_prompt, **kwargs):
                    yield event
                return
            except Exception as e:
                logger.warning("Bedrock invocation error: %s. Using Kirana engine.", e)

        # Kirana Engine for Strands Agent
        tool_res = self._check_tool_result(messages)

        if tool_res:
            action = tool_res.get("action")
            if action == "add_transaction":
                text = (
                    f"Ji Sethji, {tool_res['customer_name']} ke khaate me ₹{tool_res['credit_added']} "
                    f"({tool_res.get('item', 'udhaar') or 'udhaar'}) darj kar liya gaya hai.\n\n"
                    f"👉 **Kul Udhaar (Total Due)**: ₹{tool_res['new_balance']}"
                )
            elif action == "get_dues":
                if "customers" in tool_res:
                    custs = tool_res["customers"]
                    if not custs:
                        text = "Sethji, abhi kisi bhi grahak ka koi udhaar baaki nahi hai! Sab hisaab barabar hai."
                    else:
                        lines = [f"📋 **Udhaar Baaki Grahak List** (Kul: ₹{tool_res['total_outstanding']}):\n"]
                        for i, c in enumerate(custs, 1):
                            lines.append(f"{i}. **{c['customer_name']}**: ₹{c['balance']}")
                        lines.append(f"\nKul {tool_res['total_customers_with_dues']} grahako se paisa lena hai.")
                        text = "\n".join(lines)
                else:
                    cname = tool_res.get("customer_name", "Grahak")
                    bal = tool_res.get("outstanding_balance", 0)
                    text = f"Sethji, {cname} ka ₹{bal} udhaar baaki hai." if bal > 0 else f"{cname} ka koi udhaar baaki nahi hai."

            elif action == "record_payment":
                text = (
                    f"Shabash Sethji! {tool_res['customer_name']} ne ₹{tool_res['paid_amount']} jama kar diye hain.\n\n"
                    f"💰 **Pehle ka Baaki**: ₹{tool_res['previous_balance']}\n"
                    f"✅ **Bacha Hua Udhaar (Remaining Balance)**: ₹{tool_res['remaining_balance']}"
                )
            elif action == "send_reminder":
                rems = tool_res.get("reminders", [])
                if not rems:
                    text = "Kisi bhi grahak ka koi udhaar baki nahi hai, isliye reminder ki zaroorat nahi hai."
                else:
                    lines = [f"🔔 **{len(rems)} Reminder Message(s) Taiyaar Hain:**\n"]
                    for r in rems:
                        wa_url = r.get("whatsapp_url", "")
                        lines.append(f"📱 **{r['customer_name']}** (₹{r['balance']}):\n> \"{r['message']}\"")
                        if wa_url:
                            lines.append(f"[WhatsApp par Bhejo]({wa_url})\n")
                        else:
                            lines.append("")
                    lines.append("Green WhatsApp button dabakar grahak ko turant message bhejein.")
                    text = "\n".join(lines)
            else:
                text = tool_res.get("message", "Kaam poora ho gaya Sethji.")

            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            return

        # First turn: Determine tool to call
        user_prompt = self._extract_user_prompt(messages)
        intent = self._classify_intent(user_prompt)

        if intent:
            tool_name, tool_args = intent
            tool_id = f"call_{tool_name}"
            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"toolUseId": tool_id, "name": tool_name}}}}
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": json.dumps(tool_args)}}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"messageStart": {"role": "assistant"}}
            reply = (
                "Namaste Sethji! Main aapka KiranaAI digital bahi-khata assistant hoon.\n"
                "Aap kisi bhi grahak ka udhaar likhwa sakte hain, jama karwa sakte hain, ya reminder bhej sakte hain.\n"
                "Jaise: 'Mohan 300', 'Suresh liya 200 doodh', 'Kaun paisa dena hai?', 'Raju ne 500 diya', ya 'Reminder'."
            )
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": reply}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}


def create_kirana_agent() -> Agent:
    """Instantiate and return the Strands Agent configured for KiranaAI."""
    model = KiranaModel()
    return Agent(
        model=model,
        tools=KIRANA_TOOLS,
        system_prompt=SYSTEM_PROMPT
    )


kirana_agent = create_kirana_agent()
