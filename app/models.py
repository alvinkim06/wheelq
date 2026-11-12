# app/models.py
from datetime import datetime
from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal
from sqlalchemy import CheckConstraint


# ===================== CAR =====================
class Car(db.Model):
    __tablename__ = "car"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    brand = db.Column(db.String(100))
    price = db.Column(db.Integer, nullable=False, default=0)
    type = db.Column(db.String(50))
    details = db.Column(db.Text)
    image = db.Column(db.String(255))
    registration_number = db.Column(db.String(50))
    year = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(30), default="available")
    # NEW images
    image_front = db.Column(db.String(255))
    image_rear = db.Column(db.String(255))
    image_left = db.Column(db.String(255))
    image_right = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
     # --- New insurance fields ---
    insurance_provider = db.Column(db.String(150))
    insurance_expiry = db.Column(db.Date)
    insurance_notified = db.Column(db.Boolean, default=False)
    insurance_document = db.Column(db.String(255), nullable=True)
    bookings = db.relationship("Booking", back_populates="car")


# ===================== ADMIN =====================
class AdminUser(db.Model):
    __tablename__ = "admin_user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# ===================== CLIENT =====================
class Client(db.Model):
    __tablename__ = "client"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    drivers_license_number = db.Column(db.String(50), nullable=True)
    area_of_residence = db.Column(db.String(150), nullable=True)
    area_of_usage = db.Column(db.String(150), nullable=True)
    id_number = db.Column(db.String(50), nullable=True)
    id_front = db.Column(db.String(200), nullable=True)
    id_back = db.Column(db.String(200), nullable=True)
    passport = db.Column(db.String(200), nullable=True)
    drivers_license = db.Column(db.String(200), nullable=True)
    # Emergency Contacts
    emergency_contact1_name = db.Column(db.String(150))
    emergency_contact1_phone = db.Column(db.String(20))
    emergency_contact1_relationship = db.Column(db.String(50))
    emergency_contact1_area = db.Column(db.String(150))

    emergency_contact2_name = db.Column(db.String(150))
    emergency_contact2_phone = db.Column(db.String(20))
    emergency_contact2_relationship = db.Column(db.String(50))
    emergency_contact2_area = db.Column(db.String(150))

    emergency_contact3_name = db.Column(db.String(150))
    emergency_contact3_phone = db.Column(db.String(20))
    emergency_contact3_relationship = db.Column(db.String(50))
    emergency_contact3_area = db.Column(db.String(150))
    
    bookings = db.relationship("Booking", back_populates="client")
    blacklist_records = db.relationship("ClientBlacklist", back_populates="client", lazy=True, passive_deletes=True)
    documents = db.relationship( "ClientDocument", back_populates="client", lazy=True, passive_deletes=True)


# ===================== BOOKING =====================
class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)

    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False)
#    client_id = db.Column(db.Integer, db.ForeignKey("client.id"),nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id", ondelete="SET NULL"), nullable=True)
    client_name = db.Column(db.String(150), nullable=False)
    client_email = db.Column(db.String(120), nullable=False)
    client_phone = db.Column(db.String(50), nullable=False)

    pickup_date = db.Column(db.Date, nullable=False)
    dropoff_date = db.Column(db.Date, nullable=False)
    pickup_time = db.Column(db.Time, nullable=True)
    dropoff_time = db.Column(db.Time, nullable=True)
    notes = db.Column(db.Text)
    area_of_usage = db.Column(db.String(150), nullable=True)
    status = db.Column(db.String(50), default="pending")
    payment_status = db.Column(db.String(50), default="unpaid")

    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    penalty_amount = db.Column(db.Float, default=0)
    is_overdue = db.Column(db.Boolean, default=False)

    car = db.relationship("Car", back_populates="bookings")
    client = db.relationship("Client", back_populates="bookings")
    financial_records = db.relationship( "FinancialRecord",back_populates="booking",cascade="all, delete-orphan",passive_deletes=True)
    financial_charges = db.relationship(
    "FinancialCharge",
    back_populates="booking",
    foreign_keys="FinancialCharge.booking_id"
    )


