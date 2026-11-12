
import os
from decimal import Decimal
from datetime import date, datetime

from flask import current_app, render_template
from markupsafe import escape

from app import db
from app.models import (
    Booking,
    FinancialCharge,
    FinancialPayment,
    Lease,
    LeasePayment,
    LatePenalty,
    AirportTransfer,
)

from app.services.email_service import queue_email
from app.services.document_service import generate_document


# ==========================================================
# GENERAL HELPERS
# ==========================================================

def _value(obj, field, default=None):
    return getattr(obj, field, default) if obj else default


def _money(value):
    return Decimal(str(value or 0))


def _money_text(value):
    return f"KSh {_money(value):,.2f}"


def _format_date(value):
    if not value:
        return "To be confirmed"

    if isinstance(value, (datetime, date)):
        return value.strftime("%d %b %Y")

    return str(value)


def _format_datetime(value):
    if not value:
        return "To be confirmed"

    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %I:%M %p")

    return str(value)


def _admin_emails():
    """
    Get admin recipients from WHEELQ_ADMIN_EMAILS.
    Fall back to ADMIN_EMAIL or BUSINESS_EMAIL.
    """

    configured = (
        current_app.config.get("WHEELQ_ADMIN_EMAILS")
        or os.getenv("WHEELQ_ADMIN_EMAILS", "")
    )

    emails = [
        email.strip()
        for email in configured.split(",")
        if email.strip()
    ]

    if not emails:
        fallback = (
            current_app.config.get("ADMIN_EMAIL")
            or current_app.config.get("BUSINESS_EMAIL")
        )

        if fallback:
            emails = [fallback.strip()]

    # Remove duplicates while preserving order.
    return list(dict.fromkeys(emails))


def _customer_email(obj):
    """
    Find customer email from the object or its relationships.
    """

    if not obj:
        return None

    for field in ("client_email", "email", "investor_email"):
        value = _value(obj, field)

        if value and str(value).strip():
            return str(value).strip()

    client = _value(obj, "client")

    if client:
        email = _value(client, "email")

        if email:
            return str(email).strip()

    # Booking fallback for financial charges.
    booking = _value(obj, "booking")

    if booking:
        email = _value(booking, "client_email")

        if email:
            return str(email).strip()

    # Airport transfer fallback for linked financial charges.
    transfer = _value(obj, "airport_transfer")

    if transfer:
        email = _value(transfer, "email")

        if email:
            return str(email).strip()

    # Lease fallback for lease payments.
    lease = _value(obj, "lease")

    if lease:
        email = _value(lease, "email")

        if email:
            return str(email).strip()

    return None


def _customer_name(obj, default="Customer"):
    if not obj:
        return default

    for field in ("client_name", "name", "investor_name", "owner_name"):
        value = _value(obj, field)

        if value and str(value).strip():
            return str(value).strip()

    client = _value(obj, "client")

    if client and _value(client, "name"):
        return client.name

    booking = _value(obj, "booking")

    if booking and _value(booking, "client_name"):
        return booking.client_name

    return default


def _render_customer_template(template_name, context):
    """
    Render an email using app/templates/emails/.
    """

    context.setdefault("website_url", "https://wheelq.co.ke")
    context.setdefault("current_year", datetime.utcnow().year)

    return render_template(
        f"emails/{template_name}",
        **context
    )


