# import requests
# from datetime import datetime, timedelta
# from base64 import b64encode
# from requests.auth import HTTPBasicAuth
# import time


# class MpesaDaraja:
#     """
#     A class to interact with Safaricom's M-Pesa Daraja API for STK Push payments.
    
#     Attributes:
#         consumer_key (str): Daraja API consumer key.
#         consumer_secret (str): Daraja API consumer secret.
#         shortcode (str): Business short code.
#         passkey (str): Daraja API passkey.
#         callback_url (str): URL for receiving payment callbacks.
#         environment (str): 'sandbox' or 'production'.
#     """

#     def __init__(self, consumer_key, consumer_secret, shortcode, passkey, callback_url, environment="sandbox"):
#         self.consumer_key = consumer_key
#         self.consumer_secret = consumer_secret
#         self.shortcode = shortcode
#         self.passkey = passkey
#         self.callback_url = callback_url
#         self.environment = environment

#         # Base URL depending on environment
#         self.base_url = "https://sandbox.safaricom.co.ke" if environment == "sandbox" else "https://api.safaricom.co.ke"

#         # Token caching to reduce repeated API calls
#         self._access_token = None
#         self._token_expires_at = 0

#     def _normalize_phone(self, phone):
#         """
#         Convert phone number to format 2547XXXXXXXX.
#         """
#         phone = phone.strip()
#         if phone.startswith("0"):
#             phone = "254" + phone[1:]
#         elif phone.startswith("+"):
#             phone = phone.replace("+", "")
#         return phone

#     def get_access_token(self):
#         """
#         Fetch a valid access token from Daraja API.
#         Uses cached token if not expired.
#         """
#         current_time = time.time()
#         if self._access_token and current_time < self._token_expires_at - 60:
#             # Use cached token if still valid
#             return self._access_token

#         url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
#         response = requests.get(url, auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret))
        
#         if response.status_code != 200:
#             raise Exception(f"Failed to get access token: {response.text}")

#         data = response.json()
#         token = data.get("access_token")
#         expires_in = int(data.get("expires_in", 3600))  # Default 1 hour

#         if not token:
#             raise Exception(f"Access token missing in response: {data}")

#         # Cache token with expiry timestamp
#         self._access_token = token
#         self._token_expires_at = current_time + expires_in

#         return token

#     def stk_push(self, phone, amount, account_reference, description):
#         """
#         Initiate an STK Push transaction.

#         Args:
#             phone (str): Customer phone number.
#             amount (float|int): Payment amount.
#             account_reference (str): Account reference for the transaction.
#             description (str): Transaction description.

#         Returns:
#             dict: Response from Daraja API.

#         Raises:
#             Exception: If STK Push fails or API response contains errors.
#         """
#         # Ensure we have a valid access token
#         token = self.get_access_token()
#         print("MPESA TOKEN:", token)

#         # Normalize phone number
#         phone = self._normalize_phone(phone)

#         # Generate timestamp and password
#         timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#         password = b64encode(f"{self.shortcode}{self.passkey}{timestamp}".encode()).decode()

#         # Construct payload
#         payload = {
#                 # "BusinessShortCode": self.shortcode,
#             "Password": password,
#             "Timestamp": timestamp,
#             "TransactionType": "CustomerBuyGoodsOnline",
#             "Amount": int(amount),
#             "PartyA": phone,
#             "PartyB": self.shortcode,
#             "PhoneNumber": phone,
#             "CallBackURL": self.callback_url,
#             "AccountReference": account_reference,
#             "TransactionDesc": description
#         }

#         headers = {
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json"
#         }

#         # Send STK Push request
#         response = requests.post(f"{self.base_url}/mpesa/stkpush/v1/processrequest", json=payload, headers=headers)
#         data = response.json()

#         # Log response for debugging
#         print("MPESA RESPONSE:", data)

#         # Check for errors and raise exception if any
#         if data.get("ResponseCode") != "0":
#             error_msg = data.get("errorMessage") or data
#             raise Exception(f"STK push failed: {error_msg}")

#         return data
