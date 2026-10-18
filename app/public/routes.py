import os
from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, current_app
from flask_mail import Message
from werkzeug.utils import secure_filename
from app import db, mail
from app.models import Car, Lease, Client, Notification, Booking, FinancialRecord, ContactMessage, AirportTransfer
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart



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
    cars = Car.query.all()

    # Mapping database type to tab IDs
    type_map = {
        'Saloon Car': 'saloon',
        'SUV': 'suv',
        'Classic Saloon': 'classic',
        'Truck': 'truck',
        '7 Seater': '7seater',
        '14 Seater': '14seater'
    }

    grouped = {tab_id: [] for tab_id in type_map.values()}

    for car in cars:
        tab_id = type_map.get(car.type.strip(), None)
        if tab_id:
            grouped[tab_id].append(car)

    return render_template("cars.html", cars=grouped)



# Car details page
@public.route("/details/<int:car_id>")
def car_details(car_id):
    car = Car.query.get_or_404(car_id)
    return render_template("details.html", car=car)


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
# @public.route("/mpesa/callback", methods=["POST"])
# def mpesa_callback():
#     data = request.get_json()

#     stk = data["Body"]["stkCallback"]
#     result = stk["ResultCode"]

#     if result == 0:
#         meta = stk["CallbackMetadata"]["Item"]
#         amount = next(i["Value"] for i in meta if i["Name"] == "Amount")
#         receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
#         phone = next(i["Value"] for i in meta if i["Name"] == "PhoneNumber")

#         reference = stk["MerchantRequestID"]
#         booking_id = int(reference.split("-")[-1])

#         booking = Booking.query.get(booking_id)

#         transaction = Transaction(
#             booking_id=booking.id,
#             client_id=booking.client_id,
#             amount=amount,
#             receipt_number=receipt,
#             phone=phone,
#             status="success",
#             payment_type="deposit" if amount < booking.total_amount else "full"
#         )

#         db.session.add(transaction)

#         if amount < booking.total_amount:
#             booking.payment_status = "deposit_paid"
#         else:
#             booking.payment_status = "paid"

#         db.session.commit()

#     return {"ResultCode": 0, "ResultDesc": "Accepted"}


# @public.route("/book/<int:booking_id>/payment", methods=["GET", "POST"])
# def booking_payment(booking_id):
#     booking = Booking.query.get_or_404(booking_id)

#     if request.method == "POST":
#         phone = request.form.get("phone")
#         amount = booking.car.price

#         phone = phone.strip()
#         if phone.startswith("0"):
#             phone = "254" + phone[1:]
#         elif phone.startswith("+"):
#             phone =phone.replace("+", "")

#         mpesa = MpesaDaraja(
#             consumer_key="u7QYXEYKb3zh3sMwmCNIAAiHd7OFd7tmEjmxsL8PWlzmAluS",
#             consumer_secret="qc3j8xBsEAXQF2BAJCoiE8FAuTf0lNOqoTWR4y4aGFtmzqvfmpSvnoCpwqJMs00A",
#             shortcode="174379",
#             passkey="bfb279f9aa9bdbcf158e97dd33f9d54e",
#             callback_url="https://claude-saprophagous-dalia.ngrok-free.dev/mpesa/callback",
#             environment="sandbox"

#         )

#         response = mpesa.stk_push(
#             phone=phone,
#             amount=amount,
#             account_reference=f"BOOKING-{booking.id}",
#             description="WheelQ Car Booking",
#         )

#         if response.get("ResponseCode") == "0":
#             flash("Payment request sent. Enter PIN on your phone.", "success")
#         else:
#             flash("MPesa payment failed. Try again.", "danger")

#     return render_template("public_payment.html", booking=booking)



# @public.route("/payment/success/<int:booking_id>")
# def payment_success(booking_id):
#     booking = Booking.query.get_or_404(booking_id)
#     return render_template("payment_success.html", booking=booking)


 

    
    

