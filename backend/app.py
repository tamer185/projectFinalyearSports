from flask import Flask, request, jsonify, session
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from functools import wraps
import hashlib
import secrets
from datetime import datetime
import re

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:5500", "http://127.0.0.1:5500"])

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'taml7677',
    'database': 'SportsApplication'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Database error: {e}")
        return None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated

def is_admin():
    email = session.get('user_email')
    return email == 'tamernasr1717@gmail.com'

# ================================================================
# HOME ROUTE
# ================================================================

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'Sports Events API is running!',
        'status': 'online',
        'endpoints': [
            '/api/events',
            '/api/auth/register',
            '/api/auth/login',
            '/api/auth/session',
            '/api/admin/stats'
        ]
    })

# ================================================================
# AUTHENTICATION ROUTES
# ================================================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    is_google = data.get('isGoogle', False)

    if not name:
        return jsonify({'success': False, 'error': 'Name required'})
    if not email or not validate_email(email):
        return jsonify({'success': False, 'error': 'Valid email required'})
    if not is_google and len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be 6+ chars'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': 'email_exists'})

    hashed = hash_password(password) if not is_google else hash_password(f"google_{email}")
    cursor.execute(
        "INSERT INTO users (name, email, password, is_google) VALUES (%s, %s, %s, %s)",
        (name, email, hashed, is_google)
    )
    user_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    session['user_id'] = user_id
    session['user_name'] = name
    session['user_email'] = email

    return jsonify({'success': True, 'user': {'name': name, 'email': email, 'isGoogle': is_google}})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, email, password, is_google FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user or hash_password(password) != user['password']:
        return jsonify({'success': False, 'error': 'Invalid credentials'})

    session['user_id'] = user['id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']

    return jsonify({'success': True, 'user': {'name': user['name'], 'email': user['email'], 'isGoogle': user['is_google']}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/session', methods=['GET'])
def get_session():
    if session.get('user_id'):
        return jsonify({
            'success': True,
            'user': {
                'name': session['user_name'],
                'email': session['user_email']
            }
        })
    return jsonify({'success': False})

# ================================================================
# EVENTS ROUTES
# ================================================================

@app.route('/api/events', methods=['GET'])
def get_events():
    location = request.args.get('location', 'all')
    category = request.args.get('category', 'all')
    price_filter = request.args.get('price', 'all')

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed', 'events': []})

    cursor = conn.cursor(dictionary=True)
    
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    
    if location != 'all':
        query += " AND LOWER(location) = %s"
        params.append(location.lower())
    
    if category != 'all':
        query += " AND LOWER(category) = %s"
        params.append(category.lower())
    
    if price_filter == 'free':
        query += " AND price = 0"
    elif price_filter == 'budget':
        query += " AND price > 0 AND price <= 20"
    elif price_filter == 'moderate':
        query += " AND price > 20 AND price <= 50"
    elif price_filter == 'premium':
        query += " AND price > 50"
    
    try:
        cursor.execute(query, params)
        events = cursor.fetchall()
        
        # Get registration counts for each event
        for event in events:
            cursor.execute(
                "SELECT COUNT(*) as count FROM registrations WHERE event_id = %s AND status IN ('pending', 'approved')",
                (event['id'],)
            )
            reg_count = cursor.fetchone()
            event['registered'] = reg_count['count'] if reg_count else 0
    except Exception as e:
        print(f"Query error: {e}")
        events = []
    
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'events': events})

@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cursor.fetchone()
    
    if event:
        cursor.execute(
            "SELECT COUNT(*) as count FROM registrations WHERE event_id = %s AND status IN ('pending', 'approved')",
            (event_id,)
        )
        reg_count = cursor.fetchone()
        event['registered'] = reg_count['count'] if reg_count else 0
    
    cursor.close()
    conn.close()
    
    if event:
        return jsonify({'success': True, 'event': event})
    return jsonify({'success': False, 'error': 'Event not found'}), 404

# ================================================================
# REGISTRATION ROUTES
# ================================================================

def generate_registration_id():
    import random
    import string
    timestamp = datetime.now().strftime('%y%m%d%H%M%S')
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"REG{timestamp}{random_str}"

