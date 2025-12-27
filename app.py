from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def init_db(db_path):
    """ Initialize database tables if they don't exist """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    # Create borrowers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS borrowers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            number_phone TEXT NOT NULL,
            total_amount REAL NOT NULL,
            notes TEXT
        )
    ''')

    # Create payments table
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            borrower_id INTEGER NOT NULL,
            amount_paid REAL NOT NULL,
            payment_date TEXT NOT NULL,
            device_description TEXT,
            device_image TEXT,
            FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
        )
    ''')

    # Create devices table
    c.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            borrower_id INTEGER NOT NULL,
            device_description TEXT,
            device_image TEXT,
            device_date TEXT,
            device_amount REAL,
            FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
        )
    ''')

    # Check if admin user exists, if not create it
    c.execute('SELECT id FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash("123456")
        c.execute('INSERT INTO users (email, username, password) VALUES (?, ?, ?)',
                  ("admin@example.com", "admin", hashed_password))

    conn.commit()
    conn.close()

def get_db_path():
    """ Get database path that works in both development and PyInstaller environments """
    # Check if we're running from PyInstaller
    if hasattr(sys, '_MEIPASS'):
        # Running from PyInstaller exe - use user-writable AppData directory
        appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'LoanManagementSystem')
        if not os.path.exists(appdata_dir):
            os.makedirs(appdata_dir)
        db_path = os.path.join(appdata_dir, 'users.db')

        # If database doesn't exist, copy from bundled resources
        bundled_db = resource_path('users.db')
        if os.path.exists(bundled_db) and not os.path.exists(db_path):
            import shutil
            shutil.copy2(bundled_db, db_path)

        # Initialize database tables if missing
        init_db(db_path)

        return db_path
    else:
        # Development mode - use current directory
        db_path = os.path.join(os.path.abspath("."), 'users.db')
        init_db(db_path)
        return db_path

app = Flask(__name__,
            template_folder=resource_path('templates'),
            static_folder=resource_path('static'))
app.secret_key = 'your_secret_key_here'  # Needed for session management

# Custom Jinja2 filter to format numbers with commas
def format_number_with_commas(value):
    try:
        return "{:,.0f}".format(float(value))
    except (ValueError, TypeError):
        return value

app.jinja_env.filters['format_number'] = format_number_with_commas

# Configure upload folder
def get_upload_folder():
    """ Get upload folder path that works in both development and PyInstaller environments """
    # Check if we're running from PyInstaller
    if hasattr(sys, '_MEIPASS'):
        # Running from PyInstaller exe - use user-writable directory
        # Use AppData directory which is always writable for users
        appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'LoanManagementSystem')
        upload_dir = os.path.join(appdata_dir, 'uploads')

        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)

        return upload_dir
    else:
        # Development mode - use current directory
        upload_dir = 'static/uploads'
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        return upload_dir

UPLOAD_FOLDER = get_upload_folder()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/login', methods=['GET', 'POST'])
def login():
    username_error = ''
    password_error = ''
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username:
            username_error = 'يرجى إدخال اسم المستخدم'
        if not password:
            password_error = 'يرجى إدخال كلمة المرور'

        if not username_error and not password_error:
            try:
                db_path = get_db_path()
                print(f"Database path: {db_path}")  # Debug logging
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute('SELECT email, password FROM users WHERE username = ?', (username,))
                user = c.fetchone()
                conn.close()
                if user and check_password_hash(user[1], password):
                    session['email'] = user[0]  # Store email in session for other operations
                    return redirect(url_for('dashboard'))
                else:
                    password_error = 'اسم المستخدم أو كلمة المرور غير صحيحة'
            except Exception as e:
                print(f"Database error: {e}")  # Debug logging
                password_error = f'خطأ في قاعدة البيانات: {str(e)}'

    return render_template('login.html', username_error=username_error, password_error=password_error)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    error = ''
    message = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        new_username = request.form.get('new_username', '').strip()
        new_password = request.form.get('new_password', '').strip()

        if not email:
            error = 'يرجى إدخال البريد الإلكتروني.'
        else:
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            c.execute('SELECT id, username FROM users WHERE email = ?', (email,))
            user = c.fetchone()
            if user:
                try:
                    if new_username and new_password:
                        # Check if new username already exists
                        c.execute('SELECT id FROM users WHERE username = ? AND email != ?', (new_username, email))
                        if c.fetchone():
                            error = 'اسم المستخدم الجديد مستخدم بالفعل. يرجى اختيار اسم آخر.'
                        else:
                            hashed_password = generate_password_hash(new_password)
                            c.execute('UPDATE users SET username = ?, password = ? WHERE id = ?', (new_username, hashed_password, user[0]))
                    elif new_username:
                        # Check if new username already exists
                        c.execute('SELECT id FROM users WHERE username = ? AND email != ?', (new_username, email))
                        if c.fetchone():
                            error = 'اسم المستخدم الجديد مستخدم بالفعل. يرجى اختيار اسم آخر.'
                        else:
                            c.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user[0]))
                    elif new_password:
                        hashed_password = generate_password_hash(new_password)
                        c.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user[0]))
                    else:
                        error = 'يرجى إدخال اسم المستخدم أو كلمة المرور الجديدة لتحديثها.'
                    if not error:
                        conn.commit()
                        message = 'تم تحديث البيانات بنجاح.'
                except sqlite3.IntegrityError:
                    error = 'حدث خطأ أثناء تحديث البيانات.'
            else:
                error = 'البريد الإلكتروني غير موجود في النظام.'
            conn.close()

    return render_template('forgot_password.html', error=error, message=message)

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fetch borrowers with loan_date
    c.execute('SELECT * FROM borrowers')
    borrowers = c.fetchall()

    # Fetch device info for each borrower
    devices = {}
    for borrower in borrowers:
        c.execute('SELECT * FROM devices WHERE borrower_id = ? ORDER BY device_date DESC LIMIT 1', (borrower['id'],))
        device = c.fetchone()
        devices[borrower['id']] = device

    # Calculate total loans, total paid, and remaining
    c.execute('SELECT SUM(total_amount) as total_loans FROM borrowers')
    total_loans_row = c.fetchone()
    total_loans = total_loans_row['total_loans'] if total_loans_row['total_loans'] else 0

    c.execute('SELECT SUM(amount_paid) as total_paid FROM payments')
    total_paid_row = c.fetchone()
    total_paid = total_paid_row['total_paid'] if total_paid_row['total_paid'] else 0

    total_remaining = total_loans - total_paid

    # Payments grouped by borrower
    c.execute('SELECT borrower_id, SUM(amount_paid) as total_paid FROM payments GROUP BY borrower_id')
    payments_data = c.fetchall()
    payments = {row['borrower_id']: row['total_paid'] for row in payments_data}

    conn.close()

    return render_template('modern_dashboard.html', borrowers=borrowers, devices=devices, payments=payments,
                           total_loans=total_loans, total_paid=total_paid, total_remaining=total_remaining)

@app.route('/check_name')
def check_name():
    name = request.args.get('name', '').strip()
    borrower_id = request.args.get('borrower_id', '').strip()
    if not name:
        return jsonify({'exists': False})

    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    if borrower_id:
        c.execute('SELECT id FROM borrowers WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) AND id != ?', (name, borrower_id))
    else:
        c.execute('SELECT id FROM borrowers WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))', (name,))
    exists = c.fetchone() is not None
    conn.close()
    return jsonify({'exists': exists})

@app.route('/add_loan', methods=['GET', 'POST'])
def add_loan():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        # Fetch existing borrowers for the datalist
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT name FROM borrowers ORDER BY name')
        borrowers = c.fetchall()
        conn.close()

        today = datetime.now().strftime('%Y-%m-%d')
        return render_template('add_loan.html', borrowers=borrowers, today=today)
    
    # POST method handling
    name = request.form.get('name', '').strip()
    number_phone = request.form.get('number_phone', '').strip()
    total_amount = request.form.get('total_amount', '').strip()
    total_amount_clean = total_amount.replace(',', '')
    notes = request.form.get('notes', '').strip()
    device_description = request.form.get('device_description', '').strip()
    loan_date = request.form.get('loan_date', '').strip()
    device_image = request.files.get('device_image')

    name_error = ''
    if not name or not number_phone or not total_amount:
        name_error = 'يرجى ملء جميع الحقول المطلوبة'

    # Check if name already exists (case-insensitive)
    if not name_error:
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute('SELECT id FROM borrowers WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))', (name,))
        existing_borrower = c.fetchone()
        conn.close()

        if existing_borrower:
            name_error = 'هذا الاسم متكرر'

    if name_error:
        # Fetch existing borrowers for the datalist
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT name FROM borrowers ORDER BY name')
        borrowers = c.fetchall()
        conn.close()

        today = datetime.now().strftime('%Y-%m-%d')
        return render_template('add_loan.html', borrowers=borrowers, today=today, name=name, number_phone=number_phone, total_amount=total_amount, notes=notes, device_description=device_description, loan_date=loan_date, name_error=name_error)

    image_filename = None
    if device_image and device_image.filename != '':
        filename = secure_filename(device_image.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        device_image.save(image_path)
        image_filename = filename

    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    # Insert borrower
    c.execute('INSERT INTO borrowers (name, number_phone, total_amount, notes) VALUES (?, ?, ?, ?)',
              (name, number_phone, float(total_amount_clean), notes))
    borrower_id = c.lastrowid

    # Insert initial device info with individual loan amount
    if device_description or image_filename or loan_date:
        if not loan_date:
            loan_date = datetime.now().strftime('%Y-%m-%d')
        amount = 0
        try:
            amount = float(total_amount_clean)
        except (ValueError, TypeError):
            amount = 0
        c.execute('INSERT INTO devices (borrower_id, device_description, device_image, device_date, device_amount) VALUES (?, ?, ?, ?, ?)',
                  (borrower_id, device_description, image_filename, loan_date, amount))

    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

@app.route('/add_payment', methods=['GET', 'POST'])
def add_payment():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        # Fetch borrowers for the dropdown
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM borrowers')
        borrowers = c.fetchall()

        # Calculate remaining amounts for each borrower
        remaining_amounts = {}
        for borrower in borrowers:
            c.execute('SELECT SUM(amount_paid) as total_paid FROM payments WHERE borrower_id = ?', (borrower['id'],))
            total_paid_row = c.fetchone()
            total_paid = total_paid_row['total_paid'] if total_paid_row and total_paid_row['total_paid'] is not None else 0
            remaining_amounts[borrower['name']] = borrower['total_amount'] - total_paid

        conn.close()

        today = datetime.now().strftime('%Y-%m-%d')
        return render_template('add_payment.html', borrowers=borrowers, remaining_amounts=remaining_amounts, today=today)

    # POST method handling
    borrower_name = request.form.get('borrower_name', '').strip()
    amount_paid = request.form.get('amount_paid', '').strip()
    amount_paid_clean = amount_paid.replace(',', '')
    payment_date = request.form.get('payment_date', '').strip()

    if not borrower_name or not amount_paid or not payment_date:
        flash('يرجى ملء جميع الحقول المطلوبة', 'error')
        return redirect(url_for('add_payment'))

    # Look up borrower_id by name
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id FROM borrowers WHERE name = ?', (borrower_name,))
    borrower = c.fetchone()
    if not borrower:
        flash('الاسم غير موجود في النظام', 'error')
        conn.close()
        return redirect(url_for('add_payment'))

    borrower_id = borrower['id']

    # Calculate remaining amount for this borrower
    c.execute('SELECT SUM(amount_paid) as total_paid FROM payments WHERE borrower_id = ?', (borrower_id,))
    total_paid_row = c.fetchone()
    total_paid = total_paid_row['total_paid'] if total_paid_row and total_paid_row['total_paid'] is not None else 0

    c.execute('SELECT total_amount FROM borrowers WHERE id = ?', (borrower_id,))
    borrower_row = c.fetchone()
    total_amount = borrower_row['total_amount'] if borrower_row else 0

    remaining_amount = total_amount - total_paid

    # Check if borrower is already fully paid
    if remaining_amount <= 0:
        flash('هذا الشخص مسدد - لا يوجد مبلغ متبقي', 'error')
        conn.close()
        return redirect(url_for('add_payment'))

    # Validate that payment amount doesn't exceed remaining amount
    if float(amount_paid_clean) > remaining_amount:
        flash('اكثر', 'error')
        conn.close()
        return redirect(url_for('add_payment'))

    # If payment_date not provided, set to current date
    if not payment_date:
        payment_date = datetime.now().strftime('%Y-%m-%d')

    c.execute('INSERT INTO payments (borrower_id, amount_paid, payment_date) VALUES (?, ?, ?)',
              (int(borrower_id), float(amount_paid_clean), payment_date))
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

# Route to update borrower's total loan amount
@app.route('/update_loan', methods=['POST'])
def update_loan():
    if 'email' not in session:
        return redirect(url_for('login'))

    borrower_id = request.form.get('id', '').strip()
    additional_amount = request.form.get('additional_amount', '').strip()
    additional_amount_clean = additional_amount.replace(',', '')
    loan_date = request.form.get('loan_date', '').strip()
    device_description = request.form.get('device_description', '').strip()
    device_image = request.files.get('device_image')

    if not borrower_id or not additional_amount:
        flash('يرجى ملء جميع الحقول', 'error')
        return redirect(url_for('dashboard'))

    try:
        additional_amount = float(additional_amount_clean)
        if additional_amount <= 0:
            flash('⚠️ المبلغ يجب أن يكون أكبر من صفر', 'error')
            return redirect(url_for('dashboard'))
            
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()

        # Update the loan amount
        c.execute('UPDATE borrowers SET total_amount = total_amount + ? WHERE id = ?', (additional_amount, int(borrower_id)))
        
        # Insert device details for this new loan
        image_filename = None
        if device_image and device_image.filename != '':
            filename = secure_filename(device_image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            device_image.save(image_path)
            image_filename = filename
        
        if not loan_date:
            loan_date = datetime.now().strftime('%Y-%m-%d')
            
        c.execute('INSERT INTO devices (borrower_id, device_description, device_image, device_date, device_amount) VALUES (?, ?, ?, ?, ?)',
                  (int(borrower_id), device_description, image_filename, loan_date, additional_amount))
        
        conn.commit()
        conn.close()
    except ValueError:
        flash('يرجى إدخال مبلغ صحيح', 'error')
        return redirect(url_for('dashboard'))

    return redirect(url_for('edit_borrower', borrower_id=int(borrower_id)))

# Route to delete a borrower
@app.route('/delete_borrower', methods=['POST'])
def delete_borrower():
    if 'email' not in session:
        return redirect(url_for('login'))

    borrower_id = request.form.get('id', '').strip()
    if not borrower_id:
        flash('لم يتم تحديد الشخص', 'error')
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    # Delete payments related to borrower
    c.execute('DELETE FROM payments WHERE borrower_id = ?', (int(borrower_id),))
    # Delete borrower
    c.execute('DELETE FROM borrowers WHERE id = ?', (int(borrower_id),))
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

# Route to delete a payment
@app.route('/delete_payment', methods=['POST'])
def delete_payment():
    if 'email' not in session:
        return redirect(url_for('login'))

    payment_id = request.form.get('id', '').strip()
    if not payment_id:
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('DELETE FROM payments WHERE id = ?', (int(payment_id),))
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

# Route to edit borrower details (GET and POST)
@app.route('/edit_borrower/<int:borrower_id>', methods=['GET', 'POST'])
def edit_borrower(borrower_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        number_phone = request.form.get('number_phone', '').strip()
        total_amount = request.form.get('total_amount', '').strip()
        total_amount_clean = total_amount.replace(',', '')
        notes = request.form.get('notes', '').strip()

        name_error = ''
        if not name or not number_phone or not total_amount:
            name_error = 'يرجى ملء جميع الحقول المطلوبة'

        # Check if name already exists (case-insensitive), but allow same borrower
        if not name_error:
            c.execute('SELECT id FROM borrowers WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) AND id != ?', (name, borrower_id))
            existing_borrower = c.fetchone()
            if existing_borrower:
                name_error = 'هذا الاسم متكرر'

        if name_error:
            # Re-fetch borrower data
            c.execute('SELECT * FROM borrowers WHERE id = ?', (borrower_id,))
            borrower = c.fetchone()
            conn.close()
            today = datetime.now().strftime('%Y-%m-%d')
            return render_template('edit_borrower.html', borrower=borrower, today=today, name_error=name_error)

        c.execute('UPDATE borrowers SET name = ?, number_phone = ?, total_amount = ?, notes = ? WHERE id = ?',
                  (name, number_phone, float(total_amount_clean), notes, borrower_id))
        conn.commit()
        conn.close()
        return redirect(url_for('edit_borrower', borrower_id=borrower_id))

    c.execute('SELECT * FROM borrowers WHERE id = ?', (borrower_id,))
    borrower = c.fetchone()
    conn.close()

    if borrower is None:
        return redirect(url_for('dashboard'))

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('edit_borrower.html', borrower=borrower, today=today)

# Route to edit payment details (GET and POST)
@app.route('/edit_payment/<int:payment_id>', methods=['GET', 'POST'])
def edit_payment(payment_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if request.method == 'POST':
        amount_paid = request.form.get('amount_paid', '').strip()
        amount_paid_clean = amount_paid.replace(',', '')
        payment_date = request.form.get('payment_date', '').strip()
        device_description = request.form.get('device_description', '').strip()
        device_image = request.files.get('device_image')

        if not amount_paid or not payment_date:
            return redirect(url_for('dashboard'))

        image_filename = None
        if device_image and device_image.filename != '':
            filename = secure_filename(device_image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            device_image.save(image_path)
            image_filename = filename

            # Update with new image and other fields
            c.execute('UPDATE payments SET amount_paid = ?, payment_date = ?, device_image = ?, device_description = ? WHERE id = ?',
                      (float(amount_paid_clean), payment_date, image_filename, device_description, payment_id))
        else:
            # Update without changing image
            c.execute('UPDATE payments SET amount_paid = ?, payment_date = ?, device_description = ? WHERE id = ?',
                      (float(amount_paid_clean), payment_date, device_description, payment_id))

        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    c.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
    payment = c.fetchone()
    conn.close()

    if payment is None:
        return redirect(url_for('dashboard'))

    return render_template('edit_payment.html', payment=payment)

# Route to show loan details with payment history
@app.route('/loan_status/<int:borrower_id>')
def loan_status(borrower_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('SELECT * FROM borrowers WHERE id = ?', (borrower_id,))
    borrower = c.fetchone()

    c.execute('SELECT * FROM payments WHERE borrower_id = ? ORDER BY payment_date ASC', (borrower_id,))
    payments = c.fetchall()

    c.execute('SELECT SUM(amount_paid) as total_paid FROM payments WHERE borrower_id = ?', (borrower_id,))
    total_paid_row = c.fetchone()
    total_paid = total_paid_row['total_paid'] if total_paid_row['total_paid'] is not None else 0

    # Fetch device info for borrower
    c.execute('SELECT * FROM devices WHERE borrower_id = ? ORDER BY device_date DESC LIMIT 1', (borrower_id,))
    device = c.fetchone()

    conn.close()

    if borrower is None:
        return redirect(url_for('dashboard'))

    remaining = borrower['total_amount'] - total_paid

    return render_template('loan_status.html', borrower=borrower, payments=payments, total_paid=total_paid, remaining=remaining, device=device)

@app.route('/device_details/<int:borrower_id>')
def device_details(borrower_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('SELECT * FROM borrowers WHERE id = ?', (borrower_id,))
    borrower = c.fetchone()

    c.execute('SELECT * FROM devices WHERE borrower_id = ? ORDER BY device_date DESC', (borrower_id,))
    devices = c.fetchall()

    conn.close()

    if borrower is None:
        flash('العميل غير موجود', 'error')
        return redirect(url_for('dashboard'))

    return render_template('all_devices.html', borrower=borrower, devices=devices)

@app.route('/delete_device/<int:device_id>', methods=['POST'])
def delete_device(device_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get borrower_id before deleting the device
    c.execute('SELECT borrower_id, device_amount FROM devices WHERE id = ?', (device_id,))
    device = c.fetchone()

    if device:
        borrower_id = device['borrower_id']
        device_amount = device['device_amount'] or 0

        # Delete the device
        c.execute('DELETE FROM devices WHERE id = ?', (device_id,))

        # Update borrower's total amount by subtracting the deleted device amount
        c.execute('UPDATE borrowers SET total_amount = total_amount - ? WHERE id = ?', (device_amount, borrower_id))

        conn.commit()
    else:
        flash('❌ القرض غير موجود', 'error')

    conn.close()
    
    return redirect(url_for('device_details', borrower_id=borrower_id))

# Route to update user info (GET and POST)
@app.route('/update_user', methods=['GET', 'POST'])
def update_user():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    message = ''
    error = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Get current user
        c.execute('SELECT * FROM users WHERE email = ?', (session['email'],))
        current_user = c.fetchone()

        if not current_user:
            error = 'المستخدم غير موجود'
        else:
            # Email is required and cannot be empty
            if not email:
                error = 'البريد الإلكتروني مطلوب'
                conn.close()
                return render_template('update_user.html', user=current_user, message=message, error=error)

            # Check if email is provided and different from current
            if email and email != current_user['email']:
                # Check if new email already exists
                c.execute('SELECT * FROM users WHERE email = ?', (email,))
                existing_user = c.fetchone()
                if existing_user:
                    error = 'البريد الإلكتروني مستخدم بالفعل'
                    conn.close()
                    return render_template('update_user.html', user=current_user, message=message, error=error)

            # Check if username is provided and different from current
            if username and username != current_user['username']:
                # Check if new username already exists
                c.execute('SELECT * FROM users WHERE username = ?', (username,))
                existing_user = c.fetchone()
                if existing_user:
                    error = 'اسم المستخدم مستخدم بالفعل'
                    conn.close()
                    return render_template('update_user.html', user=current_user, message=message, error=error)

            # Update user information
            try:
                update_fields = []
                update_values = []

                if email and email != current_user['email']:
                    update_fields.append('email = ?')
                    update_values.append(email)

                if username and username != current_user['username']:
                    update_fields.append('username = ?')
                    update_values.append(username)

                if password:
                    from werkzeug.security import generate_password_hash
                    hashed_password = generate_password_hash(password)
                    update_fields.append('password = ?')
                    update_values.append(hashed_password)

                if update_fields:
                    update_values.append(current_user['id'])
                    c.execute('UPDATE users SET ' + ', '.join(update_fields) + ' WHERE id = ?', update_values)
                    conn.commit()
                    message = 'تم تحديث البيانات بنجاح'

                    # Update session if email was changed
                    if email and email != current_user['email']:
                        session['email'] = email
                else:
                    message = 'لم يتم إجراء أي تغييرات'
            except sqlite3.IntegrityError as e:
                error = 'حدث خطأ أثناء تحديث البيانات'
                conn.rollback()

    # Get current user data
    c.execute('SELECT * FROM users WHERE email = ?', (session['email'],))
    user = c.fetchone()
    conn.close()

    return render_template('update_user.html', user=user, message=message, error=error)

if __name__ == '__main__':
    app.run(debug=True)