# ===================== LEASE =====================
class Lease(db.Model):
    __tablename__ = "lease"

    id = db.Column(db.Integer, primary_key=True)
    owner_name = db.Column(db.String(150))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    car_model = db.Column(db.String(100))
    car_year = db.Column(db.Integer)
    car_plate = db.Column(db.String(50))
    notes = db.Column(db.Text)

    # Total amount WheelQ has agreed to pay this investor
    agreed_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    image_front = db.Column(db.String(255))
    image_rear = db.Column(db.String(255))
    image_left = db.Column(db.String(255))
    image_right = db.Column(db.String(255))

    payments = db.relationship(
        "LeasePayment",
        back_populates="lease"
    )

    @property
    def amount_paid(self):
        return sum(
            (Decimal(str(payment.amount)) for payment in self.payments),
            Decimal("0.00")
        )

    @property
    def outstanding_amount(self):
        return max(
            Decimal("0.00"),
            Decimal(str(self.agreed_amount or 0)) - self.amount_paid
        )

    @property
    def payment_status(self):
        if self.amount_paid <= 0:
            return "unpaid"
        if self.outstanding_amount > 0:
            return "partial"
        return "paid"


class LeasePayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # New link to the investor lease. Nullable to preserve old records.
    lease_id = db.Column(
        db.Integer,
        db.ForeignKey("lease.id"),
        nullable=True,
        index=True
    )

    investor_name = db.Column(db.String(100))
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"))
    amount = db.Column(db.Float, nullable=False)

    payment_method = db.Column(db.String(50))
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    car = db.relationship("Car")

    lease = db.relationship(
        "Lease",
        back_populates="payments"
    )        

# ===================== NOTIFICATION =====================
class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    message = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===================== FINANCIAL RECORD =====================

class FinancialRecord(db.Model):
    __tablename__ = "financial_records"

    id = db.Column(db.Integer, primary_key=True)
   
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id', ondelete='CASCADE', name='fk_financial_booking'),nullable=False)


    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), default="paystack")
    reference = db.Column(db.String(100), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="pending")

    booking = db.relationship("Booking", back_populates="financial_records")

    def apply_payment(self):
        if not self.booking:
            raise ValueError("Payment record has no associated booking")

        total_paid = sum(
            p.amount for p in self.booking.financial_records
            if p.status == "success"
        )

        if total_paid >= self.booking.amount:
            self.booking.payment_status = "paid"

        elif total_paid > 0:
            self.booking.payment_status = "partial"
        else:
            self.booking.payment_status = "pending"
       
    

        db.session.commit()


class FinancialCharge(db.Model):
    __tablename__ = "financial_charges"

    id = db.Column(db.Integer, primary_key=True)

    client_id = db.Column(
        db.Integer,
        db.ForeignKey("client.id", ondelete="RESTRICT"),
        nullable=True,
        index=True
    )

    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("booking.id", ondelete="RESTRICT"),
        nullable=True,
        index=True
    )

    category = db.Column(db.String(30), nullable=False, index=True)
    # booking | penalty | damage | other

    description = db.Column(db.String(255), nullable=False)

    amount_charged = db.Column(db.Numeric(12, 2), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=True
    )

    status = db.Column(db.String(30), default="active", nullable=False)

    payments = db.relationship(
        "FinancialPayment",
        back_populates="charge",
        cascade="all, delete-orphan"
    )

    adjustments = db.relationship(
        "FinancialAdjustment",
        back_populates="charge",
        cascade="all, delete-orphan"
    )

    booking = db.relationship(
    "Booking",
    back_populates="financial_charges",
    foreign_keys=[booking_id]
    )
    client = db.relationship("Client")

    created_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[created_by]
    )

    airport_transfer_id = db.Column(
        db.Integer,
        db.ForeignKey("airport_transfers.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True
    )

    airport_transfer = db.relationship(
        "AirportTransfer",
        back_populates="financial_charge",
        foreign_keys=[airport_transfer_id]
    )

    @property
    def amount_received(self):
        return sum(
            (Decimal(str(p.amount)) for p in self.payments
             if p.status == "success"),
            Decimal("0.00")
        )

    @property
    def amount_cancelled(self):
        return sum(
            (Decimal(str(a.amount)) for a in self.adjustments
             if a.status == "approved"),
            Decimal("0.00")
        )

    @property
    def amount_remaining(self):
        remaining = (
            Decimal(str(self.amount_charged))
            - self.amount_received
            - self.amount_cancelled
        )
        return max(remaining, Decimal("0.00"))

    @property
    def payment_status(self):
        received = self.amount_received
        cancelled = self.amount_cancelled
        charged = Decimal(str(self.amount_charged))

        if cancelled >= charged:
            return "cancelled"

        if received + cancelled >= charged:
            return "paid"

        if received > 0 or cancelled > 0:
            return "partially_paid"

        return "unpaid"     


class FinancialPayment(db.Model):
    __tablename__ = "financial_payments"

    id = db.Column(db.Integer, primary_key=True)

    charge_id = db.Column(
        db.Integer,
        db.ForeignKey("financial_charges.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    payment_method = db.Column(db.String(50), nullable=False)

    reference = db.Column(db.String(100), unique=True, nullable=True)

    status = db.Column(
        db.String(20),
        default="success",
        nullable=False
    )

    received_at = db.Column(db.DateTime, default=datetime.utcnow)

    recorded_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=True
    )

    notes = db.Column(db.Text)

    charge = db.relationship("FinancialCharge", back_populates="payments")

    recorded_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[recorded_by]
    )       


class FinancialAdjustment(db.Model):
    __tablename__ = "financial_adjustments"

    id = db.Column(db.Integer, primary_key=True)

    charge_id = db.Column(
        db.Integer,
        db.ForeignKey("financial_charges.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    adjustment_type = db.Column(
        db.String(30),
        nullable=False,
        default="cancellation"
    )

    reason = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), default="approved", nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=True
    )

    charge = db.relationship(
        "FinancialCharge",
        back_populates="adjustments"
    )

    created_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[created_by]
    )



