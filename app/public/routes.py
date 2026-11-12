import os
from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, current_app
from flask_mail import Message
from werkzeug.utils import secure_filename
from app import db, mail, cache
from app.models import Car, Lease, Client, Notification, Booking, FinancialRecord, ContactMessage, AirportTransfer
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.utils.cache import cache_get, cache_set
from app.services.notification_service import (
    notify_booking_created,
    notify_financial_charge_created,
    notify_payment_received,
    notify_lease_created,
    notify_lease_payment_received,
    notify_penalty_awarded,
    notify_airport_transfer_created
)


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
PUBLIC_CARS_FOLDER = os.path.join(current_app.root_path, "..", "public", "static", "cars") if False else None
# Define the blueprint
public = Blueprint('public', __name__, template_folder='templates', static_folder='static' , static_url_path='/public/static' )

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
# Homepage
@public.route("/")
def home():
    return render_template("home.html")




# Cars listing page
@public.route("/cars")
def cars():

    cache_key = "wheelq:public:cars"

    # -----------------------------------------------------
    # Try Redis first
    # -----------------------------------------------------

    cached_cars = cache_get(cache_key)

    if cached_cars is not None:
        return render_template(
            "cars.html",
            cars=cached_cars
        )

    # -----------------------------------------------------
    # Redis miss/unavailable -> use database
    # -----------------------------------------------------

    cars = Car.query.all()

    type_map = {
        "Saloon Car": "saloon",
        "SUV": "suv",
        "Classic Saloon": "classic",
        "Truck": "truck",
        "7 Seater": "7seater",
        "14 Seater": "14seater"
    }

    grouped = {
        tab_id: []
        for tab_id in type_map.values()
    }

    for car in cars:

        car_type = (car.type or "").strip()

        tab_id = type_map.get(car_type)

        if tab_id:
            grouped[tab_id].append({
                "id": car.id,
                "name": car.name,
                "brand": car.brand,
                "price": car.price,
                "type": car.type,
                "details": car.details,
                "image": car.image,
                "registration_number": car.registration_number,
                "year": car.year,
                "status": car.status,
                "image_front": car.image_front,
                "image_rear": car.image_rear,
                "image_left": car.image_left,
                "image_right": car.image_right,
                "insurance_provider": car.insurance_provider,
                "insurance_expiry": (
                    car.insurance_expiry.isoformat()
                    if car.insurance_expiry
                    else None
                )
            })

    # -----------------------------------------------------
    # Store in Redis for 60 seconds
    # -----------------------------------------------------

    cache_set(
        cache_key,
        grouped,
        timeout=60
    )

    return render_template(
        "cars.html",
        cars=grouped
    )


# Car details page

# Car details page
@public.route("/details/<int:car_id>")
def car_details(car_id):
    cache_key = f"wheelq:public:car:{car_id}"

    # Try Redis first
    cached_car = cache_get(cache_key)

    if cached_car is not None:
        return render_template("details.html", car=cached_car)

    # Fall back to the database if the cache is empty
    car = Car.query.get_or_404(car_id)

    car_data = {
        "id": car.id,
        "name": car.name,
        "brand": car.brand,
        "type": car.type,
        "price": car.price,
        "status": car.status,
        "details": car.details,
        "image": car.image,
        "image_front": car.image_front,
        "image_rear": car.image_rear,
        "image_left": car.image_left,
        "image_right": car.image_right,
    }

    # Cache for 60 seconds
    cache_set(cache_key, car_data, timeout=60)

    return render_template("details.html", car=car_data)



# About page
@public.route("/about")
def about():
    return render_template("about.html")


# Contact page

@public.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        admin_email = current_app.config.get("ADMIN_EMAIL")

        if not admin_email:
            flash("Admin email not configured", "danger")
            return redirect(url_for("public.contact"))
                
        if not name or not email or not message:
            flash("All fields are required", "danger")
            return redirect(url_for("public.contact"))
        
        contact = ContactMessage(
            name=name,
            email=email,
            message=message
        )
        db.session.add(contact)
        db.session.commit()

        msg = Message(
            subject=f"New Contact Message from {name}",
            sender= current_app.config["MAIL_USERNAME"],
            recipients=[current_app.config["ADMIN_EMAIL"]],
            reply_to=email
        )

        msg.body = f"""
        You have received a new message from WheelQ website.

        Name: {name}
        Email: {email}

        Message:
        {message}
        """

        mail.send(msg)

        flash("Your message has been sent successfully!", "success")
        return redirect(url_for("public.contact"))

    return render_template("contact.html")





