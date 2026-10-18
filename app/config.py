import os

PAYSTACK_SECRET_KEY= os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY= os.getenv("PAYSTACK_PUBLIC_KEY")


class Config:
    SECRET_KEY = "replace_this_later"
    SQLALCHEMY_DATABASE_URI = "sqlite:///wheelq.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = "alvinkimotho06@gmail.com"
    MAIL_PASSWORD = "uzelrzefonrmogoh"
    MAIL_DEFAULT_SENDER = "WheelQ Contact <alvinkimotho06@gmail.com>"
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    ADMIN_EMAIL = "alvinkimotho06@gmail.com"

    LATE_PENALTY_PER_HOUR = 500  # in your currency unit

    ONFON_SMS_API_KEY = "gjfMq4l3Q1PkWw5FbCScaz7RrKYIn92sJ60HGDi8XTmVeoOx"
    ONFON_SMS_SENDER = "WheelQ"
    ONFON_SMS_URL = "https://api.onfonmedia.com/v1/sms/send"