class ManualFinancialEntry(db.Model):
    __tablename__ = "manual_financial_entries"

    __table_args__ = (
        db.CheckConstraint(
            "entry_type IN ('earning', 'expense')",
            name="check_manual_entry_type"
        ),
        db.CheckConstraint(
            "amount > 0",
            name="check_manual_entry_amount"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    entry_type = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    category = db.Column(
        db.String(50),
        nullable=False,
        index=True
    )

    description = db.Column(
        db.String(255),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    transaction_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    payment_method = db.Column(
        db.String(50),
        nullable=True
    )

    reference = db.Column(
        db.String(100),
        nullable=True
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    created_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[created_by]
    )

    def __repr__(self):
        return (
            f"<ManualFinancialEntry "
            f"{self.entry_type}: {self.amount}>"
        )



class DamageCharge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"))
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    booking = db.relationship("Booking")
    financial_charge_id = db.Column(
    db.Integer,
    db.ForeignKey("financial_charges.id", ondelete="RESTRICT"),
    nullable=True,
    unique=True
    )

    description = db.Column(db.String(255), nullable=True)

    payment_method = db.Column(db.String(50), nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="unpaid"
    )

    financial_charge = db.relationship("FinancialCharge")



class LatePenalty(db.Model):
    __tablename__ = "late_penalties"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("booking.id"),
        nullable=False
    )

    client_phone = db.Column(db.String(20), nullable=False)
    registration_number = db.Column(db.String(50), nullable=False)

    hours_late = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)

    status = db.Column(
        db.String(20),
        default="unpaid"  # unpaid | paid
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)

    booking = db.relationship("Booking", backref="late_penalties")

    financial_charge_id = db.Column(
    db.Integer,
    db.ForeignKey("financial_charges.id", ondelete="RESTRICT"),
    nullable=True,
    unique=True
    )

    expected_return_at = db.Column(db.DateTime, nullable=True)
    actual_return_at = db.Column(db.DateTime, nullable=True)

    minutes_late = db.Column(db.Integer, nullable=False, default=0)
    chargeable_minutes = db.Column(db.Integer, nullable=False, default=0)

    rate = db.Column(db.Numeric(12, 2), nullable=True)
    interval_minutes = db.Column(db.Integer, nullable=True)
    grace_period_minutes = db.Column(db.Integer, nullable=False, default=0)
    intervals_charged = db.Column(db.Integer, nullable=False, default=0)

    discarded_at = db.Column(db.DateTime, nullable=True)
    discard_reason = db.Column(db.Text, nullable=True)

    financial_charge = db.relationship("FinancialCharge")


class PenaltySetting(db.Model):
    __tablename__ = "penalty_settings"

    id = db.Column(db.Integer, primary_key=True)

    rate = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=500
    )

    interval_minutes = db.Column(
        db.Integer,
        nullable=False,
        default=30
    )

    grace_period_minutes = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=True
    )

    updated_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[updated_by]
    )

    
