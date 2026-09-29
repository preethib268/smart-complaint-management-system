import os
import json
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from dotenv import load_dotenv
from google import genai
from google.genai import types
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pymysql

# ---------------------------------------------------------------------------
# App configuration and setup
# ---------------------------------------------------------------------------

# Load the API key from .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)
app.secret_key = "change-this-to-any-long-random-string-12345"

# File upload settings
UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB max file size

# Create the Gemini client once, when the app starts
ai_client = genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_db_connection():
    return pymysql.connect(
    host=os.getenv('MYSQLHOST', 'localhost'),
    user=os.getenv('MYSQLUSER', 'root'),
    password=os.getenv('MYSQLPASSWORD', ''),
    database=os.getenv('MYSQLDATABASE', 'complaint_system'),
    port=int(os.getenv('MYSQLPORT', 3306)),
    ssl={"ssl": {}}
)


# Check if a file's extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Send a complaint to the AI and return category, urgency, reply
def analyze_complaint(complaint_text):
    prompt = f"""
    You are a complaint-handling assistant for a college.
    Read the complaint below and do three things:
    1. Decide which department it should go to. Choose ONE from:
        IT, Hostel, Mess/Canteen, Examination, Academics, Library, Transport,
        Maintenance, Medical/Health, Counselling/Wellbeing, Accounts/Fees,
        Placement/Training, Sports/Gym, Security, Administration, Other.
    2. Decide the urgency. Choose ONE from: Low, Medium, High.
    3. Write a short, polite acknowledgement reply (2 sentences max) for the person.

    Complaint: "{complaint_text}"
    """

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "urgency": {"type": "string"},
                    "reply": {"type": "string"}
                },
                "required": ["category", "urgency", "reply"]
            }
        )
    )
    return json.loads(response.text)


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html')


# ---------------------------------------------------------------------------
# Authentication (register, login, logout)
# ---------------------------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        # Scramble (hash) the password before storing it
        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # Check if this email is already registered
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                existing = cursor.fetchone()

                if existing:
                    return render_template('register.html', error="This email is already registered.")

                # Save the new user (store the hash, never the real password)
                sql = "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)"
                cursor.execute(sql, (name, email, hashed_password))
            connection.commit()
        finally:
            connection.close()

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
        finally:
            connection.close()

        # Check the user exists AND the password matches the stored hash
        if user and check_password_hash(user["password_hash"], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid email or password.")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()   # forget the logged-in user
    return redirect(url_for('home'))


# ---------------------------------------------------------------------------
# User pages (profile, my complaints)
# ---------------------------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    message = None
    error = None

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                action = request.form.get('action')

                # --- Update name ---
                if action == 'update_name':
                    new_name = request.form['name']
                    cursor.execute("UPDATE users SET name = %s WHERE id = %s", (new_name, user_id))
                    connection.commit()
                    session['user_name'] = new_name  # keep the session in sync
                    message = "Name updated successfully."

                # --- Change password ---
                elif action == 'change_password':
                    current_password = request.form['current_password']
                    new_password = request.form['new_password']

                    cursor.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
                    user = cursor.fetchone()

                    if user and check_password_hash(user['password_hash'], current_password):
                        new_hash = generate_password_hash(new_password)
                        cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user_id))
                        connection.commit()
                        message = "Password changed successfully."
                    else:
                        error = "Your current password is incorrect."

            # Always fetch the latest profile info to show on the page
            cursor.execute("SELECT name, email, role FROM users WHERE id = %s", (user_id,))
            profile_data = cursor.fetchone()
    finally:
        connection.close()

    return render_template('profile.html', profile=profile_data, message=message, error=error)


@app.route('/my-complaints')
def my_complaints():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM complaints WHERE user_id = %s ORDER BY id DESC",
                (user_id,)
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    return render_template('my_complaints.html', complaints=rows)


# ---------------------------------------------------------------------------
# Complaint submission and viewing
# ---------------------------------------------------------------------------

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        complaint_text = request.form['complaint_text']

        # Ask the AI to analyze the complaint
        result = analyze_complaint(complaint_text)
        category = result['category']
        urgency = result['urgency']
        ai_reply = result['reply']

        user_id = session['user_id']

        # --- Handle optional file attachment ---
        attachment_filename = None
        file = request.files.get('attachment')
        if file and file.filename != '':
            if allowed_file(file.filename):
                # Make the filename safe, then give it a unique name to avoid overwrites
                safe_name = secure_filename(file.filename)
                unique_name = str(uuid.uuid4()) + "_" + safe_name
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                attachment_filename = unique_name
            else:
                return render_template('submit.html', error="Only PNG, JPG, JPEG, GIF, or PDF files are allowed.")

        # Save the complaint, including the attachment filename (or None)
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = """INSERT INTO complaints
                         (complaint_text, category, urgency, ai_reply, user_id, attachment)
                         VALUES (%s, %s, %s, %s, %s, %s)"""
                cursor.execute(sql, (complaint_text, category, urgency, ai_reply, user_id, attachment_filename))
            connection.commit()
        finally:
            connection.close()

        return redirect(url_for('thank_you'))

    return render_template('submit.html')


