import sys
from datetime import date, timedelta, datetime
from app import create_app, db
from app.models import Car, Admin, Notification
from app.utils.sms import send_sms
import os
from app.extensions import db

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE_DIR)
LOG_FILE = os.path.join(
    os.path.dirname(__file__),
    "insurance_cron.log"
)

with open(LOG_FILE, "a") as f:
    f.write(f"Ran at {datetime.now()}\n")


app = create_app()

def check_insurance_expiry():
    with app.app_context():
        today = date.today()
        alert_days = 7

        cars = Car.query.filter(
            Car.insurance_expiry != None,
            Car.insurance_expiry <= today + timedelta(days=alert_days),
            Car.insurance_notified == False
        ).all()

        for car in cars:
            msg = f"Insurance for {car.name} expires on {car.insurance_expiry}"

            db.session.add(Notification(message=msg))

            for admin in Admin.query.all():
                send_sms(admin.phone, msg)

            car.insurance_notified = True

            db.session.add(
            Notification(message="Insurance cron ran successfully")
        )
        db.session.commit()

      

if __name__ == "__main__":
    check_insurance_expiry()
