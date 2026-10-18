# app/admin/routes.py
import os
from functools import wraps
from flask_jwt_extended import (create_access_token,set_access_cookies,unset_jwt_cookies, verify_jwt_in_request, get_jwt, jwt_required)
from flask import (
    render_template, request, redirect, url_for, flash, session, current_app, jsonify, abort, send_file,abort 
)

from werkzeug.utils import secure_filename
from app.admin import admin
from app import db, mail
from app.models import Car, Booking, Client, AdminUser, Notification, Lease, FinancialRecord, LeasePayment, DamageCharge, LatePenalty, ContactMessage, AirportTransfer
from flask import g
from datetime import datetime,date, timedelta
from app.utils.paystack import Paystack
from app.utils.sms import send_sms
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy import or_





# mpesa_client = MpesaDaraja(
   
#             consumer_key="u7QYXEYKb3zh3sMwmCNIAAiHd7OFd7tmEjmxsL8PWlzmAluS",
#             consumer_secret="qc3j8xBsEAXQF2BAJCoiE8FAuTf0lNOqoTWR4y4aGFtmzqvfmpSvnoCpwqJMs00A",
#             shortcode="600001",
#             passkey="bfb279f9aa9bdbcf158e97dd33f9d54e",
#             callback_url="https://claude-saprophagous-dalia.ngrok-free.dev/mpesa/callback",
#             environment="sandbox"
# )



# --- CONFIG ---
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

PUBLIC_CARS_FOLDER = os.path.join(current_app.root_path, "..", "public", "static", "cars") if False else None
# We'll compute proper path inside functions because current_app isn't available at import time.


def save_file(field_name):
    file = request.files.get(field_name)

    if not file or file.filename == '':
        return None

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    file_path = os.path.join(upload_folder, filename)

    file.save(file_path)
    return filename

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


@admin.route('/register', methods=['GET', 'POST'])
def register_admin():

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        role = request.form.get('role', 'admin')
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('admin.register_admin'))

        if AdminUser.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('admin.register_admin'))
        role = request.form.get("role", "staff").strip().lower()

        if role not in ("admin", "staff"):
            flash("Invalid account role.", "danger")
            return redirect(url_for("admin.register_admin"))

        admin_user = AdminUser(
            name=name,
            email=email,
            role=role
        )
        admin_user.set_password(password)

        db.session.add(admin_user)
        db.session.commit()

        flash('Admin account created successfully. Please log in.', 'success')
        return redirect(url_for('admin.admin_login'))

    return render_template('register.html')



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

        selected_role = request.form.get("role", "").strip().lower()

        if user.role != selected_role:
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
    flash("Logged out successfully.", "success")
    return redirect(url_for("admin.admin_login"))


# ------------------- DASHBOARD -------------------
@admin.route("/")
@login_required
def dashboard():
    cars = Car.query.count()
    pending = Booking.query.filter_by(status="pending").count()
    active = Booking.query.filter_by(status="approved").count()
    leases_count = Lease.query.count()
    pending_leases = Lease.query.filter_by(status="pending").count()

    return render_template(
        "dashboard.html",
        cars=cars,
        pending=pending,
        active=active,
        leases_count=leases_count,
        pending_leases=pending_leases
    )
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
        car_type = request.form.get("type")
        details = request.form.get("details")

        # Use the same upload directory throughout the app.
        upload_folder = os.path.join(
            current_app.static_folder, "uploads"
        )
        os.makedirs(upload_folder, exist_ok=True)

        def save_image(file):
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash("Image file type not allowed.", "danger")
                    return None

                filename = secure_filename(file.filename)
                file.save(os.path.join(upload_folder, filename))
                return filename

            return None

        image = save_image(request.files.get("image"))
        image_front = save_image(request.files.get("image_front"))
        image_rear = save_image(request.files.get("image_rear"))
        image_left = save_image(request.files.get("image_left"))
        image_right = save_image(request.files.get("image_right"))

        insurance_provider = request.form.get("insurance_provider")
        insurance_expiry_str = request.form.get("insurance_expiry")
        insurance_expiry = None

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
            insurance_expiry=insurance_expiry
        )

        db.session.add(car)
        db.session.commit()

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
        car.type = request.form.get("type")
        car.details = request.form.get("details")

        image = request.files.get("image")

        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Image file type not allowed.", "danger")
                return redirect(
                    url_for("admin.edit_car", car_id=car.id)
                )

            filename = secure_filename(image.filename)
            upload_folder = os.path.join(
                current_app.static_folder, "uploads"
            )
            os.makedirs(upload_folder, exist_ok=True)

            image.save(os.path.join(upload_folder, filename))
            car.image = filename

        db.session.commit()

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

    db.session.delete(car)
    db.session.commit()

    flash("Car deleted.", "success")
    return redirect(url_for("admin.cars_page"))