@app.route('/thank-you')
def thank_you():
    return render_template('thank_you.html')


@app.route('/complaint/<int:complaint_id>')
def complaint_detail(complaint_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM complaints WHERE id = %s", (complaint_id,))
            complaint = cursor.fetchone()
    finally:
        connection.close()

    if complaint is None:
        return "Complaint not found.", 404

    # Ownership check: staff can view any complaint; a user can view only their own.
    is_staff = session.get('user_role') == 'staff'
    is_owner = complaint['user_id'] == session['user_id']

    if not is_staff and not is_owner:
        return "Access denied. You can only view your own complaints.", 403

    return render_template('complaint_detail.html', complaint=complaint)


# Public list of all complaints (older page; not login-protected)
@app.route('/complaints')
def complaints():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM complaints ORDER BY id DESC")
            rows = cursor.fetchall()
    finally:
        connection.close()
    return render_template('complaints.html', complaints=rows)


# ---------------------------------------------------------------------------
# Staff pages (dashboard, status update, analytics)
# ---------------------------------------------------------------------------

@app.route('/dashboard')
def dashboard():
    # Must be logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Must be a staff account
    if session.get('user_role') != 'staff':
        return "Access denied. This page is for staff only.", 403

    # Read filter choices from the URL (empty = "All")
    filter_category = request.args.get('category', '')
    filter_urgency = request.args.get('urgency', '')
    filter_status = request.args.get('status', '')

    # Build the query piece by piece, safely
    query = "SELECT * FROM complaints WHERE 1=1"
    params = []

    if filter_category:
        query += " AND category = %s"
        params.append(filter_category)
    if filter_urgency:
        query += " AND urgency = %s"
        params.append(filter_urgency)
    if filter_status:
        query += " AND status = %s"
        params.append(filter_status)

    query += " ORDER BY id DESC"

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Summary counts (over ALL complaints, not just filtered)
            cursor.execute("SELECT status, COUNT(*) AS count FROM complaints GROUP BY status")
            status_rows = cursor.fetchall()
    finally:
        connection.close()

    counts = {"Open": 0, "In Progress": 0, "Resolved": 0}
    for row in status_rows:
        counts[row["status"]] = row["count"]

    total = len(rows)

    return render_template(
        'dashboard.html',
        complaints=rows,
        counts=counts,
        total=total,
        filter_category=filter_category,
        filter_urgency=filter_urgency,
        filter_status=filter_status
    )


@app.route('/update-status', methods=['POST'])
def update_status():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('user_role') != 'staff':
        return "Access denied. This page is for staff only.", 403

    complaint_id = request.form['complaint_id']
    new_status = request.form['status']

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE complaints SET status = %s WHERE id = %s"
            cursor.execute(sql, (new_status, complaint_id))
        connection.commit()
    finally:
        connection.close()

    return redirect(url_for('dashboard'))


@app.route('/analytics')
def analytics():
    # Staff only
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('user_role') != 'staff':
        return "Access denied. This page is for staff only.", 403

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT category, COUNT(*) AS count FROM complaints GROUP BY category")
            category_rows = cursor.fetchall()

            cursor.execute("SELECT urgency, COUNT(*) AS count FROM complaints GROUP BY urgency")
            urgency_rows = cursor.fetchall()

            cursor.execute("SELECT status, COUNT(*) AS count FROM complaints GROUP BY status")
            status_rows = cursor.fetchall()
    finally:
        connection.close()

    # Turn each result into two lists: labels and values. Skip None values.
    category_labels = [r["category"] for r in category_rows if r["category"] is not None]
    category_values = [r["count"] for r in category_rows if r["category"] is not None]

    urgency_labels = [r["urgency"] for r in urgency_rows if r["urgency"] is not None]
    urgency_values = [r["count"] for r in urgency_rows if r["urgency"] is not None]

    status_labels = [r["status"] for r in status_rows if r["status"] is not None]
    status_values = [r["count"] for r in status_rows if r["status"] is not None]

    return render_template(
        'analytics.html',
        category_labels=category_labels,
        category_values=category_values,
        urgency_labels=urgency_labels,
        urgency_values=urgency_values,
        status_labels=status_labels,
        status_values=status_values
    )
# ---------------------------------------------------------------------------
# Theme Setting
# ---------------------------------------------------------------------------
@app.route('/set-theme/<theme_name>')
def set_theme(theme_name):
    # Only allow the three known themes
    if theme_name in ('clean', 'modern', 'minimal'):
        session['theme'] = theme_name
    # Go back to the page the user came from, or home
    return redirect(request.referrer or url_for('home'))
# ---------------------------------------------------------------------------
# File serving (uploaded attachments)
# ---------------------------------------------------------------------------

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ---------------------------------------------------------------------------
# Run the app
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True)
else:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
