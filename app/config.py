
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-development-secret")

    SQLALCHEMY_DATABASE_URI = "sqlite:///wheelq.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ================= EMAIL =================
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv(
        "MAIL_DEFAULT_SENDER",
        MAIL_USERNAME
    )

    BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL", MAIL_USERNAME)
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", BUSINESS_EMAIL)
    WHEELQ_ADMIN_EMAILS = os.getenv("WHEELQ_ADMIN_EMAILS", "")

    # ================= PAYSTACK =================
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")

    # ================= PENALTIES =================
    LATE_PENALTY_PER_HOUR = 500

    # ================= ONFON SMS =================
    ONFON_SMS_API_KEY = os.getenv("ONFON_SMS_API_KEY")
    ONFON_SMS_SENDER = os.getenv("ONFON_SMS_SENDER", "WheelQ")
    ONFON_SMS_URL = os.getenv(
        "ONFON_SMS_URL",
        "https://api.onfonmedia.com/v1/sms/send"
    )

    # ================= REDIS CACHE =================
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = os.getenv(
        "CACHE_REDIS_URL",
        "redis://127.0.0.1:6379/0"
    )
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_OPTIONS = {
        "protocol": 2
    }
