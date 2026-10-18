from datetime import datetime, timedelta
from math import ceil
import logging

from flask import current_app
from app import db
from app.models import Booking, LatePenalty
from app.utils.sms import send_sms

# Configurable values
GRACE_MINUTES = 30
PENALTY_PER_HOUR = 500


def late_penalty_check():
    """
    CRON ENTRY POINT (called by APScheduler)
    """
    with current_app.app_context():
        check_late_returns()


def check_late_returns():
    """
    Unified late return penalty logic

    1. Find overdue bookings
    2. Respect grace period
    3. Calculate overdue hours
    4. Create or update LatePenalty
    5. Send SMS only ONCE (first penalty)
    """

    now = datetime.utcnow()

    overdue_bookings = Booking.query.filter(
        Booking.status != "completed",
        Booking.dropoff_date < now
    ).all()

    logging.warning(f"[LATE CHECK] Found {len(overdue_bookings)} overdue bookings")

    for booking in overdue_bookings:
        try:
            grace_end = booking.dropoff_date + timedelta(minutes=GRACE_MINUTES)

            # Still within grace period
            if now <= grace_end:
                continue

            overdue_seconds = (now - grace_end).total_seconds()
            overdue_hours = ceil(overdue_seconds / 3600)

            if overdue_hours <= 0:
                continue

            penalty_amount = overdue_hours * PENALTY_PER_HOUR

            # Check for existing unpaid penalty
            existing_penalty = LatePenalty.query.filter_by(
                booking_id=booking.id,
                status="unpaid"
            ).first()

            if existing_penalty:
                # Update running penalty (NO SMS)
                existing_penalty.hours_late = overdue_hours
                existing_penalty.amount = penalty_amount
                logging.info(
                    f"[UPDATE] Penalty updated for booking {booking.id}: "
                    f"{overdue_hours} hrs | KES {penalty_amount}"
                )
            else:
                # Create new penalty
                penalty = LatePenalty(
                    booking_id=booking.id,
                    client_phone=booking.client_phone,
                    registration_number=booking.car.registration_number,
                    hours_late=overdue_hours,
                    amount=penalty_amount,
                    status="unpaid",
                    created_at=now
                )
                db.session.add(penalty)

                # Send SMS ONCE
                sms_message = (
                    f"WheelQ Alert 🚗\n"
                    f"Your vehicle ({booking.car.registration_number}) "
                    f"is overdue.\n"
                    f"Current penalty: KES {penalty_amount}\n"
                    f"Please return it immediately."
                )
                send_sms(booking.client_phone, sms_message)

                logging.warning(
                    f"[NEW PENALTY] Booking {booking.id} | "
                    f"{overdue_hours} hrs | KES {penalty_amount}"
                )

            # Update booking flags
            booking.is_overdue = True
            booking.penalty_amount = penalty_amount

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            logging.error(
                f"[ERROR] Late penalty failed for booking {booking.id}: {str(e)}",
                exc_info=True
            )