def _admin_email_html(subject, message, details=None):
    """
    Render a separate admin alert without requiring another template.
    Jinja autoescaping protects dynamic values.
    """

    details_html = ""

    if details:
        rows = "".join(
            f"<p><strong>{escape(str(key))}:</strong> "
            f"{escape(str(value))}</p>"
            for key, value in details.items()
        )

        details_html = f'<div style="background:#f7f7f7;padding:15px;border-left:4px solid #f5c518;">{rows}</div>'

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;background:#f4f4f4;font-family:Arial,sans-serif;">
        <div style="max-width:620px;margin:30px auto;background:white;border-radius:10px;overflow:hidden;">
            <div style="background:#171717;padding:25px;text-align:center;border-bottom:5px solid #f5c518;">
                <h1 style="color:#f5c518;margin:0;">WHEELQ</h1>
                <p style="color:white;">Tours &amp; Car Hire - Admin Notification</p>
            </div>
            <div style="padding:30px;color:#333;line-height:1.6;">
                <h2 style="color:#b30000;">{escape(str(subject))}</h2>
                <p>{escape(str(message))}</p>
                {details_html}
            </div>
            <div style="background:#171717;color:white;padding:15px;text-align:center;font-size:12px;">
                WheelQ Tours &amp; Car Hire
            </div>
        </div>
    </body>
    </html>
    """


def _make_pdf(title, reference, customer_name, customer_email,
              description, amount, item_description):
    """
    Generate a PDF attachment using the existing document service.
    """

    return generate_document(
        title=title,
        reference=reference,
        customer_name=customer_name,
        customer_email=customer_email,
        items=[(item_description, amount)],
        total=amount,
        description=description
    )


def _queue_safely(**kwargs):
    """
    Attempt to queue an email without interrupting other notifications.
    """

    try:
        return queue_email(**kwargs)

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Failed to queue WheelQ email: %s",
            kwargs.get("event_key")
        )

        return None


def _send_customer_and_admin(
    event_key,
    event_type,
    record,
    customer_email,
    customer_subject,
    customer_template,
    customer_context,
    customer_message,
    admin_subject,
    admin_message,
    admin_details=None,
    document=None,
    document_name=None,
):
    """
    Send customer and admin notifications independently.

    A missing customer email or failed customer email does not
    prevent the admin notification from being queued.
    """

    related_model = record.__class__.__name__
    related_id = record.id

    if customer_email:
        html_body = _render_customer_template(
            customer_template,
            customer_context
        )

        _queue_safely(
            event_key=f"{event_key}:customer",
            event_type=event_type,
            recipients=[customer_email],
            subject=customer_subject,
            html_body=html_body,
            text_body=customer_message,
            related_model=related_model,
            related_id=related_id,
            attachment_name=document_name,
            attachment_data=document,
            attachment_mimetype="application/pdf",
        )
    else:
        current_app.logger.warning(
            "No customer email for %s ID %s",
            related_model,
            related_id
        )

    admins = _admin_emails()

    if admins:
        _queue_safely(
            event_key=f"{event_key}:admin",
            event_type=f"{event_type}_admin",
            recipients=admins,
            subject=admin_subject,
            html_body=_admin_email_html(
                admin_subject,
                admin_message,
                admin_details
            ),
            text_body=admin_message,
            related_model=related_model,
            related_id=related_id,
        )
    else:
        current_app.logger.warning(
            "No admin email configured for %s ID %s",
            related_model,
            related_id
        )


# ==========================================================
# 1. BOOKING CREATED
# ==========================================================

def notify_booking_created(booking_id):
    booking = db.session.get(Booking, booking_id)

    if not booking:
        current_app.logger.warning(
            "Booking notification skipped: booking %s not found",
            booking_id
        )
        return

    car = _value(booking, "car")
    car_name = _value(car, "name", "Vehicle")
    registration = _value(car, "registration_number", "To be confirmed")

    customer_name = _customer_name(booking)
    customer_email = _customer_email(booking)

    reference = f"WQ-BKG-{booking.id}"

    pickup_date = _format_date(
        _value(booking, "pickup_date")
    )
    return_date = _format_date(
        _value(booking, "dropoff_date")
    )

    pickup_location = (
        _value(booking, "pickup_location")
        or _value(booking, "area_of_usage")
        or "As agreed"
    )

    amount = _money_text(_value(booking, "amount"))

    context = {
        "customer_name": customer_name,
        "booking_reference": reference,
        "car_name": car_name,
        "registration_number": registration,
        "pickup_date": pickup_date,
        "return_date": return_date,
        "pickup_location": pickup_location,
        "amount": amount,
        "booking_status": _value(booking, "status", "Pending"),
    }

    _send_customer_and_admin(
        event_key=f"booking:{booking.id}",
        event_type="booking_confirmation",
        record=booking,
        customer_email=customer_email,
        customer_subject=f"Your WheelQ booking confirmation - {reference}",
        customer_template="booking_confirmation.html",
        customer_context=context,
        customer_message=(
            f"Your booking request for {car_name} has been received. "
            "Our team will contact you regarding the next steps."
        ),
        admin_subject=f"New booking received - {reference}",
        admin_message=f"A new booking has been created for {car_name}.",
        admin_details={
            "Reference": reference,
            "Customer": customer_name,
            "Customer email": customer_email or "Not provided",
            "Vehicle": car_name,
            "Registration": registration,
            "Pickup date": pickup_date,
            "Return date": return_date,
            "Amount": amount,
            "Status": _value(booking, "status", "Pending"),
        },
    )


# ==========================================================
# 2. FINANCIAL CHARGE CREATED - INVOICE
# ==========================================================

def notify_financial_charge_created(charge_id):
    charge = db.session.get(FinancialCharge, charge_id)

    if not charge:
        return

    customer = _value(charge, "client")
    booking = _value(charge, "booking")

    customer_name = (
        _value(customer, "name")
        or _value(booking, "client_name")
        or "Customer"
    )

    customer_email = _customer_email(charge)

    reference = f"WQ-INV-{charge.id}"
    amount = _money(_value(charge, "amount_charged"))

    description = _value(
        charge, "description", "Financial charge"
    )

    pdf = _make_pdf(
        title="Invoice",
        reference=reference,
        customer_name=customer_name,
        customer_email=customer_email,
        description="Please find your invoice attached.",
        amount=amount,
        item_description=description,
    )

    context = {
        "customer_name": customer_name,
        "invoice_number": reference,
        "description": description,
        "invoice_date": _format_date(
            _value(charge, "created_at")
        ),
        "amount": _money_text(amount),
        "payment_status": _value(
            charge, "payment_status", "Unpaid"
        ),
    }

    _send_customer_and_admin(
        event_key=f"financial-charge:{charge.id}",
        event_type="financial_invoice",
        record=charge,
        customer_email=customer_email,
        customer_subject=f"WheelQ invoice - {reference}",
        customer_template="invoice.html",
        customer_context=context,
        customer_message="Your invoice is attached to this email.",
        admin_subject=f"New financial charge - {reference}",
        admin_message=f"A financial charge of {_money_text(amount)} was created.",
        admin_details={
            "Invoice": reference,
            "Customer": customer_name,
            "Customer email": customer_email or "Not provided",
            "Description": description,
            "Amount": _money_text(amount),
        },
        document=pdf,
        document_name=f"{reference}.pdf",
    )


# ==========================================================
# 3. FINANCIAL PAYMENT - RECEIPT
# ==========================================================

def notify_payment_received(payment_id):
    payment = db.session.get(FinancialPayment, payment_id)

    if not payment or _value(payment, "status") != "success":
        return

    charge = _value(payment, "charge")

    if not charge:
        return

    customer_name = _customer_name(charge)
    customer_email = _customer_email(charge)

    reference = (
        _value(payment, "reference")
        or f"WQ-RCP-{payment.id}"
    )

    amount = _money(_value(payment, "amount"))
    description = _value(
        charge, "description", "Customer payment"
    )

    pdf = _make_pdf(
        title="Payment Receipt",
        reference=reference,
        customer_name=customer_name,
        customer_email=customer_email,
        description="We confirm receipt of your payment.",
        amount=amount,
        item_description=description,
    )

    balance = _money_text(
        _value(charge, "amount_remaining")
    )

    context = {
        "customer_name": customer_name,
        "receipt_number": reference,
        "payment_date": _format_datetime(
            _value(payment, "received_at")
        ),
        "description": description,
        "payment_method": _value(
            payment, "payment_method", "Not specified"
        ),
        "reference": reference,
        "amount": _money_text(amount),
        "balance": balance,
    }

    _send_customer_and_admin(
        event_key=f"financial-payment:{payment.id}",
        event_type="payment_receipt",
        record=payment,
        customer_email=customer_email,
        customer_subject=f"Payment receipt - {reference}",
        customer_template="payment_receipt.html",
        customer_context=context,
        customer_message=(
            "Your payment was received successfully. "
            "Your receipt is attached."
        ),
        admin_subject=f"Payment received - {reference}",
        admin_message=f"A customer payment of {_money_text(amount)} was received.",
        admin_details={
            "Receipt": reference,
            "Customer": customer_name,
            "Customer email": customer_email or "Not provided",
            "Amount received": _money_text(amount),
            "Payment method": _value(payment, "payment_method", "Not specified"),
            "Outstanding balance": balance,
        },
        document=pdf,
        document_name=f"{reference}.pdf",
    )


# ==========================================================
# 4. LEASE CREATED
# ==========================================================

def notify_lease_created(lease_id):
    lease = db.session.get(Lease, lease_id)

    if not lease:
        return

    customer_email = _customer_email(lease)

    customer_name = (
        _value(lease, "owner_name")
        or "Investor"
    )

    reference = f"WQ-LSE-{lease.id}"

    context = {
        "customer_name": customer_name,
        "lease_reference": reference,
        "car_model": _value(lease, "car_model", "Not specified"),
        "car_year": _value(lease, "car_year", "Not specified"),
        "registration_number": _value(lease, "car_plate", "Not specified"),
        "total_amount": _money_text(
            _value(lease, "agreed_amount")
        ),
    }

    _send_customer_and_admin(
        event_key=f"lease:{lease.id}",
        event_type="lease_confirmation",
        record=lease,
        customer_email=customer_email,
        customer_subject=f"WheelQ lease confirmation - {reference}",
        customer_template="lease_payment_receipt.html",
        customer_context={
            **context,
            "receipt_number": reference,
            "payment_date": _format_date(
                _value(lease, "created_at")
            ),
            "payment_method": "Lease record created",
            "reference": reference,
            "amount": "Not applicable",
            "balance": _money_text(
                _value(lease, "agreed_amount")
            ),
        },
        customer_message=(
            "Your lease record has been created. "
            "Please contact our team if you need clarification."
        ),
        admin_subject=f"New lease created - {reference}",
        admin_message=f"A new lease record has been created for {customer_name}.",
        admin_details={
            "Lease reference": reference,
            "Owner": customer_name,
            "Email": customer_email or "Not provided",
            "Vehicle": _value(lease, "car_model", "Not specified"),
            "Registration": _value(lease, "car_plate", "Not specified"),
            "Agreed amount": _money_text(
                _value(lease, "agreed_amount")
            ),
        },
    )


# ==========================================================
# 5. LEASE PAYMENT - RECEIPT
# ==========================================================

def notify_lease_payment_received(payment_id):
    payment = db.session.get(LeasePayment, payment_id)

    if not payment or not _value(payment, "lease_id"):
        return

    lease = _value(payment, "lease")

    if not lease:
        return

    customer_email = _customer_email(payment)
    customer_name = (
        _value(payment, "investor_name")
        or _value(lease, "owner_name")
        or "Investor"
    )

    reference = (
        _value(payment, "reference")
        or f"WQ-LPR-{payment.id}"
    )

    amount = _money(_value(payment, "amount"))

    car_model = _value(lease, "car_model", "Vehicle")
    car_plate = _value(lease, "car_plate", "Not specified")

    total_amount = _money(_value(lease, "agreed_amount"))

    balance = _money(
        _value(lease, "outstanding_amount")
    )

    pdf = _make_pdf(
        title="Lease Payment Receipt",
        reference=reference,
        customer_name=customer_name,
        customer_email=customer_email,
        description="We confirm receipt of your lease payment.",
        amount=amount,
        item_description="Lease payment",
    )

    context = {
        "customer_name": customer_name,
        "receipt_number": reference,
        "car_model": car_model,
        "registration_number": car_plate,
        "payment_date": _format_datetime(
            _value(payment, "created_at")
        ),
        "payment_method": _value(
            payment, "payment_method", "Not specified"
        ),
        "reference": reference,
        "amount": _money_text(amount),
        "total_amount": _money_text(total_amount),
        "balance": _money_text(balance),
    }

    _send_customer_and_admin(
        event_key=f"lease-payment:{payment.id}",
        event_type="lease_payment_receipt",
        record=payment,
        customer_email=customer_email,
        customer_subject=f"Lease payment receipt - {reference}",
        customer_template="lease_payment_receipt.html",
        customer_context=context,
        customer_message=(
            "Your lease payment has been recorded. "
            "Your receipt is attached."
        ),
        admin_subject=f"Lease payment recorded - {reference}",
        admin_message=f"A lease payment of {_money_text(amount)} was recorded.",
        admin_details={
            "Receipt": reference,
            "Investor": customer_name,
            "Email": customer_email or "Not provided",
            "Vehicle": car_model,
            "Registration": car_plate,
            "Amount paid": _money_text(amount),
            "Lease balance": _money_text(balance),
        },
        document=pdf,
        document_name=f"{reference}.pdf",
    )


# ==========================================================
# 6. PENALTY AWARDED
# ==========================================================

def notify_penalty_awarded(penalty_id):
    penalty = db.session.get(LatePenalty, penalty_id)

    if not penalty:
        return

    booking = _value(penalty, "booking")

    if not booking:
        return

    customer_email = _customer_email(booking)
    customer_name = _customer_name(booking)

    car = _value(booking, "car")

    car_name = _value(car, "name", "Vehicle")

    registration = (
        _value(penalty, "registration_number")
        or _value(car, "registration_number")
        or "Not specified"
    )

    reference = f"WQ-PEN-{penalty.id}"
    amount = _money(_value(penalty, "amount"))

    expected_return = (
        _format_datetime(_value(booking, "dropoff_date"))
    )

    hours_late = _value(penalty, "hours_late", 0)

    pdf = _make_pdf(
        title="Late Return Penalty Notice",
        reference=reference,
        customer_name=customer_name,
        customer_email=customer_email,
        description=(
            f"Hours late: {hours_late}. "
            "Please contact WheelQ if you have questions about this charge."
        ),
        amount=amount,
        item_description="Late return penalty",
    )

    context = {
        "customer_name": customer_name,
        "booking_reference": f"WQ-BKG-{booking.id}",
        "car_name": car_name,
        "registration_number": registration,
        "expected_return": expected_return,
        "hours_late": hours_late,
        "amount": _money_text(amount),
        "payment_status": _value(penalty, "status", "Unpaid"),
    }

    _send_customer_and_admin(
        event_key=f"penalty:{penalty.id}",
        event_type="penalty_notice",
        record=penalty,
        customer_email=customer_email,
        customer_subject=f"WheelQ penalty notice - {reference}",
        customer_template="penalty_notice.html",
        customer_context=context,
        customer_message=(
            "A late return penalty has been recorded. "
            "Please see the attached notice."
        ),
        admin_subject=f"Penalty awarded - {reference}",
        admin_message=f"A penalty of {_money_text(amount)} has been awarded.",
        admin_details={
            "Penalty reference": reference,
            "Customer": customer_name,
            "Customer email": customer_email or "Not provided",
            "Vehicle": car_name,
            "Registration": registration,
            "Hours late": hours_late,
            "Amount": _money_text(amount),
            "Status": _value(penalty, "status", "Unpaid"),
        },
        document=pdf,
        document_name=f"{reference}.pdf",
    )


# ==========================================================
# 7. AIRPORT TRANSFER CREATED
# ==========================================================

def notify_airport_transfer_created(transfer_id):
    transfer = db.session.get(AirportTransfer, transfer_id)

    if not transfer:
        return

    reference = f"WQ-TRF-{transfer.id}"

    customer_name = _customer_name(transfer)
    customer_email = _customer_email(transfer)

    car = _value(transfer, "car")
    car_name = _value(car, "name", "To be confirmed")

    pickup_datetime = _format_datetime(
        _value(transfer, "pickup_datetime")
    )

    pickup_location = _value(
        transfer, "pickup_location", "Not specified"
    )

    dropoff_location = _value(
        transfer, "dropoff_location", "Not specified"
    )

    passengers = _value(transfer, "passengers", "Not specified")
    airport = _value(transfer, "airport", "Not specified")

    context = {
        "customer_name": customer_name,
        "transfer_reference": reference,
        "airport": airport,
        "pickup_location": pickup_location,
        "dropoff_location": dropoff_location,
        "pickup_datetime": pickup_datetime,
        "passengers": passengers,
        "car_name": car_name,
        "transfer_status": _value(
            transfer, "status", "Pending confirmation"
        ),
    }

    _send_customer_and_admin(
        event_key=f"airport-transfer:{transfer.id}",
        event_type="airport_transfer",
        record=transfer,
        customer_email=customer_email,
        customer_subject=f"Airport transfer confirmation - {reference}",
        customer_template="airport_transfer_confirmation.html",
        customer_context=context,
        customer_message=(
            "Your airport transfer request has been received. "
            "Our team will contact you to confirm the arrangements."
        ),
        admin_subject=f"New airport transfer - {reference}",
        admin_message=(
            f"A new airport transfer request was submitted by "
            f"{customer_name}."
        ),
        admin_details={
            "Transfer reference": reference,
            "Customer": customer_name,
            "Customer email": customer_email or "Not provided",
            "Airport": airport,
            "Pickup": pickup_location,
            "Drop-off": dropoff_location,
            "Pickup date": pickup_datetime,
            "Passengers": passengers,
            "Vehicle": car_name,
        },
    )
