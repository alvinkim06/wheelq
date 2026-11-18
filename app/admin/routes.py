# app/admin/routes.py
import os
import uuid
from app.services.notification_service import ( notify_booking_created, notify_financial_charge_created, notify_payment_received,
    notify_lease_created,
    notify_lease_payment_received,
    notify_penalty_awarded,
    notify_airport_transfer_created
)
from werkzeug.utils import secure_filename
from flask import send_from_directory, abort, g
from functools import wraps
from flask_jwt_extended import (create_access_token,set_access_cookies,unset_jwt_cookies, verify_jwt_in_request, get_jwt, get_jwt_identity, jwt_required)
from flask import (
    render_template, request, redirect, url_for, flash, session, current_app, jsonify, abort, send_file 
)
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from app.utils.cache import cache_delete,cache_get,cache_set,invalidate_admin_dashboard
from werkzeug.utils import secure_filename
from app.admin import admin
from app import db, mail
from app.models import Car, Booking, Client, AdminUser, Notification, Lease, ManualFinancialEntry, FinancialRecord, LeasePayment, DamageCharge, LatePenalty, ContactMessage, AirportTransfer, ClientBlacklist, ClientDocument, FinancialAdjustment, FinancialPayment, FinancialCharge, PenaltySetting
from datetime import datetime,date, timedelta
from app.utils.paystack import Paystack
from app.utils.sms import send_sms
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation
from math import ceil
from datetime import datetime, date, time
from collections import defaultdict, Counter
from calendar import monthrange
from flask_mail import Message



# mpesa_client = MpesaDaraja(
   
#             consumer_key="u7QYXEYKb3zh3sMwmCNIAAiHd7OFd7tmEjmxsL8PWlzmAluS",
#             consumer_secret="qc3j8xBsEAXQF2BAJCoiE8FAuTf0lNOqoTWR4y4aGFtmzqvfmpSvnoCpwqJMs00A",
#             shortcode="600001",
#             passkey="bfb279f9aa9bdbcf158e97dd33f9d54e",
#             callback_url="https://claude-saprophagous-dalia.ngrok-free.dev/mpesa/callback",
#             environment="sandbox"
# )



# --- CONFIG ---
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}

PUBLIC_CARS_FOLDER = os.path.join(current_app.root_path, "..", "public", "static", "cars") if False else None
# We'll compute proper path inside functions because current_app isn't available at import time.


INSURANCE_ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp", "pdf"
}

# ================= CLIENT DOCUMENT STORAGE =================

# CLIENT_DOCUMENT_FOLDER = os.path.join(
#     current_app.root_path,
#     "..",
#     "instance",
#     "client_documents"
# )

DOCUMENT_MAX_SIZE = 10 * 1024 * 1024  # 10 MB per file

SOCIAL_PLATFORMS = {
    "Facebook", "Instagram", "TikTok",
    "WhatsApp", "X", "Other"
}


def client_document_folder():
    """Private storage location outside the public static directory."""
    return os.path.join(current_app.instance_path, "client_documents")


def validate_document_bytes(content, document_type, filename):
    """Validate file extension and actual file signature."""
    extension = os.path.splitext(secure_filename(filename))[1].lower()

    if not content:
        raise ValueError("The uploaded file is empty.")

    if len(content) > DOCUMENT_MAX_SIZE:
        raise ValueError("Each document must be 10 MB or smaller.")

    if document_type == "mpesa_statement":
        if extension != ".pdf" or not content.startswith(b"%PDF-"):
            raise ValueError("Upload a valid M-Pesa PDF statement.")

        # Also check that the PDF can actually be parsed.
        try:
            PdfReader(BytesIO(content), strict=True)
        except Exception as exc:
            raise ValueError("The PDF file is damaged or invalid.") from exc

        return "application/pdf", extension

    if document_type == "social_media":
        valid_signatures = {
            ".jpg": content.startswith(b"\xff\xd8\xff"),
            ".jpeg": content.startswith(b"\xff\xd8\xff"),
            ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            ".webp": (
                len(content) >= 12
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            ),
        }

        if extension not in valid_signatures or not valid_signatures[extension]:
            raise ValueError("Upload a valid JPG, PNG, or WEBP image.")

        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }

        return mime_types[extension], extension

    raise ValueError("Unsupported document type.")


def store_client_document(content, original_filename, document_type):
    """Save validated bytes using a random filename in private storage."""
    mime_type, extension = validate_document_bytes(
        content, document_type, original_filename
    )

    folder = client_document_folder()
    os.makedirs(folder, mode=0o700, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    destination = os.path.join(folder, stored_filename)

    with open(destination, "xb") as file:
        file.write(content)

    return {
        "file_path": destination,
        "original_filename": secure_filename(original_filename),
        "mime_type": mime_type,
    }


def verify_mpesa_pdf_password(content, password):
    """Verify the PDF's existing password without storing it."""
    if not password:
        raise ValueError("Enter the M-Pesa PDF password.")

    try:
        reader = PdfReader(BytesIO(content), strict=True)

        if not reader.is_encrypted:
            raise ValueError(
                "This statement is not password-protected. "
                "Upload the original password-protected PDF."
            )

        if reader.decrypt(password) == 0:
            raise ValueError("Incorrect M-Pesa PDF password.")

        if len(reader.pages) == 0:
            raise ValueError("The PDF does not contain any pages.")

        return reader

    except ValueError:
        raise
    except Exception as exc:
        current_app.logger.exception("Unable to verify M-Pesa PDF")
        raise ValueError("Unable to read this PDF statement.") from exc


def decrypt_mpesa_pdf_for_view(content, password):
    """Decrypt a verified PDF in memory for this viewing request only."""
    reader = verify_mpesa_pdf_password(content, password)

    try:
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        output.seek(0)

        return output

    except Exception as exc:
        current_app.logger.exception("Unable to prepare M-Pesa PDF for viewing")
        raise ValueError("Unable to prepare this statement for viewing.") from exc


def get_private_document_path(document):
    """Ensure the stored path cannot escape the private document directory."""
    folder = os.path.realpath(client_document_folder())
    path = os.path.realpath(document.file_path)

    if os.path.commonpath([folder, path]) != folder:
        current_app.logger.error("Invalid client document storage path")
        abort(404)

    if not os.path.isfile(path):
        abort(404)

    return path

def get_client_document_folder():
    return os.path.join(
        current_app.instance_path,
        "client_documents"
    )


def save_client_document(file, document_type):
    """Save a client document outside the public static directory."""

    if not file or not file.filename:
        return None

    original_filename = secure_filename(file.filename)
    extension = os.path.splitext(original_filename)[1].lower()

    if document_type == "mpesa_statement":
        if extension != ".pdf":
            raise ValueError("M-Pesa statements must be PDF files.")

    elif document_type == "social_media":
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError(
                "Social media screenshots must be JPG, PNG or WEBP images."
            )

    else:
        raise ValueError("Invalid document type.")

    content = file.read()

    if not content:
        raise ValueError("The uploaded file is empty.")

    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Each document must be smaller than 10 MB.")

    if document_type == "mpesa_statement":
        if not content.startswith(b"%PDF-"):
            raise ValueError("The uploaded file is not a valid PDF.")

    elif not content.startswith((
        b"\xff\xd8\xff",
        b"\x89PNG\r\n\x1a\n",
        b"RIFF"
    )):
        raise ValueError("The uploaded file is not a supported image.")

    folder = get_client_document_folder()
    os.makedirs(folder, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    destination = os.path.join(folder, stored_filename)

    with open(destination, "wb") as document:
        document.write(content)

    return {
        "file_path": destination,
        "original_filename": original_filename,
        "mime_type": file.mimetype
    }


def verify_mpesa_pdf_password(pdf_bytes, password):
    """Check whether the supplied password opens the encrypted PDF."""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))

        if not reader.is_encrypted:
            raise ValueError(
                "This PDF is not password-protected. "
                "Please upload the original password-protected M-Pesa statement."
            )

        if not password or reader.decrypt(password) == 0:
            raise ValueError("Incorrect M-Pesa statement password.")

        if len(reader.pages) == 0:
            raise ValueError("The PDF contains no pages.")

        return True

    except ValueError:
        raise

    except Exception as exc:
        current_app.logger.exception("M-Pesa PDF validation failed")
        raise ValueError("Could not read this PDF. Check that it is valid.") from exc


