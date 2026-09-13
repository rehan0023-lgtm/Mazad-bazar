from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    send_from_directory,
    flash
)

import mysql.connector
import os

from decimal import Decimal, InvalidOperation
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.config["UPLOAD_FOLDER"] = "uploads"

app.secret_key = "mazad-bazaar-secret-key"

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp"
}


# =========================================================
# DATABASE
# =========================================================

def get_db():

    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="mazad_bazar"
    )


# =========================================================
# HELPER FUNCTIONS
# =========================================================
def create_notification(
    user_id,
    auction_id,
    notification_type,
    message
):

    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO notifications
            (
                user_id,
                auction_id,
                type,
                message
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
        """, (
            user_id,
            auction_id,
            notification_type,
            message
        ))

        db.commit()

    except mysql.connector.Error:

        if db:
            db.rollback()

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()

def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


def valid_contact_number(contact_number):

    if not contact_number:
        return False

    contact_number = contact_number.strip()

    return (
        contact_number.isdigit()
        and len(contact_number) == 10
    )


def parse_positive_decimal(value):

    try:

        amount = Decimal(
            str(value).strip()
        )

        if amount <= 0:
            return None

        return amount

    except (
        InvalidOperation,
        ValueError,
        TypeError
    ):

        return None


def admin_required():

    if "user_id" not in session:
        return False

    user_id = session["user_id"]

    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )

        cursor.execute("""
            SELECT
                id,
                name,
                role
            FROM users
            WHERE id = %s
        """, (
            user_id,
        ))

        user = cursor.fetchone()

        if not user:

            session.clear()

            return False

        session["name"] = user["name"]
        session["role"] = user["role"]

        return user["role"] == "admin"

    except mysql.connector.Error:

        return False

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


# =========================================================
# AUTOMATICALLY CLOSE EXPIRED AUCTIONS
# =========================================================

def close_expired_auctions():

    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )

        cursor.execute("""
            SELECT
                id,
                seller_id,
                product_name
            FROM auctions
            WHERE status = 'active'
            AND closing_date <= NOW()
        """)

        expired_auctions = cursor.fetchall()


        for auction in expired_auctions:

            auction_id = auction["id"]
            seller_id = auction["seller_id"]
            product_name = auction["product_name"]


            # =================================================
            # FIND HIGHEST BID
            # =================================================

            cursor.execute("""
                SELECT
                    bidder_id,
                    bid_amount
                FROM bids
                WHERE auction_id = %s
                ORDER BY bid_amount DESC, id DESC
                LIMIT 1
            """, (
                auction_id,
            ))

            highest_bid = cursor.fetchone()


            if highest_bid:

                winner_id = highest_bid["bidder_id"]
                winning_amount = highest_bid["bid_amount"]

                cursor.execute("""
                    UPDATE auctions
                    SET
                        status = 'closed',
                        winner_id = %s,
                        current_bid = %s
                    WHERE id = %s
                    AND status = 'active'
                """, (
                    winner_id,
                    winning_amount,
                    auction_id
                ))

                # =================================================
                # NOTIFY WINNER AND LOSING BIDDERS
                # =================================================

                cursor.execute("""
                    SELECT DISTINCT bidder_id
                    FROM bids
                    WHERE auction_id = %s
                """, (
                    auction_id,
                ))

                bidders = cursor.fetchall()

                for bidder in bidders:

                    bidder_id = bidder["bidder_id"]

                    if bidder_id == winner_id:

                        cursor.execute("""
                            INSERT INTO notifications
                            (
                                user_id,
                                auction_id,
                                type,
                                message
                            )
                            VALUES
                            (
                                %s,
                                %s,
                                %s,
                                %s
                            )
                        """, (
                            bidder_id,
                            auction_id,
                            "won",
                            f"Congratulations! You won the auction for {product_name} with a bid of ₹{winning_amount}."
                        ))

                    else:

                        cursor.execute("""
                            INSERT INTO notifications
                            (
                                user_id,
                                auction_id,
                                type,
                                message
                            )
                            VALUES
                            (
                                %s,
                                %s,
                                %s,
                                %s
                            )
                        """, (
                            bidder_id,
                            auction_id,
                            "lost",
                            f"The auction for {product_name} has ended. Another bidder placed the winning bid."
                        ))


                # =================================================
                # NOTIFY SELLER
                # =================================================

                cursor.execute("""
                    INSERT INTO notifications
                    (
                        user_id,
                        auction_id,
                        type,
                        message
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                """, (
                    seller_id,
                    auction_id,
                    "auction_ended",
                    f"Your auction for {product_name} has ended. The winning bid was ₹{winning_amount}."
                ))

            else:

                cursor.execute("""
                    UPDATE auctions
                    SET
                        status = 'closed',
                        winner_id = NULL
                    WHERE id = %s
                    AND status = 'active'
                """, (
                    auction_id,
                ))

                # =================================================
                # NOTIFY SELLER WHEN THERE ARE NO BIDS
                # =================================================

                cursor.execute("""
                    INSERT INTO notifications
                    (
                        user_id,
                        auction_id,
                        type,
                        message
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                """, (
                    seller_id,
                    auction_id,
                    "auction_ended",
                    f"Your auction for {product_name} has ended without receiving any bids."
                ))


        db.commit()

    except mysql.connector.Error:

        if db:
            db.rollback()

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    close_expired_auctions()


    if "user_id" in session:

        db = None
        cursor = None

        try:

            db = get_db()

            cursor = db.cursor(
                dictionary=True,
                buffered=True
            )

            cursor.execute("""
                SELECT
                    id,
                    name,
                    email,
                    role
                FROM users
                WHERE id = %s
            """, (
                session["user_id"],
            ))

            user = cursor.fetchone()


            if user:

                session["name"] = user["name"]
                session["role"] = user["role"]

            else:

                session.clear()


        except mysql.connector.Error:

            pass

        finally:

            if cursor:
                cursor.close()

            if db:
                db.close()


    return render_template(
        "index.html"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        if not name:

            flash(
                "Name is required.",
                "danger"
            )

            return redirect("/register")


        if not email or "@" not in email:

            flash(
                "Please enter a valid email address.",
                "danger"
            )

            return redirect("/register")


        if not valid_contact_number(phone):

            flash(
                "Phone number must contain exactly 10 digits.",
                "danger"
            )

            return redirect("/register")


        if len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "danger"
            )

            return redirect("/register")


        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "danger"
            )

            return redirect("/register")


        db = None
        cursor = None

        try:

            db = get_db()

            cursor = db.cursor(
                dictionary=True,
                buffered=True
            )


            cursor.execute("""
                SELECT id
                FROM users
                WHERE email = %s
            """, (
                email,
            ))

            existing_user = cursor.fetchone()


            if existing_user:

                flash(
                    "An account with this email already exists.",
                    "warning"
                )

                return redirect("/register")


            # =================================================
            # HASH PASSWORD
            # =================================================

            hashed_password = generate_password_hash(
                password
            )


            cursor.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    phone,
                    password,
                    role
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                name,
                email,
                phone,
                hashed_password,
                "user"
            ))


            db.commit()


        except mysql.connector.Error as error:

            if db:
                db.rollback()

            flash(
                "Registration failed: " + str(error),
                "danger"
            )

            return redirect("/register")


        finally:

            if cursor:
                cursor.close()

            if db:
                db.close()


        flash(
            "Registration successful! You can now log in.",
            "success"
        )

        return redirect("/login")


    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )


        if not email or not password:

            flash(
                "Email and password are required.",
                "danger"
            )

            return redirect("/login")


        db = None
        cursor = None

        try:

            db = get_db()

            cursor = db.cursor(
                dictionary=True,
                buffered=True
            )


            cursor.execute("""
                SELECT
                    id,
                    name,
                    email,
                    password,
                    role
                FROM users
                WHERE email = %s
            """, (
                email,
            ))


            user = cursor.fetchone()


        except mysql.connector.Error as error:

            flash(
                "Login failed: " + str(error),
                "danger"
            )

            return redirect("/login")


        finally:

            if cursor:
                cursor.close()

            if db:
                db.close()


        if not user:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return redirect("/login")


        try:

            password_correct = check_password_hash(
                user["password"],
                password
            )

        except ValueError:

            password_correct = False


        if not password_correct:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return redirect("/login")


        session.clear()

        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]


        flash(
            "Login successful!",
            "success"
        )


        return redirect("/")


    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect("/")


# =========================================================
# BROWSE AUCTIONS + SEARCH
# =========================================================

@app.route("/auctions")
def auctions():

    close_expired_auctions()


    search = request.args.get(
        "search",
        ""
    ).strip()


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        if search:

            search_value = (
                "%"
                + search
                + "%"
            )


            cursor.execute("""
                SELECT *
                FROM auctions
                WHERE status = 'active'
                AND
                (
                    product_name LIKE %s
                    OR description LIKE %s
                )
                ORDER BY created_at DESC
            """, (
                search_value,
                search_value
            ))


        else:

            cursor.execute("""
                SELECT *
                FROM auctions
                WHERE status = 'active'
                ORDER BY created_at DESC
            """)


        auctions = cursor.fetchall()


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return render_template(
        "auctions.html",
        auctions=auctions,
        search=search
    )


# =========================================================
# CREATE AUCTION
# =========================================================

@app.route(
    "/create-auction",
    methods=["GET", "POST"]
)
def create_auction():

    if "user_id" not in session:

        flash(
            "Please log in before creating an auction.",
            "warning"
        )

        return redirect("/login")


    if request.method == "POST":

        product_name = request.form.get(
            "product_name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        starting_bid = request.form.get(
            "starting_bid",
            ""
        ).strip()

        closing_date = request.form.get(
            "closing_date",
            ""
        ).strip()


        if not product_name:

            flash(
                "Product name is required.",
                "danger"
            )

            return redirect("/create-auction")


        starting_bid_value = parse_positive_decimal(
            starting_bid
        )


        if starting_bid_value is None:

            flash(
                "Starting bid must be greater than ₹0.",
                "danger"
            )

            return redirect("/create-auction")


        try:

            closing_datetime = datetime.strptime(
                closing_date,
                "%Y-%m-%dT%H:%M"
            )

        except ValueError:

            flash(
                "Invalid closing date.",
                "danger"
            )

            return redirect("/create-auction")


        if closing_datetime <= datetime.now():

            flash(
                "Auction closing date must be in the future.",
                "danger"
            )

            return redirect("/create-auction")


        image = request.files.get(
            "product_image"
        )


        if not image or image.filename == "":

            flash(
                "Please select a product image.",
                "danger"
            )

            return redirect("/create-auction")


        if not allowed_file(
            image.filename
        ):

            flash(
                "Invalid image type. Allowed: JPG, JPEG, PNG, GIF, WEBP.",
                "danger"
            )

            return redirect("/create-auction")


        image_name = secure_filename(
            image.filename
        )


        if not image_name:

            flash(
                "Invalid image filename.",
                "danger"
            )

            return redirect("/create-auction")


        os.makedirs(
            app.config["UPLOAD_FOLDER"],
            exist_ok=True
        )


        image.save(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_name
            )
        )


        seller_id = session["user_id"]


        db = None
        cursor = None

        try:

            db = get_db()

            cursor = db.cursor()


            cursor.execute("""
                INSERT INTO auctions
                (
                    seller_id,
                    product_name,
                    product_image,
                    description,
                    starting_bid,
                    current_bid,
                    closing_date
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                seller_id,
                product_name,
                image_name,
                description,
                starting_bid_value,
                0,
                closing_datetime
            ))


            db.commit()


        except mysql.connector.Error as error:

            if db:
                db.rollback()


            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_name
            )


            if os.path.exists(image_path):

                try:
                    os.remove(image_path)
                except OSError:
                    pass


            flash(
                "Auction creation failed: " + str(error),
                "danger"
            )

            return redirect("/create-auction")


        finally:

            if cursor:
                cursor.close()

            if db:
                db.close()


        flash(
            "Auction created successfully!",
            "success"
        )

        return redirect("/auctions")


    return render_template(
        "create_auction.html"
    )


# =========================================================
# UPLOADS
# =========================================================

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# =========================================================
# PRODUCT DETAILS
# =========================================================

@app.route(
    "/product/<int:product_id>"
)
def product_details(product_id):

    close_expired_auctions()


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        cursor.execute("""
            SELECT
                a.*,
                u.name AS winner_name
            FROM auctions a
            LEFT JOIN users u
                ON a.winner_id = u.id
            WHERE a.id = %s
        """, (
            product_id,
        ))


        auction = cursor.fetchone()


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    if not auction:

        flash(
            "Auction not found.",
            "danger"
        )

        return redirect("/auctions")


    return render_template(
        "product_details.html",
        auction=auction
    )


# =========================================================
# PLACE BID
# =========================================================

@app.route(
    "/product/<int:product_id>/bid",
    methods=["POST"]
)
def place_bid(product_id):

    if "user_id" not in session:

        flash(
            "Please log in before placing a bid.",
            "warning"
        )

        return redirect("/login")


    close_expired_auctions()


    bidder_id = session["user_id"]


    bid_amount_raw = request.form.get(
        "bid_amount",
        ""
    ).strip()


    contact_number = request.form.get(
        "contact_number",
        ""
    ).strip()


    # =====================================================
    # VALIDATE BID AMOUNT
    # =====================================================

    bid_amount = parse_positive_decimal(
        bid_amount_raw
    )


    if bid_amount is None:

        flash(
            "Bid amount must be greater than ₹0.",
            "danger"
        )

        return redirect(
            f"/product/{product_id}"
        )


    # =====================================================
    # VALIDATE CONTACT
    # =====================================================

    if not valid_contact_number(
        contact_number
    ):

        flash(
            "Contact number must contain exactly 10 digits.",
            "danger"
        )

        return redirect(
            f"/product/{product_id}"
        )


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        # =================================================
        # GET AUCTION
        # =================================================

        cursor.execute("""
            SELECT *
            FROM auctions
            WHERE id = %s
        """, (
            product_id,
        ))


        auction = cursor.fetchone()


        if not auction:

            flash(
                "Auction not found.",
                "danger"
            )

            return redirect("/auctions")


        # =================================================
        # CHECK STATUS
        # =================================================

        if auction["status"] != "active":

            flash(
                "This auction is closed. You cannot place a bid.",
                "danger"
            )

            return redirect(
                f"/product/{product_id}"
            )


        # =================================================
        # CHECK CLOSING DATE
        # =================================================

        if auction["closing_date"] <= datetime.now():

            cursor.execute("""
                SELECT
                    bidder_id,
                    bid_amount
                FROM bids
                WHERE auction_id = %s
                ORDER BY bid_amount DESC, id DESC
                LIMIT 1
            """, (
                product_id,
            ))


            highest_bid = cursor.fetchone()


            if highest_bid:

                cursor.execute("""
                    UPDATE auctions
                    SET
                        status = 'closed',
                        winner_id = %s,
                        current_bid = %s
                    WHERE id = %s
                """, (
                    highest_bid["bidder_id"],
                    highest_bid["bid_amount"],
                    product_id
                ))

            else:

                cursor.execute("""
                    UPDATE auctions
                    SET
                        status = 'closed',
                        winner_id = NULL
                    WHERE id = %s
                """, (
                    product_id,
                ))


            db.commit()


            flash(
                "This auction has just closed. You cannot place a bid.",
                "danger"
            )

            return redirect(
                f"/product/{product_id}"
            )


        # =================================================
        # SELLER CANNOT BID
        # =================================================

        if auction["seller_id"] == bidder_id:

            flash(
                "You cannot bid on your own auction!",
                "danger"
            )

            return redirect(
                f"/product/{product_id}"
            )


        # =================================================
        # CURRENT BID
        # =================================================

        current_bid = Decimal(
            str(
                auction["current_bid"]
                or 0
            )
        )


        if bid_amount <= current_bid:

            flash(
                f"Your bid must be higher than ₹{current_bid}.",
                "warning"
            )

            return redirect(
                f"/product/{product_id}"
            )


        # =================================================
        # CHECK LATEST BID
        # =================================================

        cursor.execute("""
            SELECT
                bidder_id,
                bid_amount
            FROM bids
            WHERE auction_id = %s
            ORDER BY bid_amount DESC, id DESC
            LIMIT 1
        """, (
            product_id,
        ))


        latest_highest = cursor.fetchone()


        if latest_highest:

            database_highest = Decimal(
                str(
                    latest_highest["bid_amount"]
                )
            )


            if bid_amount <= database_highest:

                flash(
                    f"Your bid must be higher than ₹{database_highest}.",
                    "warning"
                )

                return redirect(
                    f"/product/{product_id}"
                )


        # =================================================
        # INSERT BID
        # =================================================

        cursor.execute("""
            INSERT INTO bids
            (
                auction_id,
                bidder_id,
                bid_amount,
                contact_number
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
        """, (
            product_id,
            bidder_id,
            bid_amount,
            contact_number
        ))


        # =================================================
        # NOTIFY PREVIOUS HIGHEST BIDDER
        # =================================================

        if latest_highest:

            previous_bidder_id = latest_highest["bidder_id"]

            if previous_bidder_id != bidder_id:

                cursor.execute("""
                    INSERT INTO notifications
                    (
                        user_id,
                        auction_id,
                        type,
                        message
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                """, (
                    previous_bidder_id,
                    product_id,
                    "outbid",
                    f"You have been outbid on {auction['product_name']}. Someone placed a higher bid."
                ))


        # =================================================
        # NOTIFY SELLER OF NEW BID
        # =================================================

        if auction["seller_id"] != bidder_id:

            cursor.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    auction_id,
                    type,
                    message
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                auction["seller_id"],
                product_id,
                "new_bid",
                f"New bid of ₹{bid_amount} received on your auction: {auction['product_name']}."
            ))


        # =================================================
        # UPDATE CURRENT BID
        # =================================================

        cursor.execute("""
            UPDATE auctions
            SET current_bid = %s
            WHERE id = %s
            AND status = 'active'
        """, (
            bid_amount,
            product_id
        ))


        db.commit()


        # =================================================
        # SUCCESS MESSAGE
        # =================================================

        flash(
            "Your bid was placed successfully!",
            "success"
        )


    except mysql.connector.Error as error:

        if db:
            db.rollback()

        flash(
            "Bid failed: " + str(error),
            "danger"
        )

        return redirect(
            f"/product/{product_id}"
        )


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return redirect(
        f"/product/{product_id}"
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def notifications():

    if "user_id" not in session:

        flash(
            "Please log in first.",
            "warning"
        )

        return redirect("/login")


    user_id = session["user_id"]

    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )

        cursor.execute("""
            SELECT
                n.id,
                n.auction_id,
                n.type,
                n.message,
                n.is_read,
                n.created_at,
                a.product_name
            FROM notifications n
            LEFT JOIN auctions a
                ON n.auction_id = a.id
            WHERE n.user_id = %s
            ORDER BY n.created_at DESC
        """, (
            user_id,
        ))

        notifications_list = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) AS unread_count
            FROM notifications
            WHERE user_id = %s
            AND is_read = 0
        """, (
            user_id,
        ))

        unread_count = cursor.fetchone()["unread_count"]

    except mysql.connector.Error as error:

        flash(
            "Could not load notifications: " + str(error),
            "danger"
        )

        notifications_list = []
        unread_count = 0

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return render_template(
        "notifications.html",
        notifications=notifications_list,
        unread_count=unread_count
    )


@app.route(
    "/notifications/mark-read/<int:notification_id>",
    methods=["POST"]
)
def mark_notification_read(notification_id):

    if "user_id" not in session:

        return redirect("/login")


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor()

        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE id = %s
            AND user_id = %s
        """, (
            notification_id,
            session["user_id"]
        ))

        db.commit()

    except mysql.connector.Error:

        if db:
            db.rollback()

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return redirect("/notifications")