@app.route('/api/registrations', methods=['POST'])
@login_required
def create_registration():
    data = request.json
    event_id = data.get('eventId')
    user_id = session['user_id']
    user_name = session['user_name']
    user_email = session['user_email']
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    
    # Check if already registered
    cursor.execute(
        "SELECT id, status FROM registrations WHERE event_id = %s AND user_id = %s",
        (event_id, user_id)
    )
    existing = cursor.fetchone()
    
    if existing:
        if existing['status'] == 'cancelled':
            registration_id = generate_registration_id()
            cursor.execute(
                """UPDATE registrations SET 
                   registration_id = %s, status = 'pending', registration_date = %s,
                   approved_date = NULL, rejected_date = NULL
                   WHERE event_id = %s AND user_id = %s""",
                (registration_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), event_id, user_id)
            )
        else:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Already registered'})
    else:
        registration_id = generate_registration_id()
        cursor.execute(
            """INSERT INTO registrations 
               (registration_id, event_id, user_id, user_name, user_email, registration_date, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'pending')""",
            (registration_id, event_id, user_id, user_name, user_email, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
    
    conn.commit()
    
    # Update event registered count
    cursor.execute(
        "UPDATE events SET registered = (SELECT COUNT(*) FROM registrations WHERE event_id = %s AND status IN ('pending', 'approved')) WHERE id = %s",
        (event_id, event_id)
    )
    conn.commit()
    
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'registrationId': registration_id})

@app.route('/api/registrations/user', methods=['GET'])
@login_required
def get_user_registrations():
    user_id = session['user_id']
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT r.*, e.title, e.location, e.event_date, e.event_time, e.image_url, e.venue, e.exact_location, e.price, e.price_display
           FROM registrations r
           JOIN events e ON r.event_id = e.id
           WHERE r.user_id = %s
           ORDER BY r.created_at DESC""",
        (user_id,)
    )
    registrations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'registrations': registrations})

# ================================================================
# ADMIN ROUTES
# ================================================================

@app.route('/api/admin/stats', methods=['GET'])
@login_required
def get_admin_stats():
    if not is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM events")
    total_events = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as count FROM registrations WHERE status = 'pending'")
    pending = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as count FROM registrations WHERE status = 'approved'")
    approved = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as count FROM registrations WHERE status = 'rejected'")
    rejected = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'success': True,
        'stats': {
            'totalEvents': total_events['count'] if total_events else 0,
            'pendingRegistrations': pending['count'] if pending else 0,
            'approvedRegistrations': approved['count'] if approved else 0,
            'rejectedRegistrations': rejected['count'] if rejected else 0
        }
    })

@app.route('/api/admin/registrations/pending', methods=['GET'])
@login_required
def get_pending_registrations():
    if not is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT r.*, e.title as event_title, e.location, e.event_date, e.price, e.price_display
           FROM registrations r
           JOIN events e ON r.event_id = e.id
           WHERE r.status = 'pending'
           ORDER BY r.created_at ASC"""
    )
    pending = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'pending': pending})

@app.route('/api/admin/registrations/all', methods=['GET'])
@login_required
def get_all_registrations():
    if not is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT r.*, e.title as event_title, e.location, e.event_date, e.price, e.price_display
           FROM registrations r
           JOIN events e ON r.event_id = e.id
           ORDER BY r.created_at DESC"""
    )
    all_regs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'registrations': all_regs})

@app.route('/api/admin/registrations/<registration_id>/approve', methods=['PUT'])
@login_required
def approve_registration(registration_id):
    if not is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """UPDATE registrations 
           SET status = 'approved', approved_date = %s 
           WHERE registration_id = %s""",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), registration_id)
    )
    
    cursor.execute("SELECT event_id FROM registrations WHERE registration_id = %s", (registration_id,))
    reg = cursor.fetchone()
    
    if reg:
        cursor.execute(
            "UPDATE events SET registered = (SELECT COUNT(*) FROM registrations WHERE event_id = %s AND status IN ('pending', 'approved')) WHERE id = %s",
            (reg['event_id'], reg['event_id'])
        )
    
    cursor.execute(
        """INSERT INTO notifications (user_id, event_id, status, notification_date)
           SELECT user_id, event_id, 'approved', %s FROM registrations WHERE registration_id = %s""",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), registration_id)
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/admin/registrations/<registration_id>/reject', methods=['PUT'])
@login_required
def reject_registration(registration_id):
    if not is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed'})
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """UPDATE registrations 
           SET status = 'rejected', rejected_date = %s 
           WHERE registration_id = %s""",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), registration_id)
    )
    
    cursor.execute("SELECT event_id FROM registrations WHERE registration_id = %s", (registration_id,))
    reg = cursor.fetchone()
    
    if reg:
        cursor.execute(
            "UPDATE events SET registered = (SELECT COUNT(*) FROM registrations WHERE event_id = %s AND status IN ('pending', 'approved')) WHERE id = %s",
            (reg['event_id'], reg['event_id'])
        )
    
    cursor.execute(
        """INSERT INTO notifications (user_id, event_id, status, notification_date)
           SELECT user_id, event_id, 'rejected', %s FROM registrations WHERE registration_id = %s""",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), registration_id)
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True})

# ================================================================
# RUN SERVER
# ================================================================

if __name__ == '__main__':
    print("=" * 50)
    print("Sports Events API Server")
    print("=" * 50)
    print(f"Server running at: http://127.0.0.1:5000")
    print(f"Test the API at: http://127.0.0.1:5000/api/events")
    print("=" * 50)
    app.run(debug=True, port=5000)