def save_insurance_document(file):
    if not file or not file.filename:
        return None

    original_name = secure_filename(file.filename)

    if "." not in original_name:
        raise ValueError("Invalid insurance document filename.")

    extension = original_name.rsplit(".", 1)[1].lower()

    if extension not in INSURANCE_ALLOWED_EXTENSIONS:
        raise ValueError(
            "Only JPG, JPEG, PNG, WEBP and PDF files are allowed."
        )

    upload_folder = os.path.join(
        current_app.instance_path,
        "insurance_documents"
    )

    os.makedirs(upload_folder, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{extension}"
    file.save(os.path.join(upload_folder, filename))

    return filename


def delete_insurance_document(filename):
    if not filename:
        return

    upload_folder = os.path.join(
        current_app.instance_path,
        "insurance_documents"
    )

    file_path = os.path.join(upload_folder, os.path.basename(filename))

    if os.path.isfile(file_path):
        os.remove(file_path)

def save_public_upload(file, allowed_extensions=None):
    """
    Save a public image/document using a unique filename.
    Returns only the filename stored in the database.
    """
    if not file or not file.filename:
        return None

    filename = secure_filename(file.filename)

    if not filename or "." not in filename:
        raise ValueError("Invalid uploaded filename.")

    extension = filename.rsplit(".", 1)[1].lower()

    allowed = (
        allowed_extensions
        if allowed_extensions is not None
        else ALLOWED_EXTENSIONS
    )

    if extension not in allowed:
        raise ValueError("Uploaded file type is not allowed.")

    upload_folder = current_app.config.get("UPLOAD_FOLDER")

    if not upload_folder:
        upload_folder = os.path.join(
            current_app.static_folder,
            "uploads"
        )

    os.makedirs(upload_folder, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(upload_folder, stored_filename)

    file.save(file_path)

    return stored_filename


def save_file(field_name):
    return save_public_upload(
        request.files.get(field_name),
        ALLOWED_EXTENSIONS
    )

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS



def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request(locations=["cookies"])
        except Exception:
            return redirect(url_for("admin.admin_login"))

        return fn(*args, **kwargs)

    return wrapper


# ---------- AUTH HELPERS ----------

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            verify_jwt_in_request(locations=["cookies"])
        except Exception:
            return redirect(url_for("admin.admin_login"))

        return f(*args, **kwargs)

    return wrapped



def role_required(roles):
    """roles: list or tuple of allowed roles"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "admin_id" not in session:
                return redirect(url_for("admin.admin_login"))
            user_role = session.get("admin_role")
            if user_role not in roles:
                flash("You do not have permission to view that page.", "danger")
                return redirect(url_for("admin.dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def get_current_admin_id():
    admin = get_logged_in_admin()
    return admin.id if admin else None


def get_or_create_penalty_setting():
    setting = PenaltySetting.query.filter_by(is_active=True).first()

    if not setting:
        setting = PenaltySetting(
            rate=Decimal("500.00"),
            interval_minutes=30,
            grace_period_minutes=0,
            is_active=True
        )
        db.session.add(setting)
        db.session.flush()

    return setting


def calculate_late_penalty(
    expected_return,
    actual_return,
    rate,
    interval_minutes,
    grace_period_minutes
):
    if interval_minutes <= 0:
        raise ValueError("Penalty interval must be greater than zero.")

    if actual_return <= expected_return:
        return {
            "minutes_late": 0,
            "chargeable_minutes": 0,
            "intervals_charged": 0,
            "amount": Decimal("0.00")
        }

    minutes_late = ceil(
        (actual_return - expected_return).total_seconds() / 60
    )

    chargeable_minutes = max(
        0,
        minutes_late - grace_period_minutes
    )

    intervals = (
        ceil(chargeable_minutes / interval_minutes)
        if chargeable_minutes else 0
    )

    amount = Decimal(str(rate)) * intervals

    return {
        "minutes_late": minutes_late,
        "chargeable_minutes": chargeable_minutes,
        "intervals_charged": intervals,
        "amount": amount.quantize(Decimal("0.01"))
    }


def create_financial_charge(
    client_id,
    booking_id,
    category,
    description,
    amount,
    airport_transfer_id=None
):
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))

    if amount <= 0:
        raise ValueError("Charge amount must be greater than zero.")

    charge = FinancialCharge(
        client_id=client_id,
        booking_id=booking_id,
        airport_transfer_id=airport_transfer_id,
        category=category,
        description=description,
        amount_charged=amount,
        created_by=get_current_admin_id()
    )

    db.session.add(charge)
    db.session.flush()

    db.session.add(charge)
    db.session.commit()

    try:
        notify_financial_charge_created(charge.id)
    except Exception:
        current_app.logger.exception(
            "Financial charge email notification failed"
        )

    return charge



def parse_transfer_price(raw_price):
    """Validate and normalize an airport-transfer price."""
    try:
        amount = Decimal(str(raw_price)).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid airport-transfer price.")

    if amount <= 0:
        raise ValueError(
            "Airport-transfer price must be greater than zero."
        )

    return amount


def airport_transfer_charge_description(transfer):
    return (
        f"Airport transfer: {transfer.name} | "
        f"{transfer.pickup_location} to {transfer.dropoff_location}"
    )


def save_airport_transfer_charge(transfer, amount):
    charge = transfer.financial_charge

    if charge:
        received = Decimal(str(charge.amount_received or 0))

        if amount < received:
            raise ValueError(
                "The transfer price cannot be less than the amount "
                "already received."
            )

        charge.amount_charged = amount
        charge.category = "airport_transfer"
        charge.description = airport_transfer_charge_description(transfer)

    else:
        create_financial_charge(
            client_id=None,
            booking_id=None,
            category="airport_transfer",
            description=airport_transfer_charge_description(transfer),
            amount=amount,
            airport_transfer_id=transfer.id
        )



def sync_car_status(car):
    """
    A vehicle is booked if it has an approved/active rental
    or an airport transfer that has not reached a terminal status.
    """
    if not car:
        return

    active_booking = Booking.query.filter(
        Booking.car_id == car.id,
        Booking.status.in_(["approved", "active"])
    ).first()

    active_transfer = AirportTransfer.query.filter(
        AirportTransfer.car_id == car.id,
        AirportTransfer.status.notin_(
            ["cancelled", "rejected", "completed"]
        )
    ).first()

    car.status = (
        "booked"
        if active_booking or active_transfer
        else "available"
    )
# ==========================================================
# ACCOUNT MANAGEMENT
# ==========================================================




def get_logged_in_admin():
    """Retrieve the actual account associated with the JWT."""
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None

    user = db.session.get(AdminUser, user_id)

    if not user or not user.is_active:
        return None

    return user


@admin.app_context_processor
def inject_admin_context():
    try:
        verify_jwt_in_request(
            optional=True,
            locations=["cookies"]
        )
        user = get_logged_in_admin()

        return {
            "current_user_role": (
                user.role.strip().lower() if user else None
            ),
            "current_admin_id": user.id if user else None
        }

    except Exception:
        return {
            "current_user_role": None,
            "current_admin_id": None
        }




def account_required(fn):
    """Require a valid JWT and active account."""
    from functools import wraps

    @wraps(fn)
    @jwt_required(locations=["cookies"])
    def wrapper(*args, **kwargs):
        user = get_logged_in_admin()

        if not user:
            response = redirect(url_for("admin.admin_login"))
            unset_jwt_cookies(response)
            return response

        return fn(*args, **kwargs)

    return wrapper


def account_admin_required(fn):
    """Allow only administrator accounts."""
    from functools import wraps

    @wraps(fn)
    @jwt_required(locations=["cookies"])
    def wrapper(*args, **kwargs):
        user = get_logged_in_admin()

        if not user:
            response = redirect(url_for("admin.admin_login"))
            unset_jwt_cookies(response)
            return response

        if user.role.strip().lower() != "admin":
            flash("Administrator access required.", "danger")
            return redirect(url_for("admin.my_account"))

        return fn(*args, **kwargs)

    return wrapper


@admin.route(
    "/clients/<int:client_id>/documents/upload",
    methods=["POST"]
)
@account_required
def upload_client_document(client_id):
    client = Client.query.get_or_404(client_id)

    document_type = request.form.get("document_type", "").strip()
    uploaded_files = []
    created_records = []

    try:
        admin_user = get_logged_in_admin()

        if not admin_user:
            abort(403)

        if document_type == "mpesa_statement":
            uploaded_file = request.files.get("mpesa_statement")
            password = request.form.get("mpesa_password", "")

            if not uploaded_file or not uploaded_file.filename:
                raise ValueError("Select an M-Pesa statement PDF.")

            content = uploaded_file.read()
            verify_mpesa_pdf_password(content, password)

            saved = store_client_document(
                content,
                uploaded_file.filename,
                "mpesa_statement"
            )
            uploaded_files.append(saved["file_path"])

            record = ClientDocument(
                client_id=client.id,
                document_type="mpesa_statement",
                file_path=saved["file_path"],
                original_filename=saved["original_filename"],
                mime_type=saved["mime_type"],
                uploaded_by=admin_user.id
            )
            db.session.add(record)
            created_records.append(record)

        elif document_type == "social_media":
            platform = request.form.get("platform", "").strip()
            description = request.form.get("description", "").strip()

            if platform not in SOCIAL_PLATFORMS:
                raise ValueError("Select a valid social media platform.")

            if len(description) > 2000:
                raise ValueError("The description is too long.")

            files = [
                file for file in request.files.getlist("social_media_screenshots")
                if file and file.filename
            ]

            if not files:
                raise ValueError("Select at least one screenshot.")

            if len(files) > 10:
                raise ValueError("You can upload a maximum of 10 screenshots at once.")

            for uploaded_file in files:
                content = uploaded_file.read()

                saved = store_client_document(
                    content,
                    uploaded_file.filename,
                    "social_media"
                )
                uploaded_files.append(saved["file_path"])

                record = ClientDocument(
                    client_id=client.id,
                    document_type="social_media",
                    platform=platform,
                    description=description or None,
                    file_path=saved["file_path"],
                    original_filename=saved["original_filename"],
                    mime_type=saved["mime_type"],
                    uploaded_by=admin_user.id
                )
                db.session.add(record)
                created_records.append(record)

        else:
            raise ValueError("Select a valid document type.")

        db.session.commit()

        flash("Document uploaded successfully.", "success")

    except ValueError as exc:
        db.session.rollback()

        for path in uploaded_files:
            if os.path.isfile(path):
                os.remove(path)

        flash(str(exc), "danger")

    except Exception:
        db.session.rollback()

        for path in uploaded_files:
            if os.path.isfile(path):
                os.remove(path)

        current_app.logger.exception(
            "Client document upload failed for client %s", client.id
        )
        flash("The upload failed. Please try again.", "danger")

    return redirect(url_for("admin.client_details", client_id=client.id))


@admin.route(
    "/client-documents/<int:document_id>/view",
    methods=["GET", "POST"]
)
@account_required
def view_client_document(document_id):
    document = ClientDocument.query.get_or_404(document_id)
    path = get_private_document_path(document)

    if document.document_type == "social_media":
        if request.method != "GET":
            abort(405)

        return send_file(
            path,
            mimetype=document.mime_type or "application/octet-stream",
            as_attachment=False,
            download_name=document.original_filename,
            conditional=True
        )

    if document.document_type == "mpesa_statement":
        if request.method != "POST":
            abort(405)

        password = request.form.get("mpesa_password", "")

        try:
            with open(path, "rb") as file:
                encrypted_content = file.read()

            decrypted_pdf = decrypt_mpesa_pdf_for_view(
                encrypted_content,
                password
            )

            response = send_file(
                decrypted_pdf,
                mimetype="application/pdf",
                as_attachment=False,
                download_name=document.original_filename
            )

            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"

            return response

        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(
                url_for(
                    "admin.client_details",
                    client_id=document.client_id
                )
            )

    abort(404)

# ----------------------------------------------------------
# MY ACCOUNT
# ----------------------------------------------------------

@admin.route("/my-account", methods=["GET", "POST"])
@account_required
def my_account():
    user = get_logged_in_admin()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect(url_for("admin.my_account"))

        existing = AdminUser.query.filter(
            func.lower(AdminUser.email) == email,
            AdminUser.id != user.id
        ).first()

        if existing:
            flash("That email address is already in use.", "danger")
            return redirect(url_for("admin.my_account"))

        user.name = name
        user.email = email

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Unable to update account. Check the email address.", "danger")
            return redirect(url_for("admin.my_account"))

        # Refresh the identity token after account changes.
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role}
        )

        response = redirect(url_for("admin.my_account"))
        set_access_cookies(response, token)

        flash("Your account details have been updated.", "success")
        return response

    return render_template(
        "my_account.html",
        user=user
    )


@admin.route("/my-account/password", methods=["POST"])
@account_required
def change_my_password():
    user = get_logged_in_admin()

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not user.check_password(current_password):
        flash("Your current password is incorrect.", "danger")
        return redirect(url_for("admin.my_account"))

    if len(new_password) < 8:
        flash("Your new password must contain at least 8 characters.", "danger")
        return redirect(url_for("admin.my_account"))

    if new_password != confirm_password:
        flash("The new passwords do not match.", "danger")
        return redirect(url_for("admin.my_account"))

    user.set_password(new_password)
    db.session.commit()

    # Issue a fresh token.
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role}
    )

    response = redirect(url_for("admin.my_account"))
    set_access_cookies(response, token)

    flash("Your password has been changed successfully.", "success")
    return response


# ----------------------------------------------------------
# STAFF MANAGEMENT
# ----------------------------------------------------------

@admin.route("/staff", methods=["GET", "POST"])
@account_admin_required
def staff_management():
    current_admin = get_logged_in_admin()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff").strip().lower()

        if not name or not email or not password:
            flash("Please complete all required fields.", "danger")
            return redirect(url_for("admin.staff_management"))

        if role not in ("admin", "staff"):
            flash("Invalid account role.", "danger")
            return redirect(url_for("admin.staff_management"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return redirect(url_for("admin.staff_management"))

        if AdminUser.query.filter(
            func.lower(AdminUser.email) == email
        ).first():
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("admin.staff_management"))

        new_user = AdminUser(
            name=name,
            email=email,
            role=role,
            is_active=True
        )
        new_user.set_password(password)

        db.session.add(new_user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Unable to create account. Email may already exist.", "danger")
            return redirect(url_for("admin.staff_management"))

        flash("Account created successfully.", "success")
        return redirect(url_for("admin.staff_management"))

    users = AdminUser.query.order_by(
        AdminUser.created_at.desc()
    ).all()

    return render_template(
        "staff_management.html",
        users=users,
        current_admin_id=current_admin.id
    )


@admin.route("/staff/<int:user_id>/edit", methods=["POST"])
@account_admin_required
def edit_staff(user_id):
    current_admin = get_logged_in_admin()
    user = AdminUser.query.get_or_404(user_id)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "").strip().lower()

    if not name or not email or role not in ("admin", "staff"):
        flash("Invalid account details.", "danger")
        return redirect(url_for("admin.staff_management"))

    if user.id == current_admin.id and role not in ("admin", "super_admin"):
        flash("You cannot remove your own administrator access.", "danger")
        return redirect(url_for("admin.staff_management"))

    duplicate = AdminUser.query.filter(
        func.lower(AdminUser.email) == email,
        AdminUser.id != user.id
    ).first()

    if duplicate:
        flash("That email is already in use.", "danger")
        return redirect(url_for("admin.staff_management"))

    # Prevent removing the final administrator.
    if user.role in ("admin", "super_admin") and role == "staff":
        admin_count = AdminUser.query.filter(
            AdminUser.role.in_(("admin", "super_admin")),
            AdminUser.is_active.is_(True)
        ).count()

        if admin_count <= 1:
            flash("You cannot demote the last active administrator.", "danger")
            return redirect(url_for("admin.staff_management"))

    user.name = name
    user.email = email
    user.role = role

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Unable to update this account.", "danger")
        return redirect(url_for("admin.staff_management"))

    flash("Account updated successfully.", "success")
    return redirect(url_for("admin.staff_management"))


@admin.route("/staff/<int:user_id>/password", methods=["POST"])
@account_admin_required
def reset_staff_password(user_id):
    user = AdminUser.query.get_or_404(user_id)

    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if len(password) < 8 or password != confirm_password:
        flash("Passwords must match and contain at least 8 characters.", "danger")
        return redirect(url_for("admin.staff_management"))

    user.set_password(password)
    db.session.commit()

    flash("Account password reset successfully.", "success")
    return redirect(url_for("admin.staff_management"))


@admin.route("/staff/<int:user_id>/status", methods=["POST"])
@account_admin_required
def toggle_staff_status(user_id):
    current_admin = get_logged_in_admin()
    user = AdminUser.query.get_or_404(user_id)

    if user.id == current_admin.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin.staff_management"))

    if user.is_active and user.role in ("admin", "super_admin"):
        active_admins = AdminUser.query.filter(
            AdminUser.role.in_(("admin", "super_admin")),
            AdminUser.is_active.is_(True)
        ).count()

        if active_admins <= 1:
            flash("You cannot deactivate the last active administrator.", "danger")
            return redirect(url_for("admin.staff_management"))

    user.is_active = not user.is_active
    db.session.commit()

    flash(
        "Account activated." if user.is_active else "Account deactivated.",
        "success"
    )
    return redirect(url_for("admin.staff_management"))


@admin.route("/staff/<int:user_id>/delete", methods=["POST"])
@account_admin_required
def delete_staff(user_id):
    current_admin = get_logged_in_admin()
    user = AdminUser.query.get_or_404(user_id)

    if user.id == current_admin.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.staff_management"))

    if user.role in ("admin", "super_admin"):
        active_admins = AdminUser.query.filter(
            AdminUser.role.in_(("admin", "super_admin")),
            AdminUser.is_active.is_(True)
        ).count()

        if active_admins <= 1:
            flash("You cannot delete the last active administrator.", "danger")
            return redirect(url_for("admin.staff_management"))

    db.session.delete(user)
    db.session.commit()

    flash("Account deleted successfully.", "success")
    return redirect(url_for("admin.staff_management"))


@admin.route(
    "/cars/<int:car_id>/insurance-document",
    methods=["GET"]
)
def download_insurance_document(car_id):
    car = Car.query.get_or_404(car_id)

    if not car.insurance_document:
        abort(404)

    upload_folder = os.path.join(
        current_app.instance_path,
        "insurance_documents"
    )

    return send_from_directory(
        upload_folder,
        car.insurance_document,
        as_attachment=True
    )


@admin.route('/register', methods=['GET', 'POST'])
def register_admin():
    # Public registration is permanently disabled.
    abort(404)

@admin.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password required', 'danger')
            return redirect(url_for('admin.admin_login'))

        user = AdminUser.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid credentials', 'danger')
            return redirect(url_for('admin.admin_login'))

        if not user.is_active:
            flash("This account has been deactivated. Contact an administrator.", "danger")
            return redirect(url_for("admin.admin_login"))

        selected_role = request.form.get("role", "").strip().lower()

        if user.role.strip().lower() != selected_role:
            flash("The selected role does not match this account.", "danger")
            return redirect(url_for("admin.admin_login"))

        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={'role': user.role}
        )

        response = redirect(url_for('admin.dashboard'))
        set_access_cookies(response, access_token)
        return response

    return render_template('admin_login.html')


# @admin.route('/logout')
# def admin_logout():
#     response = redirect(url_for('admin.admin_login'))
#     unset_jwt_cookies(response)
#     return response



# ------------------- AUTH ROUTES -------------------
# @admin.route("/register", methods=["GET", "POST"])
# def register():
#     # Anyone can register in this minimal example. In production, limit registration or seed an initial admin.
#     if request.method == "POST":
#         name = request.form.get("name")
#         email = request.form.get("email")
#         role = request.form.get("role", "staff")
#         password = request.form.get("password")
#         if not (name and email and password):
#             flash("Please fill all required fields.", "danger")
#             return redirect(url_for("admin.register"))

#         if AdminUser.query.filter_by(email=email).first():
#             flash("Email already registered.", "danger")
#             return redirect(url_for("admin.register"))

#         user = AdminUser(name=name, email=email, role=role)
#         user.set_password(password)
#         db.session.add(user)
#         db.session.commit()

#         flash("Account created. You can now login.", "success")
#         return redirect(url_for("admin.login"))

#     return render_template("register.html")


# @admin.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         email = request.form.get("email")
#         password = request.form.get("password")
#         user = AdminUser.query.filter_by(email=email).first()
#         if not user or not user.check_password(password):
#             flash("Invalid credentials", "danger")
#             return redirect(url_for("admin.login"))

#         # store session
#         session["admin_id"] = user.id
#         session["admin_name"] = user.name
#         session["admin_email"] = user.email
#         session["admin_role"] = user.role

#         flash(f"Welcome back, {user.name}", "success")
#         return redirect(url_for("admin.dashboard"))

#     return render_template("login.html")


@admin.route("/logout")
def logout():
    session.clear()

    response = redirect(url_for("admin.admin_login"))
    unset_jwt_cookies(response)

    flash("Logged out successfully.", "success")
    return response

# ------------------- DASHBOARD -------------------
@admin.route("/")
@login_required
def dashboard():
    cache_key = "wheelq:admin:dashboard:stats"

    # Try Redis first
    stats = cache_get(cache_key)

    if stats is None:
        # Cache miss: fetch fresh counts from the database
        stats = {
            "cars": Car.query.count(),
            "pending": Booking.query.filter_by(
                status="pending"
            ).count(),
            "active": Booking.query.filter_by(
                status="approved"
            ).count(),
            "leases_count": Lease.query.count(),
            "pending_leases": Lease.query.filter_by(
                status="pending"
            ).count(),
        }

        # Keep dashboard statistics cached for 30 seconds
        cache_set(cache_key, stats, timeout=30)

    return render_template("dashboard.html", **stats)



@admin.route("/cars")
# @login_required
def cars_page():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip().lower()

    query = Car.query

    # Search by vehicle name, brand, or registration number
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Car.name.ilike(term),
                Car.brand.ilike(term),
                Car.registration_number.ilike(term)
            )
        )

    # Filter by vehicle status
    if status:
        query = query.filter(
            db.func.lower(Car.status) == status
        )

    cars = query.order_by(Car.created_at.desc()).all()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify([
            {
                "id": c.id,
                "name": c.name,
                "brand": c.brand,
                "reg": c.registration_number,
                "price": c.price,
                "status": c.status
            }
            for c in cars
        ])

    return render_template(
        "car.html",
        cars=cars,
        search=search,
        status=status
    )



@admin.route("/cars/add", methods=["GET", "POST"])
# @role_required(("admin", "staff"))
def add_car():
    leases = Lease.query.filter(
        db.func.lower(Lease.status) == "approved"
    ).order_by(Lease.created_at.desc()).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        brand = request.form.get("brand", "").strip()
        registration_number = request.form.get(
            "registration_number", ""
        ).strip().upper()

        price = request.form.get("price", type=int)
        car_type = request.form.get("type", "").strip()
        details = request.form.get("details")

        valid_car_types = (
            "Saloon Car", "SUV", "Classic Saloon",
            "Truck", "7 Seater", "14 Seater"
        )

        if car_type not in valid_car_types:
            flash("Please select one of the supported vehicle categories.", "danger")
            return render_template("add_car.html", leases=leases)

        image_extensions = {"png", "jpg", "jpeg", "gif", "webp"}

        try:
            image = save_public_upload(
                request.files.get("image"),
                image_extensions
            )
            image_front = save_public_upload(
                request.files.get("image_front"),
                image_extensions
            )
            image_rear = save_public_upload(
                request.files.get("image_rear"),
                image_extensions
            )
            image_left = save_public_upload(
                request.files.get("image_left"),
                image_extensions
            )
            image_right = save_public_upload(
                request.files.get("image_right"),
                image_extensions
            )

        except ValueError as error:
            flash(str(error), "danger")
            return redirect(url_for("admin.add_car"))

        insurance_provider = request.form.get("insurance_provider")
        insurance_expiry_str = request.form.get("insurance_expiry")
        insurance_expiry = None
        try:
           insurance_document = save_insurance_document(
              request.files.get("insurance_document")
         )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("add_car.html", leases=leases)
        if insurance_expiry_str:
            try:
                insurance_expiry = datetime.strptime(
                    insurance_expiry_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                flash("Please enter a valid insurance expiry date.", "danger")
                return render_template("add_car.html", leases=leases)

        car = Car(
            name=name,
            brand=brand,
            registration_number=registration_number or None,
            price=price or 0,
            type=car_type,
            details=details,
            image=image,
            image_front=image_front,
            image_rear=image_rear,
            image_left=image_left,
            image_right=image_right,
            insurance_provider=insurance_provider,
            insurance_expiry=insurance_expiry,
            insurance_document=insurance_document
        )

        db.session.add(car)
        db.session.commit()

        invalidate_admin_dashboard()

        cache_delete("wheelq:public:cars")

        flash("Car added successfully.", "success")
        return redirect(url_for("admin.cars_page"))

    return render_template("add_car.html", leases=leases)



@admin.route("/cars/edit/<int:car_id>", methods=["GET", "POST"])
# @role_required(("admin", "staff"))
def edit_car(car_id):
    car = Car.query.get_or_404(car_id)

    if request.method == "POST":
        car.name = request.form.get("name", "").strip()
        car.brand = request.form.get("brand", "").strip()
        car.registration_number = (
            request.form.get("registration_number", "").strip().upper()
            or None
        )
        car.price = request.form.get("price", type=int) or 0
        car_type = request.form.get("type", "").strip()

        valid_car_types = (
            "Saloon Car", "SUV", "Classic Saloon",
            "Truck", "7 Seater", "14 Seater"
        )

        if car_type not in valid_car_types:
            flash("Please select one of the supported vehicle categories.", "danger")
            return redirect(url_for("admin.edit_car", car_id=car.id))

        car.type = car_type
        car.details = request.form.get("details")

        image_extensions = {"png", "jpg", "jpeg", "gif", "webp"}

        try:
            for field_name in (
                "image",
                "image_front",
                "image_rear",
                "image_left",
                "image_right"
            ):
                uploaded_file = request.files.get(field_name)

                if uploaded_file and uploaded_file.filename:
                    setattr(
                        car,
                        field_name,
                        save_public_upload(
                            uploaded_file,
                            image_extensions
                        )
                    )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
            return redirect(url_for("admin.edit_car", car_id=car.id))

        new_insurance_document = None
        old_insurance_document = None
        try:
            uploaded_file = request.files.get("insurance_document")

            if uploaded_file and uploaded_file.filename:
                new_insurance_document = save_insurance_document(
                    uploaded_file
                )
                old_insurance_document = car.insurance_document
                car.insurance_document = new_insurance_document

        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("admin.edit_car", car_id=car.id))


        db.session.commit()
        if new_insurance_document and old_insurance_document:
            delete_insurance_document(old_insurance_document)
        invalidate_admin_dashboard()

          # Invalidate public car listing and this car's details
        cache_delete("wheelq:public:cars")
        cache_delete(f"wheelq:public:car:{car.id}")


        flash("Car updated successfully.", "success")
        return redirect(url_for("admin.cars_page"))

    return render_template("edit_car.html", car=car)



@admin.route("/cars/delete/<int:car_id>", methods=["POST", "GET"])
# @role_required(("admin",))
def delete_car(car_id):
    car = Car.query.get_or_404(car_id)

    # 🔒 Block deletion if bookings exist
    if car.bookings:
        flash("Cannot delete a car with existing bookings.", "danger")
        return redirect(url_for("admin.cars_page"))

    # remove image
    if car.image:
        cars_folder = os.path.join(current_app.root_path, "public", "static", "cars")
        image_path = os.path.join(cars_folder, car.image)
        if os.path.exists(image_path):
            os.remove(image_path)

    car_id = car.id
    insurance_document = car.insurance_document

    db.session.delete(car)
    db.session.commit()

    delete_insurance_document(insurance_document)

    invalidate_admin_dashboard()

    # Invalidate listing and deleted car's details
    cache_delete("wheelq:public:cars")
    cache_delete(f"wheelq:public:car:{car_id}")


    flash("Car deleted.", "success")
    return redirect(url_for("admin.cars_page"))


# ------------------- CLIENTS -------------------


@admin.route("/clients")
@account_required
def clients_page():
    search = request.args.get("search", "").strip()
    query = Client.query

    if search:
        query = query.filter(
            or_(
                Client.name.ilike(f"%{search}%"),
                Client.id_number.ilike(f"%{search}%"),
                Client.email.ilike(f"%{search}%"),
                Client.phone.ilike(f"%{search}%")
            )
        )

    clients = query.order_by(Client.created_at.desc()).all()

    # Fetch all active blacklist records in one query
    active_blacklists = ClientBlacklist.query.filter_by(
        is_active=True
    ).all()

    blacklist_by_client = {
        record.client_id: record
        for record in active_blacklists
    }

    active_statuses = ["pending", "incomplete", "in progress"]
    repeat_booking_statuses = [
        "completed", "cancelled", "canceled", "deleted"
    ]

    clients_data = []

    for c in clients:
        bookings = c.bookings
        total_bookings = len(bookings)

        normalized_statuses = [
            (booking.status or "").strip().lower()
            for booking in bookings
        ]

        has_active_booking = any(
            status in active_statuses
            for status in normalized_statuses
        )

        has_previous_booking = any(
            status in repeat_booking_statuses
            for status in normalized_statuses
        )

        blacklist_record = blacklist_by_client.get(c.id)
        is_blacklisted = blacklist_record is not None

        can_create_booking = (
            (
                total_bookings == 0
                or has_previous_booking
                or any(
                    status == "incomplete"
                    for status in normalized_statuses
                )
            )
            and not is_blacklisted
        )

        if total_bookings == 0:
            booking_status = "No bookings"
        elif has_active_booking:
            booking_status = "Active booking"
        elif has_previous_booking:
            booking_status = "Ready for new booking"
        else:
            booking_status = "Bookings up to date"

        clients_data.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "id_number": c.id_number,
            "total": total_bookings,
            "can_create_booking": can_create_booking,
            "has_incomplete_booking": any(
                status == "incomplete"
                for status in normalized_statuses
            ),
            "booking_status": booking_status,
            "is_blacklisted": is_blacklisted,
            "blacklist_reason": (
                blacklist_record.reason
                if blacklist_record else None
            ),
            "blacklisted_at": (
                blacklist_record.blacklisted_at.isoformat()
                if blacklist_record else None
            )
        })

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(clients_data)

    return render_template(
        "clients.html",
        clients=clients_data,
        search=search,
        status=request.args.get("status", "")
    )


@admin.route('/clients/register', methods=['GET', 'POST'])
@account_required
def register_client():

    if request.method == 'POST':

        data = request.form
        files = request.files
        saved_documents = []

        try:
            # Optional M-Pesa statement
            mpesa_file = files.get("mpesa_statement")
            mpesa_password = data.get("mpesa_password", "")

            if mpesa_file and mpesa_file.filename:

                if not mpesa_password:
                    raise ValueError(
                        "Enter the existing M-Pesa PDF password."
                    )

                pdf_content = mpesa_file.read()

                verify_mpesa_pdf_password(
                    pdf_content,
                    mpesa_password
                )

                mpesa_file.stream.seek(0)

            # Create client
            client = Client(
                name=data['name'],
                phone=data['phone'],
                email=data['email'],
                id_number=data['id_number'],
                drivers_license_number=data.get('drivers_license_number'),
                area_of_residence=data.get('area_of_residence'),
                area_of_usage=data.get('area_of_usage'),

                id_front=save_file('id_front'),
                id_back=save_file('id_back'),
                drivers_license=save_file('drivers_license'),
                passport=save_file('passport'),

                emergency_contact1_name=data.get('emergency_contact1_name'),
                emergency_contact1_phone=data.get('emergency_contact1_phone'),
                emergency_contact1_relationship=data.get('emergency_contact1_relationship'),
                emergency_contact1_area=data.get('emergency_contact1_area'),

                emergency_contact2_name=data.get('emergency_contact2_name'),
                emergency_contact2_phone=data.get('emergency_contact2_phone'),
                emergency_contact2_relationship=data.get('emergency_contact2_relationship'),
                emergency_contact2_area=data.get('emergency_contact2_area'),

                emergency_contact3_name=data.get('emergency_contact3_name'),
                emergency_contact3_phone=data.get('emergency_contact3_phone'),
                emergency_contact3_relationship=data.get('emergency_contact3_relationship'),
                emergency_contact3_area=data.get('emergency_contact3_area')
            )

            db.session.add(client)
            db.session.flush()

            admin_user = get_logged_in_admin()

            if not admin_user:
                raise ValueError("Your login session is invalid.")

            # Save M-Pesa statement
            if mpesa_file and mpesa_file.filename:

                saved = save_client_document(
                    mpesa_file,
                    "mpesa_statement"
                )

                saved_documents.append(saved["file_path"])

                db.session.add(ClientDocument(
                    client_id=client.id,
                    document_type="mpesa_statement",
                    description="M-Pesa statement",
                    file_path=saved["file_path"],
                    original_filename=saved["original_filename"],
                    mime_type=saved["mime_type"],
                    uploaded_by=admin_user.id
                ))

            # Save social media screenshots
            screenshots = files.getlist("social_media_screenshots")
            platform = data.get("social_media_platform", "").strip()
            description = data.get("social_media_description", "").strip()

            valid_platforms = {
                "Facebook", "Instagram", "TikTok",
                "WhatsApp", "X", "Other"
            }

            for screenshot in screenshots:

                if not screenshot or not screenshot.filename:
                    continue

                if platform not in valid_platforms:
                    raise ValueError(
                        "Select a valid social media platform."
                    )

                saved = save_client_document(
                    screenshot,
                    "social_media"
                )

                saved_documents.append(saved["file_path"])

                db.session.add(ClientDocument(
                    client_id=client.id,
                    document_type="social_media",
                    platform=platform,
                    description=description or None,
                    file_path=saved["file_path"],
                    original_filename=saved["original_filename"],
                    mime_type=saved["mime_type"],
                    uploaded_by=admin_user.id
                ))

            db.session.commit()

            flash("Client registered successfully.", "success")

            return redirect(
                url_for('admin.create_booking', client_id=client.id)
            )

        except ValueError as exc:
            db.session.rollback()

            for path in saved_documents:
                if os.path.exists(path):
                    os.remove(path)

            flash(str(exc), "danger")

        except Exception:
            db.session.rollback()

            for path in saved_documents:
                if os.path.exists(path):
                    os.remove(path)

            current_app.logger.exception("Client registration failed")
            flash("Unable to register client. Please try again.", "danger")

    return render_template('register_client.html')


@admin.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        data = request.form
        files = request.files

        client.name = data['name']
        client.phone = data['phone']
        client.email = data['email']
        client.id_number = data['id_number']
        client.drivers_license_number = data.get('drivers_license_number')
        client.area_of_residence = data.get('area_of_residence')
        client.area_of_usage = data.get('area_of_usage')

        # Update public client identification files only when replacements
        # are actually uploaded. Existing filenames remain unchanged otherwise.
        try:
            client.id_front = (
                save_public_upload(files.get("id_front"), ALLOWED_EXTENSIONS)
                or client.id_front
            )
            client.id_back = (
                save_public_upload(files.get("id_back"), ALLOWED_EXTENSIONS)
                or client.id_back
            )
            client.drivers_license = (
                save_public_upload(
                    files.get("drivers_license"),
                    ALLOWED_EXTENSIONS
                )
                or client.drivers_license
            )
            client.passport = (
                save_public_upload(files.get("passport"), ALLOWED_EXTENSIONS)
                or client.passport
            )

        except ValueError as error:
            flash(str(error), "danger")
            return redirect(url_for("admin.clients_page"))

        # Emergency contacts
        for i in range(1, 4):
            setattr(client, f'emergency_contact{i}_name', data.get(f'emergency_contact{i}_name'))
            setattr(client, f'emergency_contact{i}_phone', data.get(f'emergency_contact{i}_phone'))
            setattr(client, f'emergency_contact{i}_relationship', data.get(f'emergency_contact{i}_relationship'))
            setattr(client, f'emergency_contact{i}_area', data.get(f'emergency_contact{i}_area'))

        db.session.commit()
        flash("Client details updated", "success")
        return redirect(url_for('admin.clients_page'))

    return render_template('edit_client.html', client=client)




@admin.route("/clients/<int:client_id>")
@account_required
def client_details(client_id):

    client = Client.query.get_or_404(client_id)

    blacklist = ClientBlacklist.query.filter_by(
        client_id=client.id,
        is_active=True
    ).order_by(
        ClientBlacklist.blacklisted_at.desc()
    ).first()

    blacklist_history = ClientBlacklist.query.filter_by(
        client_id=client.id
    ).order_by(
        ClientBlacklist.blacklisted_at.desc()
    ).all()

    documents = ClientDocument.query.filter_by(
        client_id=client.id
    ).order_by(
        ClientDocument.uploaded_at.desc()
    ).all()

    financial_charges = FinancialCharge.query.filter_by(
        client_id=client.id
    ).order_by(
        FinancialCharge.created_at.desc()
    ).all()

    return render_template(
        "client_details.html",
        client=client,
        blacklist=blacklist,
        blacklist_history=blacklist_history,
        documents=documents,
        financial_charges=financial_charges
    )

   




@admin.route("/clients/delete/<int:client_id>", methods=["POST"])
@account_admin_required
def delete_client(client_id):

    client = Client.query.get_or_404(client_id)

    # Preserve blacklist audit history
    blacklist_history = ClientBlacklist.query.filter_by(
        client_id=client.id
    ).first()

    if blacklist_history:
        flash(
            "This client cannot be deleted because blacklist audit history exists.",
            "danger"
        )
        return redirect(
            url_for("admin.client_details", client_id=client.id)
        )

    # Preserve uploaded document history
    document_history = ClientDocument.query.filter_by(
        client_id=client.id
    ).first()

    if document_history:
        flash(
            "This client cannot be deleted because uploaded document records exist.",
            "danger"
        )
        return redirect(
            url_for("admin.client_details", client_id=client.id)
        )

    try:
        client_name = client.name

        # Preserve bookings but remove their link to this client
        for booking in client.bookings:
            booking.client_id = None

        db.session.delete(client)
        db.session.commit()

        flash(
            f"Client '{client_name}' was deleted successfully.",
            "success"
        )

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Failed to delete client %s",
            client_id
        )

        flash(
            "Unable to delete this client. Please try again.",
            "danger"
        )

    return redirect(url_for("admin.clients_page"))


# ------------------- BOOKINGS -------------------
@admin.route("/bookings")
#@login_required
def bookings_page():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    return render_template("bookings.html", bookings=bookings)




@admin.route("/bookings/<int:booking_id>")
@account_required
def booking_view(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    financial_charges = (
        FinancialCharge.query
        .filter_by(booking_id=booking.id)
        .order_by(FinancialCharge.created_at.desc())
        .all()
    )

    damage_charges = (
        DamageCharge.query
        .filter_by(booking_id=booking.id)
        .order_by(DamageCharge.created_at.desc())
        .all()
    )

    penalties = (
        LatePenalty.query
        .filter_by(booking_id=booking.id)
        .order_by(LatePenalty.created_at.desc())
        .all()
    )

    return render_template(
        "view_booking.html",
        booking=booking,
        financial_charges=financial_charges,
        damage_charges=damage_charges,
        penalties=penalties
    )


@admin.route("/bookings/approve/<int:booking_id>", methods=["POST", "GET"])
# @role_required(("admin", "staff"))
def booking_approve(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    booking.status = "approved"

    # mark car as booked
    if booking.car:
        booking.car.status = "booked"

    # create admin notification
    notification = Notification(
        title="Booking Approved",
        message=f"Booking #{booking.id} approved for {booking.client_name}"
    )

    db.session.add(notification)
    db.session.commit()

    invalidate_admin_dashboard()

    flash("Booking approved successfully.", "success")
    return redirect(url_for("admin.bookings_page"))




@admin.route("/bookings/cancel/<int:booking_id>", methods=["GET", "POST"])
# @role_required(("admin", "staff"))
def booking_cancel(booking_id):
    """
    Cancel booking
    """
    booking = Booking.query.get_or_404(booking_id)
    booking.status = "cancelled"

    car = Car.query.get(booking.car_id)
    if car:
        car.status = "available"

    # Create notification
    notification = Notification(
        message=f"Booking #{booking.id} was cancelled"
    )
    db.session.add(notification)

    db.session.commit()

    flash("Booking cancelled.", "danger")
    return redirect(url_for("admin.bookings_page"))


@admin.route("/bookings/<int:booking_id>/status/<string:status>")
# @login_required
# @role_required(("admin", "staff"))
def update_booking_status(booking_id, status):
    booking = Booking.query.get_or_404(booking_id)

    allowed_statuses = ["pending", "approved", "active", "completed", "cancelled"]
    if status not in allowed_statuses:
        flash("Invalid booking status", "danger")
        return redirect(url_for("admin.bookings_page"))

    booking.status = status

    # 🔄 Sync car status
    if booking.car:
        if status in ["approved", "active"]:
            booking.car.status = "booked"
        else:
            booking.car.status = "available"

    notification = Notification(
        message=f"Booking #{booking.id} marked as {status.capitalize()}"
    )

    db.session.add(notification)
    db.session.commit()

    flash(f"Booking updated to {status.capitalize()}", "success")
    return redirect(url_for("admin.bookings_page"))

@admin.route("/bookings/delete/<int:booking_id>", methods=["POST", "GET"])
# @login_required
# @role_required(("admin",))
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Free car if booking was active
    if booking.car:
        booking.car.status = "available"

    db.session.delete(booking)
    db.session.commit()

    flash("Booking deleted successfully.", "success")
    return redirect(url_for("admin.bookings_page"))

@admin.route("/bookings/edit/<int:booking_id>", methods=["GET", "POST"])
# @login_required
# @role_required(("admin", "staff"))
def edit_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if request.method == "POST":
        booking.client_name = request.form.get("client_name")
        booking.client_email = request.form.get("client_email")
        booking.client_phone = request.form.get("client_phone")
        booking.notes = request.form.get("notes")

        db.session.commit()
        flash("Booking updated successfully.", "success")
        return redirect(url_for("admin.bookings_page"))

    return render_template("edit_booking.html", booking=booking)




@admin.route("/bookings/create/<int:client_id>", methods=["GET", "POST"])
@account_required
def create_booking(client_id):

    client = Client.query.get_or_404(client_id)

    # ==========================================
    # STRICT BLACKLIST ENFORCEMENT
    # ==========================================

    active_blacklist = ClientBlacklist.query.filter_by(
        client_id=client.id,
        is_active=True
    ).first()

    if active_blacklist:
        flash(
            f"Booking blocked. This client is blacklisted: "
            f"{active_blacklist.reason}",
            "danger"
        )

        return redirect(
            url_for("admin.client_details", client_id=client.id)
        )

    # Only available vehicles can be booked.
    cars = Car.query.filter_by(status="available").all()

    # ==========================================
    # PROCESS BOOKING
    # ==========================================

    if request.method == "POST":

        car_id = request.form.get("car_id", type=int)

        pickup_date_string = request.form.get(
            "pickup_date", ""
        ).strip()

        dropoff_date_string = request.form.get(
            "dropoff_date", ""
        ).strip()

        pickup_time_string = request.form.get(
            "pickup_time", ""
        ).strip()

        dropoff_time_string = request.form.get(
            "dropoff_time", ""
        ).strip()

        area_of_usage = request.form.get(
            "area_of_usage", ""
        ).strip()

        notes = request.form.get("notes", "").strip()

        # ==========================================
        # REQUIRED FIELD VALIDATION
        # ==========================================

        if not all([
            car_id,
            pickup_date_string,
            dropoff_date_string,
            pickup_time_string,
            dropoff_time_string,
            area_of_usage
        ]):

            flash(
                "Please fill in all required fields, including the scheduled drop-off time.",
                "danger"
            )

            return redirect(
                url_for("admin.create_booking", client_id=client.id)
            )

        # ==========================================
        # FETCH AND VALIDATE VEHICLE
        # ==========================================

        car = db.session.get(Car, car_id)

        if not car or car.status != "available":

            flash(
                "Selected vehicle is unavailable. Please select another vehicle.",
                "danger"
            )

            return redirect(
                url_for("admin.create_booking", client_id=client.id)
            )

        # ==========================================
        # PARSE DATE AND TIME
        # ==========================================

        try:

            pickup_date = datetime.strptime(
                pickup_date_string,
                "%Y-%m-%d"
            ).date()

            dropoff_date = datetime.strptime(
                dropoff_date_string,
                "%Y-%m-%d"
            ).date()

            pickup_time = datetime.strptime(
                pickup_time_string,
                "%H:%M"
            ).time()

            dropoff_time = datetime.strptime(
                dropoff_time_string,
                "%H:%M"
            ).time()

        except ValueError:

            flash(
                "Invalid pickup or drop-off date/time.",
                "danger"
            )

            return redirect(
                url_for("admin.create_booking", client_id=client.id)
            )

        # ==========================================
        # VALIDATE COMPLETE DATE/TIME RANGE
        # ==========================================

        pickup_datetime = datetime.combine(
            pickup_date,
            pickup_time
        )

        dropoff_datetime = datetime.combine(
            dropoff_date,
            dropoff_time
        )

        if dropoff_datetime <= pickup_datetime:

            flash(
                "Drop-off must be after the pickup date and time.",
                "danger"
            )

            return redirect(
                url_for("admin.create_booking", client_id=client.id)
            )

        # ==========================================
        # CALCULATE RENTAL PRICE
        # ==========================================

        # Retains your existing date-based pricing.
        days = max(
            (dropoff_date - pickup_date).days,
            1
        )

        try:
            amount = Decimal(
                str(car.price)
            ) * Decimal(days)

            amount = amount.quantize(Decimal("0.01"))

        except (InvalidOperation, ValueError, TypeError):

            flash(
                "Unable to calculate the booking price. Check the vehicle price.",
                "danger"
            )

            return redirect(
                url_for("admin.create_booking", client_id=client.id)
            )

        if amount <= 0:

            flash(
                "The booking amount must be greater than zero.",
                "danger"
            )

            return redirect(
                url_for("admin.create_booking", client_id=client.id)
            )

        # ==========================================
        # CREATE BOOKING OBJECT
        # ==========================================

        booking = Booking(
            car_id=car.id,
            client_id=client.id,

            client_name=client.name,
            client_email=client.email,
            client_phone=client.phone,

            pickup_date=pickup_date,
            dropoff_date=dropoff_date,

            pickup_time=pickup_time,
            dropoff_time=dropoff_time,

            area_of_usage=area_of_usage,
            notes=notes,

            amount=amount,

            status="pending",
            payment_status="unpaid"
        )

        notification = Notification(
            message=f"New booking created for {client.name}",
            is_read=False
        )

        # ==========================================
        # SAVE BOOKING + FINANCIAL CHARGE
        # IN ONE DATABASE TRANSACTION
        # ==========================================

        try:

            # Save booking first to generate its ID.
            db.session.add(booking)
            db.session.flush()

            # Create the corresponding financial charge.
            # This uses the helper added to app/admin/routes.py.
            create_financial_charge(
                client_id=client.id,
                booking_id=booking.id,
                category="booking",
                description=(
                    f"Vehicle booking #{booking.id} - "
                    f"{car.registration_number}"
                ),
                amount=amount
            )

            # Mark vehicle as booked.
            car.status = "booked"

            # Save notification.
            db.session.add(notification)

            # Commit all changes together.
            db.session.commit()

            flash(
                f"Booking #{booking.id} created successfully. "
                f"Financial charge: KSh {amount:,.2f}.",
                "success"
            )

            db.session.add(booking)
            db.session.commit()

            try:
                notify_booking_created(booking.id)
            except Exception:
                current_app.logger.exception(
                    "Booking email notification failed"
                )
        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Failed to create booking and financial charge."
            )

            flash(
                "Could not create booking. No financial charge was recorded. Please try again.",
                "danger"
            )

        return redirect(
            url_for("admin.bookings_page")
        )

    # ==========================================
    # DISPLAY BOOKING FORM
    # ==========================================

    return render_template(
        "create_booking.html",
        client=client,
        cars=cars,
        today=date.today()
    )



@admin.route("/notifications")
# @login_required
def notifications_page():
    notifications = Notification.query.order_by(Notification.created_at.desc()).all()

    # ✅ AUTO-MARK AS READ
    Notification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()

    unread_count = 0  # since all are now read

    return render_template(
        "notifications.html",
        notifications=notifications,
        unread_count=unread_count
    )


@admin.before_app_request
def load_notifications_count():
    if hasattr(g, 'notifications_count'):
        return
    g.notifications_count = Notification.query.filter_by(is_read=False).count()
    # db.session.add(notification)
    # db.session.commit()

    # admin/routes.py

    
@admin.route("/notifications/mark-read/<int:notification_id>", methods=["POST"])
# @login_required
def mark_notification_read(notification_id):
    notif = Notification.query.get_or_404(notification_id)
    notif.is_read = True
    db.session.commit()

    flash("Notification marked as read", "success")
    return redirect(url_for("admin.notifications_page"))

@admin.route("/notifications/count")
# @login_required
def notifications_count_api():
    count = Notification.query.filter_by(is_read=False).count()
    return jsonify({"count": count})


@admin.route("/leases")
@jwt_required()
def leases_page():

    leases = Lease.query.order_by(
        Lease.created_at.desc()
    ).all()

    return render_template(
        "leases.html",
        leases=leases
    )

@admin.route("/lease/<int:lease_id>/update/<string:status>")
# @login_required
def update_lease_status(lease_id, status):
    lease = Lease.query.get_or_404(lease_id)
    if status.lower() not in ["approved", "rejected"]:
        flash("Invalid status", "danger")
        return redirect(url_for("admin.leases_page"))

    lease.status = status.lower()
    db.session.commit()

    invalidate_admin_dashboard()

    # Optional: create a notification
    notification = Notification(
        message=f"Lease request from {lease.owner_name} has been {lease.status}"
    )
    db.session.add(notification)
    db.session.commit()

    flash(f"Lease status updated to {lease.status.capitalize()}", "success")
    return redirect(url_for("admin.leases_page"))


@admin.route("/leases/<int:lease_id>")
def lease_view(lease_id):

    lease = Lease.query.get_or_404(lease_id)

    return render_template(
        "leases_details.html",
        lease=lease
    )


@admin.route("/leases/add", methods=["GET", "POST"])
@jwt_required()
def add_lease():

    if request.method == "POST":

        owner_name = request.form.get("owner_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        car_model = request.form.get("car_model", "").strip()
        car_year = request.form.get("car_year", type=int)
        car_plate = request.form.get("car_plate", "").strip()
        notes = request.form.get("notes", "").strip()

        # Validate agreed lease amount
        try:
            agreed_amount = Decimal(
                request.form.get("agreed_amount", "").strip()
            )

            if not agreed_amount.is_finite() or agreed_amount <= 0:
                raise InvalidOperation

            agreed_amount = agreed_amount.quantize(
                Decimal("0.01")
            )

        except (InvalidOperation, ValueError, TypeError):
            flash(
                "Please enter a valid agreed lease amount greater than zero.",
                "danger"
            )
            return redirect(url_for("admin.leases_page"))

        # Validate required fields
        if not all([
            owner_name,
            email,
            phone,
            car_model,
            car_year,
            car_plate
        ]):
            flash(
                "Please complete all required investor and vehicle details.",
                "danger"
            )
            return redirect(url_for("admin.leases_page"))

        image_extensions = {"png", "jpg", "jpeg", "gif", "webp"}

        try:
            image_front = save_public_upload(
                request.files.get("image_front"),
                image_extensions
            )
            image_rear = save_public_upload(
                request.files.get("image_rear"),
                image_extensions
            )
            image_left = save_public_upload(
                request.files.get("image_left"),
                image_extensions
            )
            image_right = save_public_upload(
                request.files.get("image_right"),
                image_extensions
            )

        except ValueError as error:
            flash(str(error), "danger")
            return redirect(url_for("admin.leases_page"))

        lease = Lease(
            owner_name=owner_name,
            email=email,
            phone=phone,
            car_model=car_model,
            car_year=car_year,
            car_plate=car_plate,
            notes=notes,
            agreed_amount=agreed_amount,
            image_front=image_front,
            image_rear=image_rear,
            image_left=image_left,
            image_right=image_right,
            status="pending"
        )

        try:
            db.session.add(lease)
            db.session.commit()

            invalidate_admin_dashboard()

            flash(
                "Investor lease request added successfully.",
                "success"
            )

        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Failed to create investor lease."
            )

            flash(
                "Could not save the investor lease. Please try again.",
                "danger"
            )
            return redirect(url_for("admin.leases_page"))

        try:
            notify_lease_created(lease.id)
        except Exception:
            current_app.logger.exception(
                "Lease email notification failed"
            )

        return redirect(url_for("admin.leases_page"))

    return render_template("add_lease.html")



@admin.route("/leases/edit/<int:lease_id>", methods=["GET", "POST"])
@jwt_required()
def edit_lease(lease_id):
    lease = Lease.query.get_or_404(lease_id)

    if request.method == "POST":
        try:
            new_amount = Decimal(
                request.form.get("agreed_amount", "").strip()
            )

            if not new_amount.is_finite() or new_amount < 0:
                raise InvalidOperation

            new_amount = new_amount.quantize(Decimal("0.01"))

            # Do not reduce the agreed amount below what has already been paid.
            if new_amount < lease.amount_paid:
                flash(
                    "Agreed amount cannot be less than payments already made.",
                    "danger"
                )
                return redirect(url_for("admin.edit_lease", lease_id=lease.id))

            lease.agreed_amount = new_amount

        except (InvalidOperation, ValueError, TypeError):
            flash("Enter a valid agreed lease amount.", "danger")
            return redirect(url_for("admin.edit_lease", lease_id=lease.id))

        lease.owner_name = request.form.get("owner_name", "").strip()
        lease.email = request.form.get("email", "").strip()
        lease.phone = request.form.get("phone", "").strip()
        lease.car_model = request.form.get("car_model", "").strip()
        lease.car_year = request.form.get("car_year", type=int)
        lease.car_plate = request.form.get("car_plate", "").strip()
        lease.status = request.form.get("status", lease.status)
        lease.notes = request.form.get("notes", "").strip()

        image_extensions = {"png", "jpg", "jpeg", "gif", "webp"}

        try:
            for field_name in (
                "image_front",
                "image_rear",
                "image_left",
                "image_right"
            ):
                uploaded_file = request.files.get(field_name)

                if uploaded_file and uploaded_file.filename:
                    setattr(
                        lease,
                        field_name,
                        save_public_upload(
                            uploaded_file,
                            image_extensions
                        )
                    )

        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
            return redirect(
                url_for("admin.edit_lease", lease_id=lease.id)
            )

        try:
            db.session.commit()
            invalidate_admin_dashboard()
            flash("Lease updated successfully.", "success")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to update lease")
            flash("Could not update lease.", "danger")

        return redirect(url_for("admin.leases_page"))

    return render_template("edit_lease.html", lease=lease)



@admin.route(
    "/leases/<int:lease_id>/payments/add",
    methods=["POST"]
)
@jwt_required()
def add_lease_payment(lease_id):
    lease = Lease.query.get_or_404(lease_id)

    if lease.status != "approved":
        flash(
            "Payments can only be recorded for approved leases.",
            "warning"
        )
        return redirect(url_for("admin.lease_view", lease_id=lease.id))

    try:
        amount = Decimal(
            request.form.get("amount", "").strip()
        )

        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation

        amount = amount.quantize(Decimal("0.01"))

        if amount > lease.outstanding_amount:
            flash(
                "Payment exceeds the outstanding lease balance.",
                "danger"
            )
            return redirect(url_for("admin.lease_view", lease_id=lease.id))

    except (InvalidOperation, ValueError, TypeError):
        flash("Enter a valid payment amount.", "danger")
        return redirect(url_for("admin.lease_view", lease_id=lease.id))

    payment = LeasePayment(
        lease_id=lease.id,
        investor_name=lease.owner_name,
        amount=float(amount),
        payment_method=request.form.get("payment_method", "").strip(),
        reference=request.form.get("reference", "").strip(),
        notes=request.form.get("notes", "").strip()
    )

    try:
        db.session.add(payment)
        db.session.commit()
        invalidate_admin_dashboard()

        flash("Investor payment recorded successfully.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to record investor payment")
        flash("Could not record investor payment.", "danger")

        db.session.add(payment)
        db.session.commit()

        try:
            notify_lease_payment_received(payment.id)
        except Exception:
            current_app.logger.exception(
                "Lease payment email notification failed"
            )

    return redirect(url_for("admin.lease_view", lease_id=lease.id))

# ============================================================
# DELETE LEASE
# ============================================================


@admin.route("/leases/delete/<int:lease_id>", methods=["POST"])
@jwt_required()
def delete_lease(lease_id):
    lease = Lease.query.get_or_404(lease_id)

    if lease.payments:
        flash(
            "This lease cannot be deleted because it has payment history. "
            "Preserve the financial records instead.",
            "danger"
        )
        return redirect(url_for("admin.leases_page"))

    try:
        db.session.delete(lease)
        db.session.commit()
        invalidate_admin_dashboard()
        flash("Lease deleted successfully.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to delete lease")
        flash("Failed to delete lease.", "danger")

    return redirect(url_for("admin.leases_page"))

       
@admin.route("/financials")
@account_required
def financials():

    charges = FinancialCharge.query.order_by(
        FinancialCharge.created_at.desc()
    ).all()

    total_charged = sum(
        (Decimal(str(c.amount_charged)) for c in charges),
        Decimal("0.00")
    )

    total_received = sum(
        (c.amount_received for c in charges),
        Decimal("0.00")
    )

    total_cancelled = sum(
        (c.amount_cancelled for c in charges),
        Decimal("0.00")
    )

    total_remaining = sum(
        (c.amount_remaining for c in charges),
        Decimal("0.00")
    )

    category_totals = {}

    for category in ["booking", "penalty", "damage", "other"]:
        selected = [c for c in charges if c.category == category]

        category_totals[category] = {
            "charged": sum(
                (Decimal(str(c.amount_charged)) for c in selected),
                Decimal("0.00")
            ),
            "received": sum(
                (c.amount_received for c in selected),
                Decimal("0.00")
            ),
            "cancelled": sum(
                (c.amount_cancelled for c in selected),
                Decimal("0.00")
            ),
            "remaining": sum(
                (c.amount_remaining for c in selected),
                Decimal("0.00")
            )
        }

    legacy_records = FinancialRecord.query.order_by(
        FinancialRecord.created_at.desc()
    ).all()

        # Approved investor leases are confirmed company liabilities.
    investor_leases = Lease.query.filter(
        Lease.status == "approved"
    ).order_by(Lease.created_at.desc()).all()

    investor_total_owed = sum(
        (Decimal(str(lease.agreed_amount or 0)) for lease in investor_leases),
        Decimal("0.00")
    )

    investor_total_paid = sum(
        (lease.amount_paid for lease in investor_leases),
        Decimal("0.00")
    )

    investor_outstanding = sum(
        (lease.outstanding_amount for lease in investor_leases),
        Decimal("0.00")
    )

    investor_payments = LeasePayment.query.filter(
        LeasePayment.lease_id.isnot(None)
    ).order_by(LeasePayment.created_at.desc()).all()

    return render_template(
        "financials.html",
        charges=charges,
        legacy_records=legacy_records,
        total_charged=total_charged,
        total_received=total_received,
        total_cancelled=total_cancelled,
        total_remaining=total_remaining,
        category_totals=category_totals,
        investor_leases=investor_leases,
        investor_total_owed=investor_total_owed,
        investor_total_paid=investor_total_paid,
        investor_outstanding=investor_outstanding,
        investor_payments=investor_payments
    )




def get_booking_by_id(booking_id):
    return Booking.query.get(booking_id)





@admin.route("/bookings/<int:booking_id>/pay", methods=["POST"])
@account_required
def pay_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    charge = FinancialCharge.query.filter_by(
        booking_id=booking.id,
        category="booking"
    ).first()

    if not charge:
        flash("No financial charge exists for this booking.", "danger")
        return redirect(url_for("admin.bookings_page"))

    return redirect(
        url_for("admin.financials", charge_id=charge.id)
        + f"#charge-{charge.id}"
    )

# @admin.route("/admin/bookings/<int:booking_id>/pay")
# def pay_booking(booking_id):
#     booking = Booking.query.get_or_404(booking_id)

#     # Get Paystack secret key safely
#     secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")
#     if not secret_key:
#         abort(500, "Paystack secret key missing")

#     paystack = Paystack(secret_key=secret_key)

#     callback_url = url_for(
#         "admin.verify_payment",
#         booking_id=booking.id,
#         _external=True
#     )

#     # Paystack expects amount in KOBO
#     amount_kobo = int(booking.amount * 100)
#     email=booking.client_email,


#     if not email or "@" not in email:
#         email = current_app.config.get("DEFAULT_PAYMENT_EMAIL")

#     response = paystack.initialize_payment(
#         email=email,
#         amount=amount_kobo,
#         callback_url=callback_url
#     )

#     # Safety check
#     if not response or "authorization_url" not in response:
#         abort(500, "Failed to initialize Paystack payment")

#     return redirect(response["authorization_url"])


# @admin.route("/admin/payment/verify/<int:booking_id>")
# def verify_payment(booking_id):
#     reference = request.args.get("reference")
#     paystack = Paystack(current_app.config["PAYSTACK_SECRET_KEY"])
#     result = paystack.verify_payment(reference)

#     booking = Booking.query.get_or_404(booking_id)

#     if result["data"]["status"] == "success":
#         # Mark booking as paid
#         booking.payment_status = "paid"
#         db.session.commit()

#         # Add financial record
#         record = FinancialRecord(
#             booking_id=booking.id,
#             amount=booking.amount,
#             payment_method="paystack",
#             status="success",
#             reference=reference
#         )
    
#         record.status = "success"
#         db.session.add(record)

#         # 🔥 THIS IS THE IMPORTANT LINE
#         record.apply_payment()
#         db.session.commit()

#         flash("Payment successful", "success")
#     else:
#         flash("Payment failed", "danger")

#     return redirect(url_for("admin.bookings_page"))


@admin.route("/admin/payment/verify/<int:booking_id>")
def verify_payment(booking_id):
    reference = request.args.get("reference")

    if not reference:
        flash("Missing payment reference", "danger")
        return redirect(url_for("admin.bookings_page"))

    paystack = Paystack(current_app.config["PAYSTACK_SECRET_KEY"])
    result = paystack.verify_payment(reference)

    booking = Booking.query.get_or_404(booking_id)

    if result["data"]["status"] == "success":
        record = FinancialRecord(
            booking_id=booking.id,
            amount=booking.amount,  # ✅ correct field
            payment_method="paystack",
            status="success",
            reference=reference
        )

        db.session.add(record)
        db.session.flush()  # 🔥 ensures record.booking exists

        record.apply_payment()

        flash("Payment verified and recorded successfully", "success")
    else:
        flash("Payment verification failed", "danger")

        db.session.add(record)
        db.session.commit()

        try:
            notify_payment_received(payment.id)
        except Exception:
            current_app.logger.exception(
                "Payment email notification failed"
            )

    return redirect(url_for("admin.bookings_page"))




@admin.route("/admin/bookings/<int:booking_id>/release")
@account_required
def release_car(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.status == "completed":
        flash("This booking has already been completed.", "warning")
        return redirect(url_for("admin.bookings_page"))

    return render_template(
        "release_car.html",
        booking=booking
    )


@admin.route(
    "/admin/bookings/<int:booking_id>/activate",
    methods=["POST"]
)
@account_required
def activate_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.status == "completed":
        flash("This booking has already been completed.", "warning")
        return redirect(url_for("admin.bookings_page"))

    if booking.status == "active":
        flash("This vehicle has already been released.", "info")
        return redirect(url_for("admin.active_bookings"))

    agreement_confirmed = (
        request.form.get("agreement_confirmed") == "yes"
    )

    if not agreement_confirmed:
        flash(
            "Confirm that the hire agreement has been signed.",
            "danger"
        )
        return redirect(
            url_for("admin.release_car", booking_id=booking.id)
        )

    try:
        booking.status = "active"

        if booking.car:
            booking.car.status = "booked"

        db.session.commit()

        flash("Vehicle successfully released to the client.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Vehicle activation failed.")
        flash("Unable to release this vehicle.", "danger")

    return redirect(url_for("admin.active_bookings"))



@admin.route("/admin/bookings/active")
def active_bookings():
    bookings = Booking.query.filter_by(status="active").all()
    return render_template("active_bookings.html", bookings=bookings)


@admin.route("/admin/bookings/<int:booking_id>/deactivate")
def deactivate_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.status = "completed"

    if booking.car:
        booking.car.status = "available"

    db.session.commit()
    flash("Booking deactivated", "info")
    return redirect(url_for("admin.active_bookings"))


@admin.route("/penalty-settings", methods=["GET", "POST"])
@account_admin_required
def penalty_settings():
    setting = get_or_create_penalty_setting()

    if request.method == "POST":
        try:
            rate = Decimal(
                request.form.get("rate", "0")
            ).quantize(Decimal("0.01"))

            interval = int(request.form.get("interval_minutes", "0"))
            grace = int(request.form.get("grace_period_minutes", "0"))

            if rate <= 0:
                raise ValueError("Penalty rate must be greater than zero.")

            if interval <= 0:
                raise ValueError("Penalty interval must be greater than zero.")

            if grace < 0:
                raise ValueError("Grace period cannot be negative.")

            setting.rate = rate
            setting.interval_minutes = interval
            setting.grace_period_minutes = grace
            setting.updated_by = get_current_admin_id()

            db.session.commit()

            flash("Penalty settings updated.", "success")

        except (ValueError, InvalidOperation) as exc:
            db.session.rollback()
            flash(str(exc), "danger")

        except Exception:
            db.session.rollback()
            current_app.logger.exception("Penalty settings update failed.")
            flash("Unable to update penalty settings.", "danger")

    return render_template(
        "penalty_settings.html",
        setting=setting
    )    


@admin.route(
    "/penalties/<int:penalty_id>/discard",
    methods=["POST"]
)
@account_admin_required
def discard_penalty(penalty_id):
    penalty = LatePenalty.query.get_or_404(penalty_id)

    try:
        reason = request.form.get("reason", "").strip()

        if not reason:
            raise ValueError("A discard reason is required.")

        charge = penalty.financial_charge

        if not charge:
            raise ValueError("This penalty has no financial charge.")

        remaining = charge.amount_remaining

        if remaining > 0:
            adjustment = FinancialAdjustment(
                charge_id=charge.id,
                amount=remaining,
                adjustment_type="penalty_discard",
                reason=reason,
                status="approved",
                created_by=get_current_admin_id()
            )
            db.session.add(adjustment)

        penalty.status = "discarded"
        penalty.discarded_at = datetime.utcnow()
        penalty.discard_reason = reason

        db.session.commit()

        flash("Penalty discarded and outstanding amount cancelled.", "success")

    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Penalty discard failed.")
        flash("Unable to discard penalty.", "danger")

    return redirect(url_for("admin.penalties"))



@admin.route(
    "/bookings/<int:booking_id>/return",
    methods=["GET", "POST"]
)
@account_required
def return_vehicle(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.status == "completed":
        flash("This vehicle has already been returned.", "info")
        return redirect(url_for("admin.bookings_page"))

    setting = get_or_create_penalty_setting()

    damage_charges = DamageCharge.query.filter_by(
        booking_id=booking.id
    ).order_by(DamageCharge.created_at.desc()).all()

    existing_penalty = LatePenalty.query.filter_by(
        booking_id=booking.id
    ).first()

    if request.method == "POST":
        try:
            if not booking.dropoff_time:
                raise ValueError(
                    "This booking has no scheduled drop-off time."
                )

            if existing_penalty:
                raise ValueError(
                    "A return penalty has already been processed."
                )

            actual_return_text = request.form.get(
                "actual_return_at", ""
            ).strip()

            if not actual_return_text:
                raise ValueError(
                    "Enter the actual vehicle return date and time."
                )

            actual_return = datetime.fromisoformat(
                actual_return_text
            )

            expected_return = datetime.combine(
                booking.dropoff_date,
                booking.dropoff_time
            )

            if actual_return > datetime.now() + timedelta(minutes=5):
                raise ValueError(
                    "The return date and time cannot be in the future."
                )

            if not booking.client_id:
                raise ValueError(
                    "This booking has no linked client. "
                    "Link the client before processing the return."
                )

            result = calculate_late_penalty(
                expected_return=expected_return,
                actual_return=actual_return,
                rate=setting.rate,
                interval_minutes=setting.interval_minutes,
                grace_period_minutes=setting.grace_period_minutes
            )

            if result["amount"] > 0:
                car_registration = (
                    booking.car.registration_number
                    if booking.car else "Unknown"
                )

                charge = create_financial_charge(
                    client_id=booking.client_id,
                    booking_id=booking.id,
                    category="penalty",
                    description=(
                        f"Late return penalty for {car_registration}"
                    ),
                    amount=result["amount"]
                )

                penalty = LatePenalty(
                    booking_id=booking.id,
                    client_phone=booking.client_phone,
                    registration_number=car_registration,
                    hours_late=ceil(result["minutes_late"] / 60),
                    amount=result["amount"],
                    status="unpaid",
                    expected_return_at=expected_return,
                    actual_return_at=actual_return,
                    minutes_late=result["minutes_late"],
                    chargeable_minutes=result["chargeable_minutes"],
                    rate=setting.rate,
                    interval_minutes=setting.interval_minutes,
                    grace_period_minutes=setting.grace_period_minutes,
                    intervals_charged=result["intervals_charged"],
                    financial_charge_id=charge.id
                )

                db.session.add(penalty)

            booking.status = "completed"

            if booking.car:
                booking.car.status = "available"

            db.session.commit()

            if result["amount"] > 0:
                flash(
                    f"Vehicle returned. Late penalty: "
                    f"KSh {result['amount']:,.2f}. "
                    "The penalty has been added to Financial Management.",
                    "warning"
                )
            else:
                flash("Vehicle returned successfully.", "success")

            return redirect(url_for("admin.bookings_page"))

        except (ValueError, InvalidOperation) as exc:
            db.session.rollback()
            flash(str(exc), "danger")

        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Vehicle return processing failed."
            )
            flash("Unable to process vehicle return.", "danger")

    return render_template(
        "return.html",
        booking=booking,
        setting=setting,
        damage_charges=damage_charges,
        existing_penalty=existing_penalty
    )

@admin.route(
    "/financial-charges/<int:charge_id>/payment",
    methods=["POST"]
)
@account_required
def record_financial_payment(charge_id):
    charge = FinancialCharge.query.get_or_404(charge_id)

    try:
        amount = Decimal(
            request.form.get("amount", "0")
        ).quantize(Decimal("0.01"))

        method = request.form.get("payment_method", "").strip()
        reference = request.form.get("reference", "").strip() or None

        if amount <= 0:
            raise ValueError("Enter a valid payment amount.")

        if not method:
            raise ValueError("Select a payment method.")

        if amount > charge.amount_remaining:
            raise ValueError(
                "Payment cannot exceed the outstanding balance."
            )

        if reference and FinancialPayment.query.filter_by(
            reference=reference
        ).first():
            raise ValueError("This payment reference already exists.")

        
        payment = FinancialPayment(
            charge=charge,
            amount=amount,
            payment_method=method,
            reference=reference,
            status="success",
            recorded_by=get_current_admin_id(),
            notes=request.form.get("notes", "").strip()
        )

        db.session.add(payment)
        db.session.flush()

                # Keep the booking payment status synchronized
        # with actual payments received against its booking charge.
        if charge.category == "booking" and charge.booking:
            received = charge.amount_received
            charged = Decimal(str(charge.amount_charged))

            if received >= charged:
                charge.booking.payment_status = "paid"
            elif received > 0:
                charge.booking.payment_status = "partial"
            else:
                charge.booking.payment_status = "pending"

        if charge.category == "penalty":
            penalty = LatePenalty.query.filter_by(
                financial_charge_id=charge.id
            ).first()

            if penalty and charge.amount_remaining == 0:
                penalty.status = "paid"
                penalty.paid_at = datetime.utcnow()
                penalty.payment_method = method
                penalty.payment_reference = reference

        if charge.category == "damage":
            damage = DamageCharge.query.filter_by(
                financial_charge_id=charge.id
            ).first()

            if damage and charge.amount_remaining == 0:
                damage.status = "paid"
                damage.paid_at = datetime.utcnow()
                damage.payment_method = method
                damage.payment_reference = reference

        db.session.commit()

        flash("Payment recorded successfully.", "success")

    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Payment recording failed.")
        flash("Unable to record payment.", "danger")

    return redirect(url_for("admin.financials"))


@admin.route(
    "/financial-payments/<int:payment_id>/delete",
    methods=["POST"]
)
@account_admin_required
def delete_financial_payment(payment_id):
    payment = FinancialPayment.query.get_or_404(payment_id)
    charge = payment.charge

    try:
        payment_id_value = payment.id
        deleted_amount = Decimal(str(payment.amount))
        charge_id = charge.id

        # Delete only this transaction.
        db.session.delete(payment)
        db.session.flush()

        # Recalculate successful payments still attached to this charge.
        remaining_received = db.session.query(
            db.func.coalesce(db.func.sum(FinancialPayment.amount), 0)
        ).filter(
            FinancialPayment.charge_id == charge_id,
            FinancialPayment.status == "success"
        ).scalar()

        received = Decimal(str(remaining_received))
        charged = Decimal(str(charge.amount_charged))
        fully_paid = received >= charged

        # Synchronize the linked booking.
        if charge.category == "booking" and charge.booking:
            if fully_paid:
                charge.booking.payment_status = "paid"
            elif received > 0:
                charge.booking.payment_status = "partial"
            else:
                charge.booking.payment_status = "pending"

        # Synchronize a linked late penalty.
        if charge.category == "penalty":
            penalty = LatePenalty.query.filter_by(
                financial_charge_id=charge.id
            ).first()

            if penalty:
                penalty.status = "paid" if fully_paid else "unpaid"
                penalty.paid_at = (
                    datetime.utcnow() if fully_paid else None
                )

        # Synchronize a linked damage charge.
        if charge.category == "damage":
            damage = DamageCharge.query.filter_by(
                financial_charge_id=charge.id
            ).first()

            if damage:
                damage.status = "paid" if fully_paid else "unpaid"
                damage.paid_at = (
                    datetime.utcnow() if fully_paid else None
                )

                if not fully_paid:
                    damage.payment_method = None
                    damage.payment_reference = None

        db.session.commit()

        current_app.logger.warning(
            "Financial payment deleted: payment_id=%s charge_id=%s "
            "amount=%s admin_id=%s",
            payment_id_value,
            charge_id,
            deleted_amount,
            get_current_admin_id()
        )

        flash(
            "Payment transaction deleted. Related payment statuses were updated.",
            "success"
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Financial payment deletion failed."
        )
        flash("Unable to delete this payment transaction.", "danger")

    return redirect(
        url_for("admin.financials") + f"#charge-{charge.id}"
    )


@admin.route(
    "/financial-charges/<int:charge_id>/cancel",
    methods=["POST"]
)
@account_admin_required
def cancel_financial_charge(charge_id):
    charge = FinancialCharge.query.get_or_404(charge_id)

    try:
        amount = Decimal(
            request.form.get("amount", "0")
        ).quantize(Decimal("0.01"))

        reason = request.form.get("reason", "").strip()

        if amount <= 0:
            raise ValueError("Enter a valid cancellation amount.")

        if not reason:
            raise ValueError("A cancellation reason is required.")

        if amount > charge.amount_remaining:
            raise ValueError(
                "Cancellation cannot exceed the outstanding balance."
            )

        adjustment = FinancialAdjustment(
            charge_id=charge.id,
            amount=amount,
            adjustment_type="cancellation",
            reason=reason,
            status="approved",
            created_by=get_current_admin_id()
        )

        db.session.add(adjustment)
        db.session.commit()

        flash("Financial adjustment recorded.", "success")

    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Financial adjustment failed.")
        flash("Unable to cancel the charge.", "danger")

    return redirect(url_for("admin.financials"))


@admin.route(
    "/bookings/<int:booking_id>/damages",
    methods=["POST"]
)
@account_required
def add_damage_charge(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    try:
        if not booking.client_id:
            raise ValueError("This booking has no linked client.")

        description = request.form.get("description", "").strip()
        notes = request.form.get("notes", "").strip()

        amount = Decimal(
            request.form.get("amount", "0")
        ).quantize(Decimal("0.01"))

        if not description:
            raise ValueError("Enter a damage description.")

        if amount <= 0:
            raise ValueError("Enter a valid damage amount.")
        

        if booking.status == "completed":
            flash(
                "You cannot add damage charges to a completed booking.",
                "danger"
            )
            return redirect(url_for("admin.bookings_page"))

        charge = create_financial_charge(
            client_id=booking.client_id,
            booking_id=booking.id,
            category="damage",
            description=description,
            amount=amount
        )

        damage = DamageCharge(
            booking_id=booking.id,
            amount=amount,
            description=description,
            notes=notes,
            status="unpaid",
            financial_charge_id=charge.id
        )

        db.session.add(damage)
        db.session.commit()

        flash("Damage charge recorded successfully.", "success")

    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Damage recording failed.")
        flash("Unable to record damage charge.", "danger")

    return redirect(
    url_for("admin.return_vehicle", booking_id=booking.id)
)





@admin.route("/admin/bookings/<int:booking_id>/agreement")
def download_agreement(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Example: serve a PDF or static agreement
    return send_file(
        "static/docs/hire_agreement.pdf",
        as_attachment=True
    )

@admin.route("/financials/receipt/<int:transaction_id>")
# @login_required
def generate_receipt(transaction_id):
    transaction = FinancialRecord.query.get_or_404(transaction_id)

    booking = transaction.booking
    client = booking.client
    car = booking.car

    return render_template(
        "receipt.html",
        transaction=transaction,
        booking=booking,
        client=client,
        car=car
    )


@admin.route("/reports")
@account_admin_required
def reports_dashboard():
    # --------------------------------------------------
    # 1. DATE FILTERS
    # --------------------------------------------------
    today = date.today()
    period = request.args.get("period", "monthly").lower()

    if period not in ("daily", "weekly", "monthly", "annual", "custom"):
        period = "monthly"

    try:
        if period == "daily":
            start_date = end_date = today

        elif period == "weekly":
            start_date = today - timedelta(days=6)
            end_date = today

        elif period == "annual":
            start_date = date(today.year, 1, 1)
            end_date = today

        elif period == "custom":
            start_date = date.fromisoformat(request.args.get("start_date", ""))
            end_date = date.fromisoformat(request.args.get("end_date", ""))

            if start_date > end_date:
                raise ValueError("Start date cannot be after end date.")

        else:
            start_date = today.replace(day=1)
            end_date = today

    except (ValueError, TypeError):
        flash("Invalid reporting dates. Showing this month instead.", "warning")
        period = "monthly"
        start_date = today.replace(day=1)
        end_date = today

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(
        end_date + timedelta(days=1),
        datetime.min.time()
    )

    def in_period(column):
        return (column >= start_dt, column < end_dt)

    def money(value):
        return Decimal(str(value or 0))

    def total_amount(items, field="amount"):
        return sum(
            (money(getattr(item, field)) for item in items),
            Decimal("0.00")
        )

    # --------------------------------------------------
    # 2. BOOKINGS
    # --------------------------------------------------
    bookings = Booking.query.filter(
        *in_period(Booking.created_at)
    ).all()

    booking_statuses = Counter(
        (booking.status or "unknown").strip().lower()
        for booking in bookings
    )

    total_bookings = len(bookings)

    completed_bookings = booking_statuses.get("completed", 0)
    cancelled_bookings = booking_statuses.get("cancelled", 0)
    pending_bookings = booking_statuses.get("pending", 0)

    booking_value = total_amount(bookings, "amount")

    # Booking dates can span periods, so calculate booked days
    # overlapping the selected reporting window.
    period_days = (end_date - start_date).days + 1
    booking_days = 0

    for booking in bookings:
        if booking.pickup_date and booking.dropoff_date:
            overlap_start = max(booking.pickup_date, start_date)
            overlap_end = min(booking.dropoff_date, end_date)

            if overlap_end >= overlap_start:
                booking_days += (overlap_end - overlap_start).days + 1

    # --------------------------------------------------
    # 3. FLEET SNAPSHOT
    # --------------------------------------------------
    cars = Car.query.all()

    fleet_statuses = Counter(
        (car.status or "unknown").strip().lower()
        for car in cars
    )

    total_vehicles = len(cars)
    available_vehicles = fleet_statuses.get("available", 0)

    # --------------------------------------------------
    # 4. CUSTOMERS
    # --------------------------------------------------
    new_customers = Client.query.filter(
        *in_period(Client.created_at)
    ).all()

    total_new_customers = len(new_customers)

    # Returning customers are clients who have at least
    # one booking created in this reporting period.
    returning_customer_ids = {
        booking.client_id
        for booking in bookings
        if booking.client_id is not None
    }

    returning_customers = len(returning_customer_ids)

    active_blacklist = ClientBlacklist.query.filter_by(
        is_active=True
    ).count()

    new_blacklist_records = ClientBlacklist.query.filter(
        *in_period(ClientBlacklist.blacklisted_at)
    ).count()

    # --------------------------------------------------
    # 5. ACTUAL EARNINGS
    # --------------------------------------------------
    successful_payments = FinancialPayment.query.filter(
        FinancialPayment.status == "success",
        *in_period(FinancialPayment.received_at)
    ).all()

    manual_entries = ManualFinancialEntry.query.filter(
        *in_period(ManualFinancialEntry.transaction_date)
    ).all()

    manual_earnings = [
        entry for entry in manual_entries
        if entry.entry_type == "earning"
    ]

    manual_expenses = [
        entry for entry in manual_entries
        if entry.entry_type == "expense"
    ]

    customer_payment_total = total_amount(
        successful_payments
    )

    manual_earning_total = total_amount(manual_earnings)
    manual_expense_total = total_amount(manual_expenses)

    total_earnings = (
        customer_payment_total + manual_earning_total
    )

    # --------------------------------------------------
    # 6. ACTUAL INVESTOR PAYOUTS
    # --------------------------------------------------
    investor_payments = LeasePayment.query.filter(
        LeasePayment.lease_id.isnot(None),
        *in_period(LeasePayment.created_at)
    ).all()

    investor_payout_total = total_amount(investor_payments)

    total_expenses = manual_expense_total + investor_payout_total
    net_profit = total_earnings - total_expenses

    # --------------------------------------------------
    # 7. FINANCIAL CHARGES / OUTSTANDING AMOUNTS
    # --------------------------------------------------
    financial_charges = FinancialCharge.query.filter(
        *in_period(FinancialCharge.created_at)
    ).all()

    charges_raised = sum(
        (money(charge.amount_charged) for charge in financial_charges),
        Decimal("0.00")
    )

    outstanding_charges = sum(
        (charge.amount_remaining for charge in financial_charges),
        Decimal("0.00")
    )

    approved_adjustments = FinancialAdjustment.query.filter(
        FinancialAdjustment.status == "approved",
        *in_period(FinancialAdjustment.created_at)
    ).all()

    total_adjustments = total_amount(
        approved_adjustments
    )

    # --------------------------------------------------
    # 8. PENALTIES
    # --------------------------------------------------
    penalties = LatePenalty.query.filter(
        *in_period(LatePenalty.created_at)
    ).all()

    penalty_total = total_amount(penalties)

    paid_penalties = [
        penalty for penalty in penalties
        if (penalty.status or "").lower() == "paid"
    ]

    unpaid_penalties = [
        penalty for penalty in penalties
        if (penalty.status or "").lower() != "paid"
    ]

    penalty_collected = total_amount(paid_penalties)
    penalty_outstanding = total_amount(unpaid_penalties)

    # --------------------------------------------------
    # 9. DAMAGE CHARGES
    # --------------------------------------------------
    damage_charges = DamageCharge.query.filter(
        *in_period(DamageCharge.created_at)
    ).all()

    damage_total = total_amount(damage_charges)

    # Prefer actual linked FinancialPayment records for
    # collections, so damage collections are not counted twice.
    damage_charge_ids = {
        charge.id for charge in financial_charges
        if charge.category == "damage"
    }

    damage_collected = sum(
        (
            money(payment.amount)
            for payment in successful_payments
            if payment.charge_id in damage_charge_ids
        ),
        Decimal("0.00")
    )

    # --------------------------------------------------
    # 10. AIRPORT TRANSFERS
    # --------------------------------------------------
    airport_transfers = AirportTransfer.query.filter(
        *in_period(AirportTransfer.created_at)
    ).all()

    transfer_statuses = Counter(
        (transfer.status or "unknown").strip().lower()
        for transfer in airport_transfers
    )

    # --------------------------------------------------
    # 11. INVESTOR / LEASE ACTIVITY
    # --------------------------------------------------
    leases = Lease.query.filter(
        *in_period(Lease.created_at)
    ).all()

    lease_statuses = Counter(
        (lease.status or "unknown").strip().lower()
        for lease in leases
    )

    approved_leases = [
        lease for lease in leases
        if (lease.status or "").lower() == "approved"
    ]

    lease_agreed_total = sum(
        (money(lease.agreed_amount) for lease in approved_leases),
        Decimal("0.00")
    )

    # This is a liability indicator, not a cash expense.
    # It must not be added to total_expenses.
    lease_outstanding_total = sum(
        (lease.outstanding_amount for lease in approved_leases),
        Decimal("0.00")
    )

    # --------------------------------------------------
    # 12. CONTACT ENQUIRIES
    # --------------------------------------------------
    enquiries = ContactMessage.query.filter(
        *in_period(ContactMessage.created_at)
    ).all()

    unread_enquiries = sum(
        1 for message in enquiries if not message.is_read
    )

    replied_enquiries = sum(
        1 for message in enquiries if message.admin_reply
    )

    # --------------------------------------------------
    # 13. CHART DATA
    # --------------------------------------------------
    daily_chart = period_days <= 31

    chart_labels = []
    earnings_map = defaultdict(float)
    expenses_map = defaultdict(float)

    if daily_chart:
        cursor = start_date

        while cursor <= end_date:
            key = cursor.isoformat()
            chart_labels.append(cursor.strftime("%d %b"))
            earnings_map[key] = 0
            expenses_map[key] = 0
            cursor += timedelta(days=1)

        def bucket_key(value):
            return value.date().isoformat()

    else:
        cursor = start_date.replace(day=1)

        while cursor <= end_date:
            key = cursor.strftime("%Y-%m")
            chart_labels.append(cursor.strftime("%b %Y"))
            earnings_map[key] = 0
            expenses_map[key] = 0

            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)

        def bucket_key(value):
            return value.strftime("%Y-%m")

    for payment in successful_payments:
        if payment.received_at:
            earnings_map[bucket_key(payment.received_at)] += float(
                payment.amount or 0
            )

    for entry in manual_earnings:
        earnings_map[bucket_key(entry.transaction_date)] += float(
            entry.amount or 0
        )

    for payment in investor_payments:
        if payment.created_at:
            expenses_map[bucket_key(payment.created_at)] += float(
                payment.amount or 0
            )

    for entry in manual_expenses:
        expenses_map[bucket_key(entry.transaction_date)] += float(
            entry.amount or 0
        )

    earnings_series = list(earnings_map.values())
    expenses_series = list(expenses_map.values())

    # --------------------------------------------------
    # 14. BREAKDOWNS
    # --------------------------------------------------
    payment_methods = defaultdict(Decimal)

    for payment in successful_payments:
        method = payment.payment_method or "Unknown"
        payment_methods[method] += money(payment.amount)

    for entry in manual_earnings:
        method = entry.payment_method or "Unknown"
        payment_methods[method] += money(entry.amount)

    booking_categories = Counter(
        (booking.status or "unknown").strip().title()
        for booking in bookings
    )

    # --------------------------------------------------
    # 15. RECENT ACTIVITY TABLES
    # --------------------------------------------------
    recent_bookings = sorted(
        bookings,
        key=lambda item: item.created_at or datetime.min,
        reverse=True
    )[:10]

    recent_payments = sorted(
        successful_payments,
        key=lambda item: item.received_at or datetime.min,
        reverse=True
    )[:10]

    recent_expenses = sorted(
        investor_payments,
        key=lambda item: item.created_at or datetime.min,
        reverse=True
    )[:10]

    return render_template(
        "reports/dashboard.html",

        period=period,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),

        total_bookings=total_bookings,
        completed_bookings=completed_bookings,
        cancelled_bookings=cancelled_bookings,
        pending_bookings=pending_bookings,
        booking_value=booking_value,
        booking_statuses=dict(booking_statuses),
        booking_days=booking_days,

        total_vehicles=total_vehicles,
        available_vehicles=available_vehicles,
        fleet_statuses=dict(fleet_statuses),

        total_new_customers=total_new_customers,
        returning_customers=returning_customers,
        active_blacklist=active_blacklist,
        new_blacklist_records=new_blacklist_records,

        total_earnings=total_earnings,
        total_expenses=total_expenses,
        net_profit=net_profit,
        customer_payment_total=customer_payment_total,
        manual_earning_total=manual_earning_total,
        manual_expense_total=manual_expense_total,
        investor_payout_total=investor_payout_total,

        charges_raised=charges_raised,
        outstanding_charges=outstanding_charges,
        total_adjustments=total_adjustments,

        penalty_total=penalty_total,
        penalty_collected=penalty_collected,
        penalty_outstanding=penalty_outstanding,

        damage_total=damage_total,
        damage_collected=damage_collected,

        airport_transfer_count=len(airport_transfers),
        transfer_statuses=dict(transfer_statuses),

        lease_count=len(leases),
        lease_statuses=dict(lease_statuses),
        lease_agreed_total=lease_agreed_total,
        lease_outstanding_total=lease_outstanding_total,

        enquiry_count=len(enquiries),
        unread_enquiries=unread_enquiries,
        replied_enquiries=replied_enquiries,

        labels=chart_labels,
        earnings_series=earnings_series,
        expenses_series=expenses_series,

        payment_methods=dict(payment_methods),
        recent_bookings=recent_bookings,
        recent_payments=recent_payments,
        recent_expenses=recent_expenses
    )




# =========================================================
# EARNINGS & EXPENSES
# =========================================================

def _financial_report_dates():
    """Resolve the selected reporting period into inclusive dates."""
    period = request.args.get("period", "monthly").lower()
    today = datetime.utcnow().date()

    if period == "daily":
        start_date = end_date = today

    elif period == "weekly":
        start_date = today - timedelta(days=6)
        end_date = today

    elif period == "monthly":
        start_date = today.replace(day=1)
        end_date = today

    elif period == "annual":
        start_date = today.replace(month=1, day=1)
        end_date = today

    elif period == "custom":
        try:
            start_date = datetime.strptime(
                request.args.get("start_date", ""), "%Y-%m-%d"
            ).date()
            end_date = datetime.strptime(
                request.args.get("end_date", ""), "%Y-%m-%d"
            ).date()

            if start_date > end_date:
                raise ValueError("Start date cannot be after end date.")

        except ValueError:
            flash("Please select a valid custom date range.", "danger")
            period = "monthly"
            start_date = today.replace(day=1)
            end_date = today

    else:
        period = "monthly"
        start_date = today.replace(day=1)
        end_date = today

    return period, start_date, end_date


def _financial_report_bucket(transaction_date, daily_buckets):
    """Return the date key used to group a transaction."""
    if daily_buckets:
        return transaction_date.date().isoformat()

    return transaction_date.strftime("%Y-%m")


@admin.route("/reports/earnings-expenses")
@account_admin_required
def earnings_expenses():
    period, start_date, end_date = _financial_report_dates()

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_exclusive = datetime.combine(
        end_date + timedelta(days=1),
        datetime.min.time()
    )

    # Use daily chart buckets for short ranges and monthly buckets
    # for longer ranges.
    daily_buckets = (end_date - start_date).days <= 31

    if daily_buckets:
        bucket_dates = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]
        labels = [d.strftime("%d %b") for d in bucket_dates]
        bucket_keys = [d.isoformat() for d in bucket_dates]
    else:
        bucket_dates = []
        cursor = start_date.replace(day=1)

        while cursor <= end_date:
            bucket_dates.append(cursor)
            if cursor.month == 12:
                cursor = cursor.replace(
                    year=cursor.year + 1, month=1
                )
            else:
                cursor = cursor.replace(month=cursor.month + 1)

        labels = [d.strftime("%b %Y") for d in bucket_dates]
        bucket_keys = [d.strftime("%Y-%m") for d in bucket_dates]

    earnings_map = defaultdict(float)
    expenses_map = defaultdict(float)
    records = []

    # -----------------------------------------------------
    # 1. Customer payments actually received
    # -----------------------------------------------------
    customer_payments = FinancialPayment.query.filter(
        FinancialPayment.status == "success",
        FinancialPayment.received_at >= start_dt,
        FinancialPayment.received_at < end_exclusive
    ).order_by(FinancialPayment.received_at.desc()).all()

    for payment in customer_payments:
        transaction_date = payment.received_at

        if not transaction_date:
            continue

        amount = float(payment.amount or 0)
        key = _financial_report_bucket(
            transaction_date, daily_buckets
        )

        earnings_map[key] += amount

        charge = payment.charge
        records.append({
            "date": transaction_date,
            "type": "earning",
            "category": charge.category if charge else "customer payment",
            "description": (
                charge.description if charge
                else "Customer payment"
            ),
            "amount": amount,
            "payment_method": payment.payment_method,
            "reference": payment.reference,
            "source": "Customer payment",
            "editable": False
        })

    # -----------------------------------------------------
    # 2. Actual investor payouts linked to leases
    # -----------------------------------------------------
    investor_payments = LeasePayment.query.filter(
        LeasePayment.lease_id.isnot(None),
        LeasePayment.created_at >= start_dt,
        LeasePayment.created_at < end_exclusive
    ).order_by(LeasePayment.created_at.desc()).all()

    for payment in investor_payments:
        transaction_date = payment.created_at

        if not transaction_date:
            continue

        amount = float(payment.amount or 0)
        key = _financial_report_bucket(
            transaction_date, daily_buckets
        )

        expenses_map[key] += amount

        records.append({
            "date": transaction_date,
            "type": "expense",
            "category": "investor payout",
            "description": (
                payment.notes or
                f"Investor payout - {payment.investor_name or 'Investor'}"
            ),
            "amount": amount,
            "payment_method": payment.payment_method,
            "reference": payment.reference,
            "source": "Investor payout",
            "editable": False
        })

    # -----------------------------------------------------
    # 3. Manually recorded earnings and expenses
    # -----------------------------------------------------
    manual_entries = ManualFinancialEntry.query.filter(
        ManualFinancialEntry.transaction_date >= start_dt,
        ManualFinancialEntry.transaction_date < end_exclusive
    ).order_by(
        ManualFinancialEntry.transaction_date.desc()
    ).all()

    for entry in manual_entries:
        transaction_date = entry.transaction_date
        amount = float(entry.amount or 0)

        key = _financial_report_bucket(
            transaction_date, daily_buckets
        )

        if entry.entry_type == "earning":
            earnings_map[key] += amount
        else:
            expenses_map[key] += amount

        records.append({
            "date": transaction_date,
            "type": entry.entry_type,
            "category": entry.category,
            "description": entry.description,
            "amount": amount,
            "payment_method": entry.payment_method,
            "reference": entry.reference,
            "source": "Manual entry",
            "editable": True,
            "id": entry.id
        })

    earnings_series = [
        round(earnings_map[key], 2) for key in bucket_keys
    ]

    expenses_series = [
        round(expenses_map[key], 2) for key in bucket_keys
    ]

    total_earnings = round(sum(earnings_series), 2)
    total_expenses = round(sum(expenses_series), 2)
    net_profit = round(total_earnings - total_expenses, 2)

    records.sort(key=lambda item: item["date"], reverse=True)

    return render_template(
        "reports/earnings_expenses.html",
        period=period,
        start_date=start_date,
        end_date=end_date,
        labels=bucket_keys,
        earnings_series=earnings_series,
        expenses_series=expenses_series,
        total_earnings=total_earnings,
        total_expenses=total_expenses,
        net_profit=net_profit,
        records=records
    )


# =========================================================
# ADD MANUAL FINANCIAL ENTRY
# =========================================================

@admin.route("/reports/earnings-expenses/add", methods=["GET", "POST"])
@account_admin_required
def add_manual_financial_entry():
    if request.method == "POST":
        try:
            entry_type = request.form.get("entry_type", "").strip().lower()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            amount = Decimal(request.form.get("amount", "0"))
            transaction_date = datetime.strptime(
                request.form.get("transaction_date", ""),
                "%Y-%m-%d"
            )
            payment_method = request.form.get("payment_method", "").strip() or None
            reference = request.form.get("reference", "").strip() or None

            if entry_type not in ("earning", "expense"):
                raise ValueError("Select a valid transaction type.")

            if not category or not description:
                raise ValueError("Category and description are required.")

            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")

            if reference and ManualFinancialEntry.query.filter_by(
                reference=reference
            ).first():
                raise ValueError("That reference number already exists.")

            entry = ManualFinancialEntry(
                entry_type=entry_type,
                category=category,
                description=description,
                amount=amount,
                transaction_date=transaction_date,
                payment_method=payment_method,
                reference=reference,
                created_by=get_logged_in_admin().id
            )

            db.session.add(entry)
            db.session.commit()

            flash("Transaction added successfully.", "success")
            return redirect(url_for("admin.earnings_expenses"))

        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(str(error), "danger")

        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to add financial transaction.")
            flash("An error occurred while saving the transaction.", "danger")

    return render_template(
        "reports/transaction_form.html",
        page_title="Add Transaction",
        form_mode="add",
        entry=None,
        today_date=date.today().isoformat()
    )


@admin.route(
    "/reports/earnings-expenses/edit/<int:entry_id>",
    methods=["GET", "POST"]
)
@account_admin_required
def edit_manual_financial_entry(entry_id):
    entry = ManualFinancialEntry.query.get_or_404(entry_id)

    if request.method == "POST":
        try:
            entry_type = request.form.get("entry_type", "").strip().lower()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            amount = Decimal(request.form.get("amount", "0"))
            transaction_date = datetime.strptime(
                request.form.get("transaction_date", ""),
                "%Y-%m-%d"
            )
            payment_method = request.form.get("payment_method", "").strip() or None
            reference = request.form.get("reference", "").strip() or None

            if entry_type not in ("earning", "expense"):
                raise ValueError("Select a valid transaction type.")

            if not category or not description:
                raise ValueError("Category and description are required.")

            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")

            if reference:
                duplicate = ManualFinancialEntry.query.filter(
                    ManualFinancialEntry.reference == reference,
                    ManualFinancialEntry.id != entry.id
                ).first()

                if duplicate:
                    raise ValueError("That reference number already exists.")

            entry.entry_type = entry_type
            entry.category = category
            entry.description = description
            entry.amount = amount
            entry.transaction_date = transaction_date
            entry.payment_method = payment_method
            entry.reference = reference

            db.session.commit()

            flash("Transaction updated successfully.", "success")
            return redirect(url_for("admin.earnings_expenses"))

        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(str(error), "danger")

        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to update financial transaction.")
            flash("An error occurred while updating the transaction.", "danger")

    return render_template(
        "reports/transaction_form.html",
        page_title="Edit Transaction",
        form_mode="edit",
        entry=entry
    )
# =========================================================
# DELETE MANUAL FINANCIAL ENTRY
# =========================================================

@admin.route(
    "/reports/earnings-expenses/delete/<int:entry_id>",
    methods=["POST"]
)
@account_admin_required
def delete_manual_financial_entry(entry_id):
    entry = ManualFinancialEntry.query.get_or_404(entry_id)

    try:
        db.session.delete(entry)
        db.session.commit()

        flash("Manual financial transaction deleted.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Manual financial entry deletion failed."
        )
        flash("Unable to delete this transaction.", "danger")

    return redirect(url_for("admin.earnings_expenses"))



@admin.route('/penalties')
@account_required
def penalties():
    penalties = (
        LatePenalty.query
        .order_by(LatePenalty.created_at.desc())
        .all()
    )

    setting = (
        PenaltySetting.query
        .filter_by(is_active=True)
        .order_by(PenaltySetting.updated_at.desc())
        .first()
    )

    # Provide default settings if none have been configured.
    if setting is None:
        setting = PenaltySetting(
            rate=500,
            interval_minutes=30,
            grace_period_minutes=0,
            is_active=True
        )

    return render_template(
        'penalties.html',
        penalties=penalties,
        setting=setting
    )



# Mark penalty as paid (POST)
@admin.route('/penalties/<int:penalty_id>/pay', methods=['POST'])
def pay_penalty(penalty_id):
    mark_penalty_paid(penalty_id)
    flash('Penalty marked as paid', 'success')
    return redirect(url_for('admin.penalties'))


@admin.route("/messages")
# @jwt_required()
def admin_messages():
    messages = ContactMessage.query.order_by(
        ContactMessage.created_at.desc()
    ).all()
    return render_template("messages.html", messages=messages)



@admin.route("/messages/<int:message_id>/reply", methods=["POST"])
@account_admin_required
def admin_message_reply(message_id):
    message = ContactMessage.query.get_or_404(message_id)

    reply_text = request.form.get("reply", "").strip()

    if not reply_text:
        flash("Please enter a reply before sending.", "danger")
        return redirect(url_for(
            "admin.admin_message_detail",
            message_id=message.id
        ))

    try:
        email_message = Message(
            subject=f"Re: Your enquiry to WheelQ Tours & Car Hire",
            recipients=[message.email],
            body=reply_text,
            sender=current_app.config.get("MAIL_DEFAULT_SENDER")
        )

        mail.send(email_message)

        # Save the reply after the email has been sent successfully.
        message.admin_reply = reply_text
        message.is_read = True

        db.session.commit()

        flash(f"Your reply has been sent to {message.email}.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to send reply to contact message %s",
            message.id
        )
        flash(
            "The reply could not be sent. Check your email configuration and try again.",
            "danger"
        )

    return redirect(url_for(
        "admin.admin_message_detail",
        message_id=message.id
    ))


@admin.route("/admin/messages/<int:message_id>")
@account_required
def admin_message_detail(message_id):
    message = ContactMessage.query.get_or_404(message_id)

    if not message.is_read:
        message.is_read = True
        db.session.commit()

    return render_template(
        "message_detail.html",
        message=message
    )  


    
from app.models import EmailOutbox
from app.services.email_service import retry_failed_email


@admin.route("/email-logs")
@account_admin_required
def email_logs():
    emails = EmailOutbox.query.order_by(
        EmailOutbox.created_at.desc()
    ).limit(200).all()

    return render_template(
        "admin/email_logs.html",
        emails=emails
    )


@admin.route("/email-logs/<int:email_id>/retry", methods=["POST"])
@account_admin_required
def retry_email_log(email_id):
    email = db.session.get(EmailOutbox, email_id)

    if not email:
        abort(404)

    if email.status == "sent":
        flash("This email has already been sent.", "info")
    else:
        success = retry_failed_email(email.id)

        if success:
            flash("Email sent successfully.", "success")
        else:
            flash("Email delivery failed. Check the error log.", "danger")

    return redirect(url_for("admin.email_logs"))
  

@admin.route("/test-sms", methods=["POST"])
def test_sms():
    phone = "+254708920528"  # YOUR NUMBER
    message = "✅ SMS TEST: Onfon Media integration is working."

    result = send_sms(phone, message)
    return {"status": "sent", "provider_response": result}


    
# =========================================================
# AIRPORT TRANSFERS
# =========================================================

@admin.route("/airport-transfers")
@jwt_required()
def airport_transfers():
    transfers = AirportTransfer.query.order_by(
        AirportTransfer.created_at.desc()
    ).all()

    cars = Car.query.filter_by(
        status="available"
    ).order_by(Car.name.asc()).all()

    return render_template(
        "airport_transfers.html",
        transfers=transfers,
        cars=cars
    )


def airport_transfer_form_data():
    return {
        "transfers": AirportTransfer.query.order_by(
            AirportTransfer.created_at.desc()
        ).all(),
        "cars": Car.query.order_by(Car.name.asc()).all()
    }


@admin.route("/airport-transfers/add", methods=["POST"])
@jwt_required()
def add_airport_transfer():
    name = request.form.get("name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    airport = request.form.get("airport", "").strip()

    pickup_location = request.form.get("pickup_location", "").strip()
    dropoff_location = request.form.get("dropoff_location", "").strip()
    pickup_datetime_string = request.form.get(
        "pickup_datetime", ""
    ).strip()

    passengers = request.form.get("passengers", type=int)
    notes = request.form.get("notes", "").strip()
    car_id = request.form.get("car_id", type=int)
    raw_price = request.form.get("price", "").strip()

    redirect_url = url_for("admin.airport_transfers")

    if not all([
        name, phone_number, email, airport,
        pickup_location, dropoff_location,
        pickup_datetime_string, raw_price
    ]):
        flash("Please complete all required fields, including the price.", "danger")
        return redirect(redirect_url)

    if not passengers or not 1 <= passengers <= 100:
        flash("Enter a valid passenger count between 1 and 100.", "danger")
        return redirect(redirect_url)

    try:
        pickup_datetime = datetime.fromisoformat(
            pickup_datetime_string
        )
        amount = parse_transfer_price(raw_price)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(redirect_url)

    car = None

    if car_id:
        car = db.session.get(Car, car_id)

        if not car:
            flash("The selected vehicle could not be found.", "danger")
            return redirect(redirect_url)

        if car.status != "available":
            flash("The selected vehicle is not available.", "warning")
            return redirect(redirect_url)

    try:
        transfer = AirportTransfer(
            name=name,
            phone_number=phone_number,
            email=email,
            airport=airport,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            pickup_datetime=pickup_datetime,
            passengers=passengers,
            notes=notes or None,
            car_id=car.id if car else None,
            status="pending"
        )

        db.session.add(transfer)
        db.session.flush()

        save_airport_transfer_charge(transfer, amount)

        if car:
            sync_car_status(car)

        db.session.commit()

        flash(
            "Airport transfer created and financial charge recorded successfully.",
            "success"
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to create airport transfer"
        )
        flash(
            "Could not save the airport transfer. Please check the details and try again.",
            "danger"
        )

        db.session.add(transfer)
        db.session.commit()

        try:
            notify_airport_transfer_created(transfer.id)
        except Exception:
            current_app.logger.exception(
                "Airport transfer email notification failed"
            )   

    return redirect(redirect_url)


@admin.route(
    "/airport-transfers/<int:transfer_id>/edit",
    methods=["GET", "POST"]
)
@jwt_required()
def edit_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    cars = Car.query.filter_by(
        status="available"
    ).order_by(Car.name.asc()).all()

    if transfer.car and transfer.car not in cars:
        cars.append(transfer.car)

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            pickup_location = request.form.get(
                "pickup_location", ""
            ).strip()
            dropoff_location = request.form.get(
                "dropoff_location", ""
            ).strip()
            airport = request.form.get("airport", "").strip()
            notes = request.form.get("notes", "").strip()

            passengers = request.form.get("passengers", type=int)
            pickup_datetime_string = request.form.get(
                "pickup_datetime", ""
            ).strip()
            raw_price = request.form.get("price", "").strip()
            car_id = request.form.get("car_id", type=int)

            if not all([
                name, email, phone_number,
                pickup_location, dropoff_location,
                airport, pickup_datetime_string, raw_price
            ]):
                raise ValueError("Please complete all required fields.")

            if not passengers or not 1 <= passengers <= 100:
                raise ValueError(
                    "Enter a valid passenger count between 1 and 100."
                )

            pickup_datetime = datetime.fromisoformat(
                pickup_datetime_string
            )
            amount = parse_transfer_price(raw_price)

            old_car = transfer.car
            new_car = None

            if car_id:
                new_car = db.session.get(Car, car_id)

                if not new_car:
                    raise ValueError("Selected vehicle was not found.")

                if (
                    new_car.id != transfer.car_id
                    and new_car.status != "available"
                ):
                    raise ValueError(
                        "The selected vehicle is not available."
                    )

            transfer.name = name
            transfer.email = email
            transfer.phone_number = phone_number
            transfer.pickup_location = pickup_location
            transfer.dropoff_location = dropoff_location
            transfer.airport = airport
            transfer.notes = notes or None
            transfer.passengers = passengers
            transfer.pickup_datetime = pickup_datetime
            transfer.car_id = new_car.id if new_car else None

            save_airport_transfer_charge(transfer, amount)

            db.session.flush()

            if old_car:
                sync_car_status(old_car)

            if new_car and (
                not old_car or new_car.id != old_car.id
            ):
                sync_car_status(new_car)

            db.session.commit()

            flash(
                "Airport transfer and financial charge updated successfully.",
                "success"
            )

            return redirect(url_for("admin.airport_transfers"))

        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Failed to update airport transfer"
            )
            flash("Could not update the airport transfer.", "danger")

        # Reload the transfer after rollback.
        transfer = AirportTransfer.query.get_or_404(transfer_id)

        cars = Car.query.filter_by(
            status="available"
        ).order_by(Car.name.asc()).all()

        if transfer.car and transfer.car not in cars:
            cars.append(transfer.car)

    return render_template(
        "edit_airport_transfer.html",
        transfer=transfer,
        cars=cars
    )


@admin.route(
    "/airport-transfers/<int:transfer_id>/approve",
    methods=["POST"]
)
@jwt_required()
def approve_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    if transfer.status in ["cancelled", "rejected", "completed"]:
        flash("This transfer cannot be approved in its current status.", "warning")
    else:
        transfer.status = "confirmed"

        if transfer.car:
            sync_car_status(transfer.car)

        db.session.commit()
        flash("Airport transfer approved and confirmed.", "success")

    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/reject",
    methods=["POST"]
)
@jwt_required()
def reject_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)
    car = transfer.car

    transfer.status = "rejected"

    if car:
        sync_car_status(car)

    db.session.commit()

    flash("Airport transfer rejected.", "success")
    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/cancel",
    methods=["POST"]
)
@jwt_required()
def cancel_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    if transfer.status == "completed":
        flash("A completed transfer cannot be cancelled.", "warning")
    else:
        car = transfer.car
        transfer.status = "cancelled"

        if car:
            sync_car_status(car)

        db.session.commit()
        flash("Airport transfer cancelled.", "success")

    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/delete",
    methods=["POST"]
)
@jwt_required()
def delete_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)
    car = transfer.car

    try:
        # Preserve the financial charge and its payment history.
        # The database FK uses ON DELETE SET NULL.
        db.session.delete(transfer)
        db.session.flush()

        if car:
            sync_car_status(car)

        db.session.commit()
        flash(
            "Airport transfer deleted. Its financial record has been preserved.",
            "success"
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to delete airport transfer"
        )
        flash("Could not delete the airport transfer.", "danger")

    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/assign-car",
    methods=["POST"]
)
@jwt_required()
def assign_airport_transfer_car(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    car_id = request.form.get("car_id", type=int)

    if not car_id:
        flash("Please select a vehicle.", "danger")
        return redirect(url_for("admin.airport_transfers"))

    car = db.session.get(Car, car_id)

    if not car:
        flash("Selected vehicle was not found.", "danger")
        return redirect(url_for("admin.airport_transfers"))

    if car.id != transfer.car_id and car.status != "available":
        flash("That vehicle is not currently available.", "warning")
        return redirect(url_for("admin.airport_transfers"))

    old_car = transfer.car

    try:
        transfer.car_id = car.id
        db.session.flush()

        if old_car and old_car.id != car.id:
            sync_car_status(old_car)

        sync_car_status(car)

        db.session.commit()

        flash(
            f"{car.name} has been assigned and marked as booked.",
            "success"
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to assign vehicle to airport transfer"
        )
        flash("Could not assign the selected vehicle.", "danger")

    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/remove-car",
    methods=["POST"]
)
@jwt_required()
def remove_airport_transfer_car(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)
    car = transfer.car

    try:
        transfer.car_id = None
        db.session.flush()

        if car:
            sync_car_status(car)

        db.session.commit()

        flash("Vehicle assignment removed.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to remove airport-transfer vehicle"
        )
        flash("Could not remove the vehicle assignment.", "danger")

    return redirect(url_for("admin.airport_transfers"))
# =========================================================
# CLIENT BLACKLIST MANAGEMENT
# =========================================================

@admin.route("/clients/blacklist")
@account_required
def client_blacklist_page():
    records = (
        ClientBlacklist.query
        .order_by(
            ClientBlacklist.is_active.desc(),
            ClientBlacklist.blacklisted_at.desc()
        )
        .all()
    )

    return render_template(
        "client_blacklist.html",
        records=records
    )


# ---------------------------------------------------------
# BLACKLIST CLIENT - ADMIN ONLY
# ---------------------------------------------------------

@admin.route(
    "/clients/<int:client_id>/blacklist",
    methods=["POST"]
)
@account_admin_required
def blacklist_client(client_id):
    client = Client.query.get_or_404(client_id)

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("A reason is required to blacklist a client.", "danger")
        return redirect(
            request.referrer or url_for("admin.clients_page")
        )

    existing = ClientBlacklist.query.filter_by(
        client_id=client.id,
        is_active=True
    ).first()

    if existing:
        flash("This client is already blacklisted.", "warning")
        return redirect(
            request.referrer or url_for("admin.clients_page")
        )

    admin_user = get_logged_in_admin()

    if not admin_user:
        flash("Your account session is invalid. Please log in again.", "danger")
        return redirect(url_for("admin.login"))

    record = ClientBlacklist(
        client_id=client.id,
        reason=reason,
        blacklisted_by=admin_user.id,
        blacklisted_at=datetime.utcnow(),
        is_active=True
    )

    try:
        db.session.add(record)
        db.session.commit()

        flash(
            f"{client.name} has been blacklisted successfully.",
            "success"
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to blacklist client")
        flash("Could not blacklist client. Please try again.", "danger")

    return redirect(
        request.referrer or url_for("admin.clients_page")
    )


# ---------------------------------------------------------
# UNBLACKLIST CLIENT - ADMIN ONLY
# ---------------------------------------------------------

@admin.route(
    "/clients/<int:client_id>/unblacklist",
    methods=["POST"]
)
@account_admin_required
def unblacklist_client(client_id):
    client = Client.query.get_or_404(client_id)

    removal_reason = request.form.get(
        "removal_reason", ""
    ).strip()

    if not removal_reason:
        flash(
            "A reason is required to remove a client from the blacklist.",
            "danger"
        )
        return redirect(
            request.referrer or url_for("admin.client_blacklist_page")
        )

    record = ClientBlacklist.query.filter_by(
        client_id=client.id,
        is_active=True
    ).order_by(
        ClientBlacklist.blacklisted_at.desc()
    ).first()

    if not record:
        flash("This client is not currently blacklisted.", "warning")
        return redirect(
            request.referrer or url_for("admin.client_blacklist_page")
        )

    admin_user = get_logged_in_admin()

    if not admin_user:
        flash("Your account session is invalid. Please log in again.", "danger")
        return redirect(url_for("admin.login"))

    record.is_active = False
    record.removed_by = admin_user.id
    record.removed_at = datetime.utcnow()
    record.removal_reason = removal_reason

    try:
        db.session.commit()

        flash(
            f"{client.name} has been removed from the blacklist.",
            "success"
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to unblacklist client")
        flash("Could not remove client from blacklist.", "danger")

    return redirect(
        request.referrer or url_for("admin.client_blacklist_page")
    )