# Book car page
@public.route("/book/<int:car_id>", methods=["GET", "POST"])
def book_car(car_id):
    car = Car.query.get_or_404(car_id)

    if request.method == "POST":
        # get form data
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        notes = request.form.get("notes")

        pickup_date = datetime.strptime(form.pickup_date.data, "%Y-%m-%d")
        dropoff_date = datetime.strptime(form.dropoff_date.data, "%Y-%m-%d")
        days = (dropoff_date - pickup_date).days or 1
        amount = car.price * days
        # find or create client
        client = Client.query.filter_by(email=email).first()
        if not client:
            client = Client(name=full_name, email=email, phone=phone)
            db.session.add(client)
            db.session.commit()

        # create booking
        booking = Booking(
            car_id=car.id,
            client_id=client.id,
            client_name=full_name,
            client_email=email,
            client_phone=phone,
            pickup_date=pickup_date,
            dropoff_date=dropoff_date,
            amount=amount,
            notes=notes,
            status="pending",
            payment_status="unpaid"
        )

        db.session.add(booking)
        db.session.commit()

        print("BOOKING CREATED:", booking.id)

        # ✅ REDIRECT TO PAYMENT
        # return redirect(url_for("public.booking_payment", booking_id=booking.id))

    return render_template("booking_landing.html", car=car)






@public.route("/lease", methods=["GET"])
def lease_page():
    return render_template("lease.html")

@public.route("/lease/submit", methods=["POST"])
def submit_lease():
    owner_name = request.form.get("owner_name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    car_model = request.form.get("car_model")
    car_year = request.form.get("car_year")
    car_plate = request.form.get("car_plate")
    notes = request.form.get("notes")

    # Ensure upload folder exists
    upload_folder = os.path.join(current_app.root_path, "static", "uploads")
    os.makedirs(upload_folder, exist_ok=True)

    # Same save_image logic as add_car
    def save_image(file):
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Image file type not allowed.", "danger")
                return None
            filename = secure_filename(file.filename)
            file.save(os.path.join(upload_folder, filename))
            return filename
        return None

    # Save images
    image_front = save_image(request.files.get("image_front"))
    image_rear = save_image(request.files.get("image_rear"))
    image_left = save_image(request.files.get("image_left"))
    image_right = save_image(request.files.get("image_right"))

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

    notification = Notification(
        message=f"New lease request from {owner_name} ({car_model})"
    )
    db.session.add(notification)
    db.session.commit()

    db.session.add(lease)
    db.session.commit()

    try:
        notify_lease_created(lease.id)
    except Exception:
        current_app.logger.exception(
            "Lease email notification failed"
        ) 

    flash("Lease request submitted successfully!", "success")
    return redirect(url_for("public.lease_page"))



@public.route("/airport-transfer", methods=["GET", "POST"])
def airport_transfer():

    if request.method == "POST":

        name = request.form.get("client_name", "").strip()
        email = request.form.get("client_email", "").strip()
        phone = request.form.get("client_phone", "").strip()

        pickup_location = request.form.get(
            "pickup_location", ""
        ).strip()

        dropoff_location = request.form.get(
            "dropoff_location", ""
        ).strip()

        pickup_datetime_string = request.form.get(
            "pickup_datetime", ""
        ).strip()

        passengers = request.form.get(
            "passengers",
            type=int
        )

        notes = request.form.get(
            "notes",
            ""
        ).strip()

        # Basic validation
        if not name or not email or not phone:
            flash(
                "Please fill in all your contact information.",
                "danger"
            )

            return render_template(
                "airport_transfer.html"
            )

        if not pickup_location or not dropoff_location:
            flash(
                "Please provide both pickup and dropoff locations.",
                "danger"
            )

            return render_template(
                "airport_transfer.html"
            )

        if not pickup_datetime_string:
            flash(
                "Please select your pickup date and time.",
                "danger"
            )

            return render_template(
                "airport_transfer.html"
            )

        if not passengers or passengers < 1:
            flash(
                "Please enter a valid number of passengers.",
                "danger"
            )

            return render_template(
                "airport_transfer.html"
            )

        # Convert datetime-local value
        try:
            pickup_datetime = datetime.fromisoformat(
                pickup_datetime_string
            )
        except ValueError:

            flash(
                "Invalid pickup date and time.",
                "danger"
            )

            return render_template(
                "airport_transfer.html"
            )

        # Create transfer request
        transfer = AirportTransfer(
            name=name,
            email=email,
            phone_number=phone,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            pickup_datetime=pickup_datetime,
            passengers=passengers,
            notes=notes,
            status="pending"
        )

        db.session.add(transfer)
        db.session.commit()

        try:
            notify_airport_transfer_created(transfer.id)
        except Exception:
            current_app.logger.exception(
                "Airport transfer email notification failed"
            ) 

        flash(
            "Your airport transfer request has been submitted successfully. "
            "Our team will contact you to confirm the details.",
            "success"
        )

        return redirect(
            url_for("public.airport_transfer")
        )

    return render_template(
        "airport_transfer.html"
    )


    
    

