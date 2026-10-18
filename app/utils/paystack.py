import requests
import uuid

class Paystack:
    def __init__(self, secret_key):
        self.secret_key = secret_key
        self.base_url = "https://api.paystack.co"


    def initialize_payment(self, email, amount, callback_url, reference=None):
        if not reference:
            reference = str(uuid.uuid4())

        payload = {
            "email": email,
            "amount": int(amount * 100),  # Paystack uses kobo
            "callback_url": callback_url,
            "reference": reference,
            "channels": ["card", "mobile_money"]
        }

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            f"{self.base_url}/transaction/initialize",
            json=payload,
            headers=headers
        )

        data = response.json()
        if not data.get("status"):
            raise Exception(data.get("message"))

        return data["data"]

    def verify_payment(self, reference):
        headers = {
            "Authorization": f"Bearer {self.secret_key}"
        }

        response = requests.get(
            f"{self.base_url}/transaction/verify/{reference}",
            headers=headers
        )

        return response.json()