class ContactMessage(db.Model):
    __tablename__ = "contact_messages"
   
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(120),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    admin_reply = db.Column(
        db.Text,
        nullable=True
    )

    is_read = db.Column(
        db.Boolean,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    def __repr__(self):
        return f"<ContactMessage {self.email}"

        

   

class AirportTransfer(db.Model):
    __tablename__ = "airport_transfers"

    id = db.Column(db.Integer, primary_key=True)

    # Client information
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(50), nullable=False)

    # Journey information
    pickup_location = db.Column(db.String(255), nullable=False)
    dropoff_location = db.Column(db.String(255), nullable=False)
    pickup_datetime = db.Column(db.DateTime, nullable=False)
    passengers = db.Column(db.Integer, nullable=False)

    # Airport
    airport = db.Column(db.String(150))

    # Assigned vehicle
    car_id = db.Column(
        db.Integer,
        db.ForeignKey("car.id"),
        nullable=True
    )

    car = db.relationship(
        "Car",
        backref="airport_transfers"
    )

    # Additional information
    notes = db.Column(db.Text)

    # Booking status
    status = db.Column(
        db.String(50),
        default="pending",
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    financial_charge = db.relationship(
        "FinancialCharge",
        back_populates="airport_transfer",
        uselist=False
    )

# ===================== CLIENT BLACKLIST =====================

class ClientBlacklist(db.Model):
    __tablename__ = "client_blacklist"

    id = db.Column(db.Integer, primary_key=True)

    client_id = db.Column(
        db.Integer,
        db.ForeignKey("client.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    reason = db.Column(db.Text, nullable=False)

    blacklisted_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=False
    )

    blacklisted_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
        index=True
    )

    removed_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=True
    )

    removed_at = db.Column(db.DateTime, nullable=True)
    removal_reason = db.Column(db.Text, nullable=True)
    client = db.relationship(
        "Client",
        back_populates="blacklist_records"
    )

    blacklisted_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[blacklisted_by]
    )

    removed_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[removed_by]
    )    


# ===================== CLIENT DOCUMENTS =====================

class ClientDocument(db.Model):

    __tablename__ = "client_documents"

    id = db.Column(db.Integer, primary_key=True)

    client_id = db.Column(
        db.Integer,
        db.ForeignKey("client.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # mpesa_statement or social_media
    document_type = db.Column(
        db.String(30),
        nullable=False,
        index=True
    )

    # Facebook, Instagram, TikTok, WhatsApp, X, Other
    platform = db.Column(db.String(50), nullable=True)

    description = db.Column(db.Text, nullable=True)

    # Secure server-side storage path
    file_path = db.Column(db.String(500), nullable=False)

    original_filename = db.Column(db.String(255), nullable=False)

    mime_type = db.Column(db.String(100), nullable=True)

    uploaded_by = db.Column(
        db.Integer,
        db.ForeignKey("admin_user.id"),
        nullable=True
    )

    uploaded_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    client = db.relationship(
        "Client",
        back_populates="documents"
    )

    uploaded_by_user = db.relationship(
        "AdminUser",
        foreign_keys=[uploaded_by]
    )


class EmailOutbox(db.Model):
    __tablename__ = "email_outbox"

    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(180), unique=True, nullable=False, index=True)

    event_type = db.Column(db.String(60), nullable=False, index=True)
    related_model = db.Column(db.String(60))
    related_id = db.Column(db.Integer)

    recipients = db.Column(db.JSON, nullable=False)
    subject = db.Column(db.String(255), nullable=False)

    html_body = db.Column(db.Text)
    text_body = db.Column(db.Text)

    attachment_name = db.Column(db.String(255))
    attachment_data = db.Column(db.LargeBinary)
    attachment_mimetype = db.Column(
        db.String(100),
        default="application/pdf"
    )

    status = db.Column(
        db.String(20),
        default="pending",
        nullable=False,
        index=True
    )

    attempts = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    sent_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"<EmailOutbox {self.id} {self.event_type} {self.status}>"
