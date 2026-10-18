import requests
import logging
from flask import current_app


def send_sms(phone, message):
    api_key = current_app.config.get("ONFON_SMS_API_KEY")
    sender_id = current_app.config.get("ONFON_SMS_SENDER", "WheelQ")

    url = "https://api.onfonmedia.co.ke/v1/sms/send"

    if not api_key:
        logging.error("❌ ONFON_API_KEY missing")
        return {"status": "failed", "error": "Missing API key"}

    payload = {
        "apikey": api_key,
        "senderId": sender_id,
        "phoneNumber": phone,
        "message": message,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(
            url,
            data=payload,        # ✅ NOT json=
            headers=headers,
            timeout=15
        )

        logging.info(f"ONFON RESPONSE [{response.status_code}]: {response.text}")

        if response.status_code != 200:
            return {
                "status": "failed",
                "provider_response": response.text
            }

        return {
            "status": "sent",
            "provider_response": response.text
        }

    except requests.exceptions.RequestException as e:
        logging.error("SMS sending failed", exc_info=True)
        return {
            "status": "failed",
            "error": str(e)
        }