# ------------------- CLIENTS -------------------

# @admin.route("/clients")
# @login_required
# def clients_page():
    """
    Show all clients with number of bookings
    Supports search by name, email, phone, or ID number
    """

    search = request.args.get("search", "").strip()

    query = Client.query

    if search:
        query = query.filter(
            or_(
                Client.name.ilike(f"%{search}%"),
                Client.email.ilike(f"%{search}%"),
                Client.phone.ilike(f"%{search}%"),
                Client.id_number.ilike(f"%{search}%")
            )
        )

    clients = query.order_by(Client.created_at.desc()).all()

    clients_data = []
    for client in clients:
        clients_data.append({
            "client": client,
            "total": len(client.bookings)
        })

    return render_template(
        "clients.html",
        clients=clients_data,
        search=search
    )




@admin.route("/clients")
# @login_required
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

    # These statuses are treated as unfinished.
    incomplete_statuses = ["pending", "incomplete", "in progress"]

    clients_data = []

    for c in clients:
        bookings = c.bookings
        total_bookings = len(bookings)

        incomplete_bookings = [
            booking for booking in bookings
            if (booking.status or "").strip().lower() in incomplete_statuses
        ]

        clients_data.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "id_number": c.id_number,
            "total": total_bookings,
            "has_incomplete_booking": len(incomplete_bookings) > 0,
            "booking_status": (
                "No bookings" if total_bookings == 0
                else "Incomplete booking" if incomplete_bookings
                else "Bookings up to date"
            )
        })

    # AJAX response
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(clients_data)

    return render_template(
        "clients.html",
        clients=clients_data,
        search=search,
        status=request.args.get("status", "")
    )


@admin.route('/clients/register', methods=['GET', 'POST'])
def register_client():
    if request.method == 'POST':
        data = request.form
        files = request.files

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
        db.session.commit()
        flash("Client registered successfully", "success")
        return redirect(url_for('admin.create_booking', client_id=client.id))

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

        # Update files if uploaded
        def update_file(field_name, current_path):
            f = files.get(field_name)
            if f:
                filename = secure_filename(f.filename)
                path = os.path.join('static/uploads', filename)
                f.save(path)
                return path
            return current_path

        client.id_front = update_file('id_front', client.id_front)
        client.id_back = update_file('id_back', client.id_back)
        client.drivers_license = update_file('drivers_license', client.drivers_license)
        client.passport = update_file('passport', client.passport)

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
# @role_required(("admin", "staff"))
def client_details(client_id):
    client = Client.query.get_or_404(client_id)
    return render_template("client_details.html", client=client)






# ------------------- BOOKINGS -------------------
@admin.route("/bookings")
#@login_required
def bookings_page():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    return render_template("bookings.html", bookings=bookings)




