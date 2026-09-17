"""
KiranaAI - AWS Lambda Handler
Enables deploying KiranaAI agent as an AWS Lambda function behind Amazon API Gateway,
and handles autonomous scheduled events directly from Amazon EventBridge Scheduler.
"""

import json
import logging
from agent import create_kirana_agent
from tools import send_reminder
from db import db

logger = logging.getLogger("kirana_ai.lambda")
logger.setLevel(logging.INFO)

agent = create_kirana_agent()


def lambda_handler(event, context):
    """
    AWS Lambda entrypoint.
    Supports:
    1. Autonomous EventBridge Scheduler invocations (no chat request required)
    2. API Gateway HTTP proxy events
    3. Direct JSON invocations
    """
    try:
        # 1. Check if invocation is an autonomous scheduled event from EventBridge
        is_eventbridge = False
        if isinstance(event, dict):
            if (
                event.get("source") == "aws.events" or
                event.get("detail-type") == "Scheduled Event" or
                event.get("action") == "autonomous_reminder" or
                event.get("action") == "cron_reminder" or
                event.get("scheduled") is True
            ):
                is_eventbridge = True
            elif "body" in event and event["body"]:
                try:
                    b = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
                    if isinstance(b, dict) and b.get("action") == "autonomous_reminder":
                        is_eventbridge = True
                except Exception:
                    pass

        if is_eventbridge:
            logger.info("⚡ Autonomous EventBridge Scheduler trigger received! Checking DynamoDB for outstanding balances...")
            # Autonomous check of DynamoDB and invocation of send_reminder without chat request
            reminder_result = send_reminder()
            logger.info("Autonomous reminder result: %s", reminder_result)

            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "status": "success",
                    "trigger": "EventBridge_Scheduler",
                    "mode": "autonomous",
                    "message": f"Autonomous EventBridge run completed. Generated {reminder_result.get('total_reminders', 0)} reminder(s).",
                    "reminder_result": reminder_result,
                    "ledger": db.get_dues()
                })
            }

        # 2. Parse standard chat prompt
        prompt = ""
        if isinstance(event, dict):
            if "body" in event and event["body"]:
                try:
                    body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
                    prompt = body.get("prompt", "") or body.get("message", "")
                except Exception:
                    prompt = str(event["body"])
            elif "prompt" in event:
                prompt = event["prompt"]
            elif "message" in event:
                prompt = event["message"]
            elif "queryStringParameters" in event and event["queryStringParameters"]:
                prompt = event["queryStringParameters"].get("prompt", "")

        if not prompt:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({"error": "Missing 'prompt' in request payload."})
            }

        # 3. Invoke Strands Agent
        result = agent(prompt)
        response_text = str(result)
        ledger = db.get_dues()

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "status": "success",
                "prompt": prompt,
                "response": response_text,
                "ledger": ledger
            })
        }

    except Exception as e:
        logger.error("Error executing KiranaAI in Lambda: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"status": "error", "message": str(e)})
        }
