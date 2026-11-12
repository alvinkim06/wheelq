
from datetime import datetime

from flask import current_app
from flask_mail import Message

from app import db, mail
from app.models import EmailOutbox


def queue_email(
    event_key,
    event_type,
    recipients,
    subject,
    html_body,
    text_body=None,
    related_model=None,
    related_id=None,
    attachment_name=None,
    attachment_data=None,
    attachment_mimetype="application/pdf"
):
    """
    Save an email to the outbox and attempt delivery.

    event_key must be unique for the business event and recipient group.
    """

    recipients = [
        email.strip()
        for email in recipients
        if email and email.strip()
    ]

    if not recipients:
        current_app.logger.warning(
            "Email not queued: no recipients for %s", event_key
        )
        return None

    existing = EmailOutbox.query.filter_by(
        event_key=event_key
    ).first()

    if existing:
        return existing

    record = EmailOutbox(
        event_key=event_key,
        event_type=event_type,
        related_model=related_model,
        related_id=related_id,
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body or "",
        attachment_name=attachment_name,
        attachment_data=attachment_data,
        attachment_mimetype=attachment_mimetype,
        status="pending"
    )

    db.session.add(record)
    db.session.commit()

    send_outbox_email(record.id)

    return record


def send_outbox_email(email_id):
    """
    Attempt to send one queued email.

    Failure is recorded without changing the original business record.
    """

    record = db.session.get(EmailOutbox, email_id)

    if not record or record.status == "sent":
        return False

    record.attempts = (record.attempts or 0) + 1

    try:
        message = Message(
            subject=record.subject,
            recipients=record.recipients,
            body=record.text_body,
            html=record.html_body
        )

        if record.attachment_data:
            message.attach(
                record.attachment_name or "wheelq-document.pdf",
                record.attachment_mimetype or "application/pdf",
                record.attachment_data
            )

        mail.send(message)

        record.status = "sent"
        record.sent_at = datetime.utcnow()
        record.last_error = None

        db.session.commit()

        return True

    except Exception as exc:
        db.session.rollback()

        record = db.session.get(EmailOutbox, email_id)
        if record:
            record.status = "failed"
            record.last_error = str(exc)
            db.session.commit()

        current_app.logger.exception(
            "WheelQ email delivery failed: %s", email_id
        )

        return False


def retry_failed_email(email_id):
    record = db.session.get(EmailOutbox, email_id)

    if not record or record.status == "sent":
        return False

    record.status = "pending"
    record.last_error = None
    db.session.commit()

    return send_outbox_email(record.id)