@admin.route("/bookings/<int:booking_id>")
# @login_required
def booking_view(booking_id):
    """
    View a single booking
    """
    booking = Booking.query.get_or_404(booking_id)
    return render_template("view_booking.html", booking=booking)


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
@role_required(("admin",))
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
# @login_required
# @role_required(("admin", "staff"))
def create_booking(client_id):
    client = Client.query.get_or_404(client_id)
    cars = Car.query.filter_by(status="available").all()

    if request.method == "POST":
        # 1. Get car_id from form
        car_id = request.form.get("car_id", type=int)

        # 2. Fetch the car object
        car = Car.query.get(car_id)
        if not car:
            flash("Selected car not found.", "danger")
            return redirect(url_for("admin.create_booking"))
       
        pickup_date = datetime.strptime(
            request.form.get("pickup_date"),
            "%Y-%m-%d"
        ).date()

        dropoff_date = datetime.strptime(
            request.form.get("dropoff_date"),
            "%Y-%m-%d"
        ).date()
        notes = request.form.get("notes")


        if dropoff_date <= pickup_date:
            flash("Drop-off date must be after pickup date.", "danger")
            return redirect(request.referrer)

        if not (car_id and pickup_date and dropoff_date):
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("admin.create_booking", client_id=client.id))
        
        days = (dropoff_date - pickup_date).days 
        days = days if days > 0 else 1
        amount = car.price * days


        booking = Booking(
            car_id=car_id,
            client_id=client.id,
            client_name=client.name,
            client_email=client.email,
            client_phone=client.phone,
            pickup_date=pickup_date,
            dropoff_date=dropoff_date,
            notes=notes,
            amount=amount,
            status="pending"
        )

        car = Car.query.get(car_id)
        if car:
            car.status = "booked"

        notification = Notification(
            message=f"New booking created for {client.name}",
            is_read=False
        )

 

        db.session.add_all([booking, notification])
        db.session.commit()

        message = (
            f"Hello {booking.client.name},\n"
            f"Your vehicle booking was successful.\n"
            f"Vehicle: {booking.car.name}\n"
            f"Return Date: {booking.dropoff_date}\n"
            f"Thank you for choosing WheelQ."
        )

        # send_sms(booking.phone, admin_messages)

        flash("Booking created successfully.", "success")
        return redirect(url_for("admin.bookings_page"))

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

        owner_name = request.form.get("owner_name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        car_model = request.form.get("car_model")
        car_year = request.form.get("car_year", type=int)
        car_plate = request.form.get("car_plate")
        notes = request.form.get("notes")

        upload_folder = os.path.join(
            current_app.root_path,
            "static",
            "uploads"
        )

        os.makedirs(
            upload_folder,
            exist_ok=True
        )

        def save_image(file):

            if file and file.filename:

                if not allowed_file(file.filename):
                    flash(
                        "Image file type not allowed.",
                        "danger"
                    )
                    return None

                filename = secure_filename(
                    file.filename
                )

                file.save(
                    os.path.join(
                        upload_folder,
                        filename
                    )
                )

                return filename

            return None

        image_front = save_image(
            request.files.get("image_front")
        )

        image_rear = save_image(
            request.files.get("image_rear")
        )

        image_left = save_image(
            request.files.get("image_left")
        )

        image_right = save_image(
            request.files.get("image_right")
        )

        lease = Lease(
            owner_name=owner_name,
            email=email,
            phone=phone,
            car_model=car_model,
            car_year=car_year,
            car_plate=car_plate,
            notes=notes,
            image_front=image_front,
            image_rear=image_rear,
            image_left=image_left,
            image_right=image_right,
            status="pending"
        )

        db.session.add(lease)
        db.session.commit()

        # log_admin_action(
        #     action="Add Lease",
        #     page="/leases/add",
        #     description=(
        #         f"Added lease request for "
        #         f"{lease.owner_name} - "
        #         f"{lease.car_model}"
        #     )
        # )

        flash(
            "Lease request added successfully.",
            "success"
        )

        return redirect(
            url_for("admin.leases_page")
        )

    return render_template(
        "add_lease.html"
    )

@admin.route("/leases/edit/<int:lease_id>", methods=["GET", "POST"])
@jwt_required()
def edit_lease(lease_id):

    lease = Lease.query.get_or_404(lease_id)

    if request.method == "POST":

        lease.owner_name = request.form.get("owner_name")
        lease.email = request.form.get("email")
        lease.phone = request.form.get("phone")
        lease.car_model = request.form.get("car_model")
        lease.car_year = request.form.get("car_year", type=int)
        lease.car_plate = request.form.get("car_plate")
        lease.status = request.form.get("status")
        lease.notes = request.form.get("notes")

        db.session.commit()

        flash("Lease updated successfully.", "success")

        return redirect(url_for("admin.leases_page"))

    return render_template(
        "edit_lease.html",
        lease=lease
    )

# ============================================================
# DELETE LEASE
# ============================================================

@admin.route(
    "/leases/delete/<int:lease_id>",
    methods=["POST"]
)
@jwt_required()
def delete_lease(lease_id):

    lease = Lease.query.get_or_404(lease_id)

    try:

        db.session.delete(lease)

        db.session.commit()

        flash(
            "Lease deleted successfully.",
            "success"
        )

    except Exception as e:

        db.session.rollback()

        flash(
            f"Failed to delete lease: {str(e)}",
            "danger"
        )

    return redirect(
        url_for("admin.leases_page")
    )
       

@admin.route("/financials")
def financials():
    financials = FinancialRecord.query.order_by(
        FinancialRecord.created_at.desc()
    ).all()

    return render_template(
        "financials.html",
        financials=financials
    )


def get_booking_by_id(booking_id):
    return Booking.query.get(booking_id)






@admin.route('/bookings/<int:booking_id>/pay', methods=['POST'])
# @login_required
def pay_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Prevent duplicate payment records
    if booking.payment_status == 'paid':
        flash('This booking has already been marked as paid.', 'info')
        return redirect(url_for('admin.bookings_page'))

    try:
        # Update the booking payment status
        booking.payment_status = 'paid'

        # Create the financial record
        financial_record = FinancialRecord(
            booking_id=booking.id,
            amount=booking.amount,
            payment_method='Manual',
            status='paid',
            created_at=datetime.utcnow()
        )

        db.session.add(financial_record)
        db.session.commit()

        flash('Booking marked as paid and financial record created.', 'success')

    except Exception:
        db.session.rollback()
        flash('Unable to update payment. Please try again.', 'danger')

    return redirect(url_for('admin.bookings_page'))

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

    return redirect(url_for("admin.bookings_page"))




@admin.route("/admin/bookings/<int:booking_id>/release")
def release_car(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template("release_car.html", booking=booking)


@admin.route("/admin/bookings/<int:booking_id>/activate")
def activate_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.status = "active"
    db.session.commit()

    flash("Vehicle released to client", "success")
    return redirect(url_for("admin.active_bookings"))


@admin.route("/admin/bookings/active")
def active_bookings():
    bookings = Booking.query.filter_by(status="active").all()
    return render_template("active_bookings.html", bookings=bookings)


@admin.route("/admin/bookings/<int:booking_id>/deactivate")
def deactivate_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.status = "completed"
    db.session.commit()
    flash("Booking deactivated", "info")
    return redirect(url_for("admin.active_bookings"))


@admin.route("/admin/bookings/<int:booking_id>/return", methods=["GET", "POST"])
def return_vehicle(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if request.method == "POST":
        booking.status = "completed"
        db.session.commit()
        flash("Vehicle returned successfully", "success")
        return redirect(url_for("admin.bookings_page"))

    return render_template("return.html", booking=booking)


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
#@login_required
def reports_dashboard():
    return render_template("reports/dashboard.html")




@admin.route("/reports/earnings-expenses")
# @login_required
def earnings_expenses():
    period = request.args.get("period", "daily")
    today = datetime.utcnow().date()

    # 📅 Date range logic
    if period == "weekly":
        start_date = today - timedelta(days=7)
        group_format = "%Y-%m-%d"
    elif period == "monthly":
        start_date = today.replace(day=1)
        group_format = "%Y-%m-%d"
    elif period == "annual":
        start_date = today.replace(month=1, day=1)
        group_format = "%Y-%m"
    else:  # daily
        start_date = today
        group_format = "%Y-%m-%d"

    # 📈 Earnings grouped (Hire fees, successful payments)
    earnings_data = (
        db.session.query(
            func.strftime(group_format, FinancialRecord.created_at).label("period"),
            func.sum(FinancialRecord.amount).label("total")
        )
        .filter(
            FinancialRecord.status == "success",
            FinancialRecord.created_at >= start_date
        )
        .group_by("period")
        .all()
    )

    # 📉 Expenses grouped (Lease payments to investors)
    expenses_data = (
        db.session.query(
            func.strftime(group_format, LeasePayment.created_at).label("period"),
            func.sum(LeasePayment.amount).label("total")
        )
        .filter(
            LeasePayment.created_at >= start_date
        )
        .group_by("period")
        .all()
    )

    # 🏷️ Merge labels
    labels = sorted(
        set([e.period for e in earnings_data] + [x.period for x in expenses_data])
    )

    earnings_map = {e.period: float(e.total or 0) for e in earnings_data}
    expenses_map = {x.period: float(x.total or 0) for x in expenses_data}

    earnings_series = [earnings_map.get(label, 0) for label in labels]
    expenses_series = [expenses_map.get(label, 0) for label in labels]

    # ✅ Totals (THIS FIXES YOUR ERROR)
    total_earnings = sum(earnings_series)
    total_expenses = sum(expenses_series)

    # 📋 Individual financial records for table
    records = (
        FinancialRecord.query
        .filter(
            FinancialRecord.status == "success",
            FinancialRecord.created_at >= start_date
        )
        .order_by(FinancialRecord.created_at.desc())
        .all()
    )

    return render_template(
        "reports/earnings_expenses.html",
        period=period,
        total_earnings=total_earnings,
        total_expenses=total_expenses,
        labels=labels,
        earnings_series=earnings_series,
        expenses_series=expenses_series,
        records=records
    )
# List all penalties
@admin.route('/penalties')
def penalties():
    penalties = LatePenalty.query.all()
    return render_template('penalties.html', penalties=penalties)


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


@admin.route("/admin/messages/<int:message_id>")
# @jwt_required()
def admin_message_detail(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    message.is_read = True
    db.session.commit()

    return render_template("message_detail.html", message=message)

@admin.route("/test-sms", methods=["POST"])
def test_sms():
    phone = "+254708920528"  # YOUR NUMBER
    message = "✅ SMS TEST: Onfon Media integration is working."

    result = send_sms(phone, message)
    return {"status": "sent", "provider_response": result}


    
@admin.route("/airport-transfers")
@jwt_required()
def airport_transfers():

    transfers = AirportTransfer.query.order_by(
        AirportTransfer.created_at.desc()
    ).all()

    cars = Car.query.filter_by(
        status="available"
    ).order_by(
        Car.name.asc()
    ).all()

    return render_template(
        "airport_transfers.html",
        transfers=transfers,
        cars=cars
    )

# ================= AIRPORT TRANSFERS =================

def airport_transfer_form_data():
    """Load the data needed by the airport transfer form."""
    return {
        "transfers": AirportTransfer.query.order_by(
            AirportTransfer.created_at.desc()
        ).all(),
        "cars": Car.query.order_by(Car.name.asc()).all()
    }


@admin.route("/airport-transfers/add", methods=["POST"])
def add_airport_transfer():
    name = request.form.get("name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    airport = request.form.get("airport", "").strip()
    notes = request.form.get("notes", "").strip()
    car_id = request.form.get("car_id", type=int)

    if not all([name, phone_number, email, airport]):
        flash("Please fill in the name, phone, email and airport.", "danger")
        return redirect(url_for("admin.airport_transfers_page"))

    car = None
    if car_id:
        car = db.session.get(Car, car_id)
        if car is None:
            flash("The selected vehicle could not be found.", "danger")
            return redirect(url_for("admin.airport_transfers_page"))

    transfer = AirportTransfer(
        name=name,
        phone_number=phone_number,
        email=email,
        airport=airport,
        notes=notes or None,
        car_id=car.id if car else None,
        status="pending"
    )

    db.session.add(transfer)
    db.session.commit()

    flash("Airport transfer created successfully.", "success")
    return redirect(url_for("admin.airport_transfers_page"))


# @admin.route("/airport-transfers/<int:transfer_id>/edit", methods=["GET", "POST"])
# def edit_airport_transfer(transfer_id):
#     transfer = AirportTransfer.query.get_or_404(transfer_id)
#     cars = Car.query.order_by(Car.name.asc()).all()

#     if request.method == "POST":
#         name = request.form.get("name", "").strip()
#         phone_number = request.form.get("phone_number", "").strip()
#         email = request.form.get("email", "").strip()
#         airport = request.form.get("airport", "").strip()
#         notes = request.form.get("notes", "").strip()
#         car_id = request.form.get("car_id", type=int)

#         if not all([name, phone_number, email, airport]):
#             flash("Name, phone, email and airport are required.", "danger")
#             return render_template(
#                 "edit_airport_transfer.html",
#                 transfer=transfer,
#                 cars=cars
#             )

#         car = db.session.get(Car, car_id) if car_id else None
#         if car_id and car is None:
#             flash("The selected vehicle could not be found.", "danger")
#             return render_template(
#                 "edit_airport_transfer.html",
#                 transfer=transfer,
#                 cars=cars
#             )

#         transfer.name = name
#         transfer.phone_number = phone_number
#         transfer.email = email
#         transfer.airport = airport
#         transfer.notes = notes or None
#         transfer.car_id = car.id if car else None

#         db.session.commit()
#         flash("Airport transfer updated successfully.", "success")
#         return redirect(url_for("admin.airport_transfers_page"))

#     return render_template(
#         "edit_airport_transfer.html",
#         transfer=transfer,
#         cars=cars
#     )


@admin.route(
    "/airport-transfers/<int:transfer_id>/edit",
    methods=["GET", "POST"]
)
@jwt_required()
def edit_airport_transfer(transfer_id):

    transfer = AirportTransfer.query.get_or_404(
        transfer_id
    )

    cars = Car.query.filter_by(
        status="available"
    ).order_by(
        Car.name.asc()
    ).all()

    # Include the currently assigned vehicle
    # even if its status is no longer available.
    if transfer.car and transfer.car not in cars:

        cars.append(transfer.car)

    if request.method == "POST":

        transfer.name = request.form.get(
            "name",
            ""
        ).strip()

        transfer.email = request.form.get(
            "email",
            ""
        ).strip()

        transfer.phone_number = request.form.get(
            "phone_number",
            ""
        ).strip()

        transfer.pickup_location = request.form.get(
            "pickup_location",
            ""
        ).strip()

        transfer.dropoff_location = request.form.get(
            "dropoff_location",
            ""
        ).strip()

        transfer.airport = request.form.get(
            "airport",
            ""
        ).strip()

        transfer.notes = request.form.get(
            "notes",
            ""
        ).strip()

        transfer.passengers = request.form.get(
            "passengers",
            type=int
        )

        pickup_datetime = request.form.get(
            "pickup_datetime"
        )

        if pickup_datetime:

            try:
                transfer.pickup_datetime = datetime.fromisoformat(
                    pickup_datetime
                )

            except ValueError:

                flash(
                    "Invalid pickup date and time.",
                    "danger"
                )

                return render_template(
                    "edit_airport_transfer.html",
                    transfer=transfer,
                    cars=cars
                )

        car_id = request.form.get(
            "car_id",
            type=int
        )

        if car_id:

            car = Car.query.get(car_id)

            if not car:

                flash(
                    "Selected vehicle was not found.",
                    "danger"
                )

                return render_template(
                    "edit_airport_transfer.html",
                    transfer=transfer,
                    cars=cars
                )

            transfer.car_id = car.id

        else:

            transfer.car_id = None

        db.session.commit()

        flash(
            "Airport transfer updated successfully.",
            "success"
        )

        return redirect(
            url_for("admin.airport_transfers")
        )

    return render_template(
        "edit_airport_transfer.html",
        transfer=transfer,
        cars=cars
    )

@admin.route("/airport-transfers/<int:transfer_id>/approve", methods=["POST"])
def approve_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    if transfer.status == "cancelled":
        flash("A cancelled transfer cannot be approved.", "warning")
    else:
        transfer.status = "confirmed"
        db.session.commit()
        flash("Airport transfer approved and confirmed.", "success")

    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/reject",
    methods=["POST"]
)
@jwt_required()
def reject_airport_transfer(transfer_id):

    transfer = AirportTransfer.query.get_or_404(
        transfer_id
    )

    transfer.status = "rejected"

    db.session.commit()

    flash(
        "Airport transfer rejected.",
        "danger"
    )

    return redirect(
        url_for("admin.airport_transfers")
    )



@admin.route("/airport-transfers/<int:transfer_id>/cancel", methods=["POST"])
def cancel_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    if transfer.status == "completed":
        flash("A completed transfer cannot be cancelled.", "warning")
    else:
        transfer.status = "cancelled"
        db.session.commit()
        flash("Airport transfer cancelled.", "success")

    return redirect(url_for("admin.airport_transfers"))


@admin.route("/airport-transfers/<int:transfer_id>/delete", methods=["POST"])
def delete_airport_transfer(transfer_id):
    transfer = AirportTransfer.query.get_or_404(transfer_id)

    db.session.delete(transfer)
    db.session.commit()

    flash("Airport transfer deleted successfully.", "success")
    return redirect(url_for("admin.airport_transfers"))


@admin.route(
    "/airport-transfers/<int:transfer_id>/assign-car",
    methods=["POST"]
)
@jwt_required()
def assign_airport_transfer_car(transfer_id):

    transfer = AirportTransfer.query.get_or_404(
        transfer_id
    )

    car_id = request.form.get(
        "car_id",
        type=int
    )

    if not car_id:

        flash(
            "Please select a vehicle.",
            "danger"
        )

        return redirect(
            url_for("admin.airport_transfers")
        )

    car = Car.query.get_or_404(car_id)

    # Only available vehicles should be assigned
    if car.status != "available":

        flash(
            "That vehicle is not currently available.",
            "danger"
        )

        return redirect(
            url_for("admin.airport_transfers")
        )

    transfer.car_id = car.id

    db.session.commit()

    flash(
        f"{car.name} has been assigned to the airport transfer.",
        "success"
    )

    return redirect(
        url_for("admin.airport_transfers")
    )


@admin.route(
    "/airport-transfers/<int:transfer_id>/remove-car",
    methods=["POST"]
)
@jwt_required()
def remove_airport_transfer_car(transfer_id):

    transfer = AirportTransfer.query.get_or_404(
        transfer_id
    )

    transfer.car_id = None

    db.session.commit()

    flash(
        "Vehicle assignment removed.",
        "success"
    )

    return redirect(
        url_for("admin.airport_transfers")
    )