# app/models.py
from datetime import datetime
from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash


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

    bookings = db.relationship("Booking", back_populates="car")


# ===================== ADMIN =====================
class AdminUser(db.Model):
    __tablename__ = "admin_user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
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
   


# ===================== BOOKING =====================
class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)

    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"),nullable=False)

    client_name = db.Column(db.String(150), nullable=False)
    client_email = db.Column(db.String(120), nullable=False)
    client_phone = db.Column(db.String(50), nullable=False)

    pickup_date = db.Column(db.Date, nullable=False)
    dropoff_date = db.Column(db.Date, nullable=False)

    notes = db.Column(db.Text)

    status = db.Column(db.String(50), default="pending")
    payment_status = db.Column(db.String(50), default="unpaid")

    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    penalty_amount = db.Column(db.Float, default=0)
    is_overdue = db.Column(db.Boolean, default=False)

    car = db.relationship("Car", back_populates="bookings")
    client = db.relationship("Client", back_populates="bookings")
    financial_records = db.relationship( "FinancialRecord",back_populates="booking",cascade="all, delete-orphan",passive_deletes=True)
    # financial_records = db.relationship(
    #     "FinancialRecord",
    #     back_populates="booking",
    #     cascade="all, delete-orphan"
    # )


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
    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    image_front = db.Column(db.String(255))
    image_rear = db.Column(db.String(255))
    image_left = db.Column(db.String(255))
    image_right = db.Column(db.String(255))



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




class LeasePayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    investor_name = db.Column(db.String(100))
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"))
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    car = db.relationship("Car")

class DamageCharge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"))
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship("Booking")


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