@app.route(
    "/notifications/mark-all-read",
    methods=["POST"]
)
def mark_all_notifications_read():

    if "user_id" not in session:

        return redirect("/login")


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor()

        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = %s
            AND is_read = 0
        """, (
            session["user_id"],
        ))

        db.commit()

    except mysql.connector.Error:

        if db:
            db.rollback()

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return redirect("/notifications")


# =========================================================
# MY BIDS
# =========================================================

@app.route("/my-bids")
def my_bids():

    if "user_id" not in session:

        flash(
            "Please log in first.",
            "warning"
        )

        return redirect("/login")


    close_expired_auctions()


    bidder_id = session["user_id"]


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        cursor.execute("""
            SELECT

                b.id AS bid_id,
                b.bid_amount,
                b.contact_number,
                b.created_at,

                a.id AS auction_id,
                a.product_name,
                a.product_image,
                a.starting_bid,
                a.current_bid,
                a.closing_date,
                a.status,
                a.winner_id

            FROM bids b

            JOIN auctions a
                ON b.auction_id = a.id

            WHERE b.bidder_id = %s

            ORDER BY
                b.created_at DESC

        """, (
            bidder_id,
        ))


        my_bids = cursor.fetchall()


        for bid in my_bids:

            if bid["status"] == "closed":

                if bid["winner_id"] == bidder_id:

                    bid["bid_status"] = "won"

                else:

                    bid["bid_status"] = "lost"


            else:

                cursor.execute("""
                    SELECT
                        bidder_id,
                        bid_amount
                    FROM bids
                    WHERE auction_id = %s
                    ORDER BY bid_amount DESC, id DESC
                    LIMIT 1
                """, (
                    bid["auction_id"],
                ))


                highest_bid = cursor.fetchone()


                if highest_bid:

                    if highest_bid["bidder_id"] == bidder_id:

                        bid["bid_status"] = "highest"

                    else:

                        bid["bid_status"] = "outbid"

                else:

                    bid["bid_status"] = "waiting"


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return render_template(
        "my_bids.html",
        my_bids=my_bids
    )


# =========================================================
# SELLER DASHBOARD
# =========================================================
# =========================================================
# AUCTION HISTORY
# =========================================================

# =========================================================
# MY AUCTION HISTORY
# =========================================================

@app.route("/auction-history")
def auction_history():

    # -----------------------------------------------------
    # LOGIN REQUIRED
    # -----------------------------------------------------

    if "user_id" not in session:

        flash(
            "Please log in to view your auction history.",
            "warning"
        )

        return redirect("/login")


    close_expired_auctions()


    user_id = session["user_id"]


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        # =================================================
        # ADMIN
        # =================================================
        # Admin can see every completed auction.
        # =================================================

        if session.get("role") == "admin":

            cursor.execute("""
                SELECT

                    a.id,
                    a.product_name,
                    a.product_image,
                    a.starting_bid,
                    a.current_bid,
                    a.closing_date,
                    a.status,
                    a.winner_id,

                    u.name AS winner_name

                FROM auctions a

                LEFT JOIN users u
                    ON a.winner_id = u.id

                WHERE a.status = 'closed'

                ORDER BY
                    a.closing_date DESC
            """)


        # =================================================
        # NORMAL USER
        # =================================================
        # User sees an auction if:
        #
        # 1. They are the seller
        # OR
        # 2. They placed a bid on that auction
        #
        # DISTINCT prevents an auction from appearing
        # multiple times if the user placed multiple bids.
        # =================================================

        else:

            cursor.execute("""
                SELECT DISTINCT

                    a.id,
                    a.product_name,
                    a.product_image,
                    a.starting_bid,
                    a.current_bid,
                    a.closing_date,
                    a.status,
                    a.winner_id,

                    u.name AS winner_name

                FROM auctions a

                LEFT JOIN users u
                    ON a.winner_id = u.id

                LEFT JOIN bids b
                    ON a.id = b.auction_id
                    AND b.bidder_id = %s

                WHERE a.status = 'closed'

                AND
                (
                    a.seller_id = %s
                    OR b.bidder_id = %s
                )

                ORDER BY
                    a.closing_date DESC

            """, (
                user_id,
                user_id,
                user_id
            ))


        auctions = cursor.fetchall()


    except mysql.connector.Error as error:

        flash(
            "Could not load auction history: "
            + str(error),
            "danger"
        )

        auctions = []


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return render_template(
        "auction_history.html",
        auctions=auctions
    )
@app.route("/seller-dashboard")
def seller_dashboard():

    if "user_id" not in session:

        flash(
            "Please log in first.",
            "warning"
        )

        return redirect("/login")


    close_expired_auctions()


    seller_id = session["user_id"]


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        # =================================================
        # AUCTIONS + WINNER
        # =================================================

        cursor.execute("""
            SELECT

                a.*,

                u.name AS winner_name,

                (
                    SELECT
                        b.contact_number

                    FROM bids b

                    WHERE b.auction_id = a.id

                    AND b.bidder_id = a.winner_id

                    ORDER BY b.bid_amount DESC

                    LIMIT 1

                ) AS winner_contact

            FROM auctions a

            LEFT JOIN users u
                ON a.winner_id = u.id

            WHERE a.seller_id = %s

            ORDER BY a.created_at DESC

        """, (
            seller_id,
        ))


        seller_auctions = cursor.fetchall()


        total_listings = len(
            seller_auctions
        )


        # =================================================
        # TOTAL BIDS
        # =================================================

        cursor.execute("""
            SELECT
                COUNT(*) AS total_bids

            FROM bids b

            JOIN auctions a
                ON b.auction_id = a.id

            WHERE a.seller_id = %s

        """, (
            seller_id,
        ))


        total_bids = cursor.fetchone()[
            "total_bids"
        ]


        # =================================================
        # HIGHEST BID
        # =================================================

        cursor.execute("""
            SELECT
                MAX(b.bid_amount)
                AS highest_bid

            FROM bids b

            JOIN auctions a
                ON b.auction_id = a.id

            WHERE a.seller_id = %s

        """, (
            seller_id,
        ))


        result = cursor.fetchone()


        highest_bid = (
            result["highest_bid"]
            or 0
        )


        # =================================================
        # RECEIVED BIDS
        # =================================================

        cursor.execute("""
            SELECT

                b.id,
                b.bidder_id,
                b.bid_amount,
                b.contact_number,
                b.created_at,

                a.product_name,
                a.id AS auction_id,
                a.status AS auction_status,
                a.winner_id,

                u.name AS bidder_name

            FROM bids b

            JOIN auctions a
                ON b.auction_id = a.id

            JOIN users u
                ON b.bidder_id = u.id

            WHERE a.seller_id = %s

            ORDER BY b.created_at DESC

        """, (
            seller_id,
        ))


        received_bids = cursor.fetchall()


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return render_template(
        "seller_dashboard.html",

        seller_auctions=seller_auctions,

        total_listings=total_listings,

        total_bids=total_bids,

        highest_bid=highest_bid,

        received_bids=received_bids
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin_dashboard():

    if not admin_required():

        return (
            "Access denied. "
            "Admin privileges required.",
            403
        )


    close_expired_auctions()


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        cursor.execute("""
            SELECT COUNT(*) AS total_users
            FROM users
        """)

        total_users = cursor.fetchone()[
            "total_users"
        ]


        cursor.execute("""
            SELECT COUNT(*) AS active_auctions
            FROM auctions
            WHERE status = 'active'
        """)

        active_auctions = cursor.fetchone()[
            "active_auctions"
        ]


        cursor.execute("""
            SELECT COUNT(*) AS total_bids
            FROM bids
        """)

        total_bids = cursor.fetchone()[
            "total_bids"
        ]


        cursor.execute("""
            SELECT
                id,
                name,
                email,
                phone,
                role
            FROM users
            ORDER BY id DESC
        """)

        users = cursor.fetchall()


        cursor.execute("""
            SELECT *
            FROM auctions
            ORDER BY created_at DESC
        """)

        auctions = cursor.fetchall()


        cursor.execute("""
            SELECT

                b.id AS bid_id,
                b.bid_amount,
                b.contact_number,
                b.created_at,
                b.bidder_id,

                u.name AS bidder_name,
                u.email AS bidder_email,

                a.id AS auction_id,
                a.product_name,
                a.current_bid,
                a.status AS auction_status,
                a.winner_id

            FROM bids b

            JOIN users u
                ON b.bidder_id = u.id

            JOIN auctions a
                ON b.auction_id = a.id

            ORDER BY b.created_at DESC
        """)

        all_bids = cursor.fetchall()


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    return render_template(
        "admin_dashboard.html",

        total_users=total_users,

        active_auctions=active_auctions,

        total_bids=total_bids,

        users=users,

        auctions=auctions,

        all_bids=all_bids
    )


# =========================================================
# ADMIN - DELETE USER
# =========================================================

@app.route(
    "/admin/delete-user/<int:user_id>",
    methods=["POST"]
)
def admin_delete_user(user_id):

    if not admin_required():

        return "Access denied.", 403


    if user_id == session["user_id"]:

        flash(
            "You cannot delete your own admin account.",
            "danger"
        )

        return redirect("/admin")


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        cursor.execute("""
            SELECT *
            FROM users
            WHERE id = %s
        """, (
            user_id,
        ))


        user = cursor.fetchone()


        if not user:

            flash(
                "User not found.",
                "danger"
            )

            return redirect("/admin")


        if user["role"] == "admin":

            flash(
                "Admin accounts cannot be deleted.",
                "danger"
            )

            return redirect("/admin")


        cursor.execute("""
            UPDATE auctions
            SET winner_id = NULL
            WHERE winner_id = %s
        """, (
            user_id,
        ))


        cursor.execute("""
            DELETE FROM bids
            WHERE bidder_id = %s
        """, (
            user_id,
        ))


        cursor.execute("""
            SELECT id
            FROM auctions
            WHERE seller_id = %s
        """, (
            user_id,
        ))


        seller_auctions = cursor.fetchall()


        for auction in seller_auctions:

            auction_id = auction["id"]


            cursor.execute("""
                DELETE FROM bids
                WHERE auction_id = %s
            """, (
                auction_id,
            ))


            cursor.execute("""
                DELETE FROM auctions
                WHERE id = %s
            """, (
                auction_id,
            ))


        cursor.execute("""
            DELETE FROM users
            WHERE id = %s
        """, (
            user_id,
        ))


        db.commit()


    except mysql.connector.Error as error:

        if db:
            db.rollback()

        flash(
            "Could not delete user: " + str(error),
            "danger"
        )

        return redirect("/admin")


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    flash(
        "User removed successfully.",
        "success"
    )

    return redirect("/admin")


# =========================================================
# ADMIN - DELETE AUCTION
# =========================================================

@app.route(
    "/admin/delete-auction/<int:auction_id>",
    methods=["POST"]
)
def admin_delete_auction(auction_id):

    if not admin_required():

        return "Access denied.", 403


    db = None
    cursor = None

    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True,
            buffered=True
        )


        cursor.execute("""
            SELECT *
            FROM auctions
            WHERE id = %s
        """, (
            auction_id,
        ))


        auction = cursor.fetchone()


        if not auction:

            flash(
                "Auction not found.",
                "danger"
            )

            return redirect("/admin")


        cursor.execute("""
            DELETE FROM bids
            WHERE auction_id = %s
        """, (
            auction_id,
        ))


        cursor.execute("""
            DELETE FROM auctions
            WHERE id = %s
        """, (
            auction_id,
        ))


        db.commit()


        image_name = auction.get(
            "product_image"
        )


        if image_name:

            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_name
            )


            if os.path.exists(image_path):

                try:
                    os.remove(image_path)
                except OSError:
                    pass


    except mysql.connector.Error as error:

        if db:
            db.rollback()

        flash(
            "Could not delete auction: " + str(error),
            "danger"
        )

        return redirect("/admin")


    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


    flash(
        "Auction removed successfully.",
        "success"
    )

    return redirect("/admin")


# =========================================================
# TEST DATABASE
# =========================================================

@app.route("/test-db")
def test_db():

    db = None

    try:

        db = get_db()

        return "MySQL connection successful!"

    except mysql.connector.Error as error:

        return (
            "MySQL connection failed: "
            + str(error)
        ), 500

    finally:

        if db:
            db.close()


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )