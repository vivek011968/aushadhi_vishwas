import sqlite3
import os
import psycopg2
from psycopg2.extras import DictCursor
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from datetime import datetime
import socket
import hashlib
import io
import csv
from werkzeug.security import generate_password_hash, check_password_hash

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def generate_hash(data_str):
    return hashlib.sha256(data_str.encode()).hexdigest()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_health_key')

# On Vercel, the filesystem is read-only, so we must use /tmp for the database
# If a DATABASE_URL is found, we use Supabase (PostgreSQL)
DATABASE_URL = os.environ.get('DATABASE_URL')
if os.environ.get('VERCEL_URL') and not DATABASE_URL:
    DB_FILE = '/tmp/database.db'
else:
    DB_FILE = 'database.db'

def get_base_url():
    # If on Vercel, use the provided environment variable
    if os.environ.get('VERCEL_URL'):
        return f"https://{os.environ.get('VERCEL_URL')}/"
    # Fallback to local network IP for demo if available
    local_ip = get_local_ip()
    return f"http://{local_ip}:5000/"

# --- UNIFIED DATABASE HANDLER (SQLite <-> Postgres) ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        # Sanitize for SQLAlchemy/psycopg2 compatibility if needed (postgres -> postgresql)
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        # PostgreSQL (Supabase)
        conn = psycopg2.connect(db_url)
        return conn
    else:
        # Local SQLite
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def db_execute(query, params=(), commit=False, fetch="none"):
    """Handles both SQLite (?) and Postgres (%s) syntax variations"""
    db_url = os.environ.get('DATABASE_URL')
    is_postgres = True if db_url else False
    
    # Simple syntax translation: SQLite ? -> Postgres %s
    if is_postgres:
        query = query.replace('?', '%s')
        # PostgreSQL doesn't support "INSERT OR IGNORE" directly - convert simple cases
        if "INSERT OR IGNORE" in query:
            # Note: This requires the table to have a unique constraint/primary key being hit
            # We handle common cases here; complex ones should be handled manually
            query = query.replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT DO NOTHING"
        # Removed broken generic "INSERT OR REPLACE" -> Postgres translation (requires SET clause)

    conn = get_db_connection()
    try:
        if is_postgres:
            cur = conn.cursor(cursor_factory=DictCursor)
        else:
            cur = conn.cursor()
            
        cur.execute(query, params)
        
        result = None
        if fetch == "all":
            result = cur.fetchall()
        elif fetch == "one":
            result = cur.fetchone()
            
        if commit:
            conn.commit()
        return result
    except Exception as e:
        print(f"DATABASE ERROR: {e}")
        print(f"QUERY: {query}")
        print(f"PARAMS: {params}")
        try:
            conn.rollback()
        except:
            pass
        raise e
    finally:
        conn.close()

def init_db():
    db_url = os.environ.get('DATABASE_URL')
    is_postgres = True if db_url else False
    pk_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    text_type = "TEXT"
    
    # SQL logic for both
    # Users (Admin) table
    db_execute(f'''CREATE TABLE IF NOT EXISTS users (
                    id {pk_type},
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                 )''', commit=True)
                 
    # Admin default login
    admin_pass = generate_password_hash('admin123')
    if is_postgres:
        db_execute("INSERT INTO users (username, password) VALUES ('admin', %s) ON CONFLICT (username) DO NOTHING", (admin_pass,), commit=True)
    else:
        db_execute("INSERT OR IGNORE INTO users (username, password) VALUES ('admin', ?)", (admin_pass,), commit=True)
        db_execute("UPDATE users SET password = ? WHERE username = 'admin'", (admin_pass,), commit=True)
    
    # Create other tables
    tables = [
        f'''CREATE TABLE IF NOT EXISTS medicines (
                    id {pk_type},
                    name TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    batch_number TEXT NOT NULL,
                    mfg_date TEXT NOT NULL,
                    exp_date TEXT NOT NULL,
                    distributor TEXT NOT NULL,
                    qr_code_id TEXT UNIQUE NOT NULL
                 )''',
        f'''CREATE TABLE IF NOT EXISTS supply_chain (
                    id {pk_type},
                    qr_code_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    location TEXT,
                    timestamp TEXT NOT NULL,
                    previous_hash TEXT,
                    current_hash TEXT
                 )''',
        f'''CREATE TABLE IF NOT EXISTS scan_logs (
                    id {pk_type},
                    qr_code_id TEXT NOT NULL,
                    location TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    result TEXT NOT NULL,
                    scanner_type TEXT NOT NULL
                 )''',
        f'''CREATE TABLE IF NOT EXISTS complaints (
                    id {pk_type},
                    medicine_name TEXT,
                    batch_number TEXT,
                    location TEXT,
                    description TEXT,
                    timestamp TEXT NOT NULL
                 )''',
        f'''CREATE TABLE IF NOT EXISTS fake_alerts (
                    id {pk_type},
                    qr_code_id TEXT NOT NULL,
                    location TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                 )''',
        f'''CREATE TABLE IF NOT EXISTS blacklisted_qrs (
                    id {pk_type},
                    qr_code_id TEXT UNIQUE NOT NULL,
                    reason TEXT,
                    timestamp TEXT NOT NULL
                 )''',
        f'''CREATE TABLE IF NOT EXISTS global_medicines (
                    id {pk_type},
                    qr_code_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    batch_number TEXT NOT NULL,
                    mfg_date TEXT NOT NULL,
                    exp_date TEXT NOT NULL,
                    distributor TEXT NOT NULL,
                    trust_source TEXT NOT NULL
                 )'''
    ]
    
    for t in tables:
        db_execute(t, commit=True)

    # Performance Indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_med_qr ON medicines(qr_code_id)",
        "CREATE INDEX IF NOT EXISTS idx_global_qr ON global_medicines(qr_code_id)",
        "CREATE INDEX IF NOT EXISTS idx_scan_qr ON scan_logs(qr_code_id)",
        "CREATE INDEX IF NOT EXISTS idx_supply_qr ON supply_chain(qr_code_id)"
    ]
    for idx in indexes:
        try:
            db_execute(idx, commit=True)
        except:
            pass # Index might already exist

    # Global Seeds
    seeds = [
        ("https://sun.psverify.com/21/G2KTDMHK5", "Rosuvas 10mg", "Sun Pharma", "G2KTDMHK5", "2024-01-01", "2027-12-31", "Global Health Dist", "Government Verified / Sun Pharma portal"),
        ("QR-EXTERNAL-DRUG-001", "Generic Paracetamol", "HealthCorp Global", "B-9988", "2024-05-10", "2026-05-10", "Express Dist", "WHO Trusted List"),
        ("https://pfizer.verify/P12345", "Pfizer Vaccine", "Pfizer", "P12345", "2024-01-01", "2026-01-01", "Universal Health", "Pfizer Official Port"),
        ("https://gsk.verify/G6789", "Augmentin", "GSK", "G6789", "2024-02-15", "2026-02-15", "GSK Supply Chain", "GSK Trust Portal"),
        ("https://novartis.verify/V9988", "Voltaren", "Novartis", "V9988", "2024-04-10", "2027-04-10", "Novartis Global", "Novartis Secure Portal"),
        ("QR-ABBOTT-DRUG-555", "Ensure", "Abbott", "AB-555", "2024-03-20", "2025-03-20", "Apollo Pharmacy", "Abbott Direct")
    ]
    
    for s in seeds:
        if is_postgres:
            db_execute("INSERT INTO global_medicines (qr_code_id, name, manufacturer, batch_number, mfg_date, exp_date, distributor, trust_source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (qr_code_id) DO NOTHING", s, commit=True)
        else:
            db_execute("INSERT OR IGNORE INTO global_medicines (qr_code_id, name, manufacturer, batch_number, mfg_date, exp_date, distributor, trust_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", s, commit=True)

# Initialize DB on startup (wrapped to prevent crash if DB unreachable)
try:
    init_db()
except Exception as e:
    print(f"DATABASE INITIALIZATION FAILED: {e}")

# === ROUTES for Templates ===

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/scanner')
def scanner():
    return render_template('scanner.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = db_execute("SELECT * FROM users WHERE username = ?", (username,), fetch="one")
        
        if user and check_password_hash(user['password'], password):
            session['admin'] = True
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    total_meds = db_execute('SELECT COUNT(*) FROM medicines', fetch="one")[0]
    total_scans = db_execute('SELECT COUNT(*) FROM scan_logs', fetch="one")[0]
    fake_alerts = db_execute('SELECT COUNT(*) FROM fake_alerts', fetch="one")[0]
    total_complaints = db_execute('SELECT COUNT(*) FROM complaints', fetch="one")[0]
    
    # Count unique unknown scans for pending registration
    unknown_scans = db_execute("SELECT COUNT(DISTINCT qr_code_id) FROM scan_logs WHERE result = 'Unknown'", fetch="one")[0]
    
    recent_scans = db_execute('SELECT * FROM scan_logs ORDER BY id DESC LIMIT 5', fetch="all")
    
    # Timeline Data (Last 7 days of scans)
    timeline_query = """
        SELECT DATE(timestamp) as scan_date, COUNT(*) as count 
        FROM scan_logs 
        GROUP BY scan_date
        ORDER BY scan_date DESC
        LIMIT 7
    """
    timeline = db_execute(timeline_query, fetch="all")
    timeline_labels = [str(t['scan_date']) for t in reversed(timeline)]
    timeline_counts = [t['count'] for t in reversed(timeline)]
    
    # Expiring Soon (Next 30 days)
    # Using a syntax that works for both SQLite and Postgres
    expiring_soon_query = """
        SELECT * FROM medicines 
        WHERE (CASE 
                WHEN exp_date IS NOT NULL AND exp_date != 'N/A' 
                THEN DATE(exp_date) 
                ELSE NULL 
               END) >= CURRENT_DATE 
        AND (CASE 
                WHEN exp_date IS NOT NULL AND exp_date != 'N/A' 
                THEN DATE(exp_date) 
                ELSE NULL 
               END) <= CURRENT_DATE + INTERVAL '30 days'
        ORDER BY exp_date ASC
    """
    # SQLite fallback if not on postgres
    if not os.environ.get('DATABASE_URL'):
        expiring_soon_query = """
            SELECT * FROM medicines 
            WHERE date(exp_date) >= date('now') 
            AND date(exp_date) <= date('now', '+30 days')
            ORDER BY exp_date ASC
        """
        
    expiring_soon = db_execute(expiring_soon_query, fetch="all")
    
    # Distribution Data
    results = db_execute("SELECT result, COUNT(*) as count FROM scan_logs GROUP BY result", fetch="all")
    distribution = {r['result']: r['count'] for r in results}

    return render_template('dashboard.html', stats={
        "total_meds": total_meds,
        "total_scans": total_scans,
        "fake_alerts": fake_alerts,
        "total_complaints": total_complaints,
        "unknown_scans": unknown_scans
    }, recent=recent_scans, distribution=distribution, 
    timeline_labels=timeline_labels, timeline_counts=timeline_counts,
    expiring_soon=expiring_soon)


@app.route('/api/stats')
def api_stats():
    if not session.get('admin'):
        return jsonify({"error": "Unauthorized"}), 403
        
    total_meds = db_execute('SELECT COUNT(*) FROM medicines', fetch="one")[0]
    total_scans = db_execute('SELECT COUNT(*) FROM scan_logs', fetch="one")[0]
    fake_alerts = db_execute('SELECT COUNT(*) FROM fake_alerts', fetch="one")[0]
    total_complaints = db_execute('SELECT COUNT(*) FROM complaints', fetch="one")[0]
    unknown_scans = db_execute("SELECT COUNT(DISTINCT qr_code_id) FROM scan_logs WHERE result = 'Unknown'", fetch="one")[0]
    
    return jsonify({
        "total_meds": total_meds,
        "total_scans": total_scans,
        "fake_alerts": fake_alerts,
        "total_complaints": total_complaints,
        "unknown_scans": unknown_scans
    })

@app.route('/generate_qr', methods=['GET', 'POST'])
def generate_qr():
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        manufacturer = request.form['manufacturer']
        batch = request.form.get('batch')
        if not batch or batch.strip() == "":
            batch = f"BAT-{int(datetime.now().timestamp())%100000}"
            
        mfg_date = request.form['mfg_date']
        exp_date = request.form['exp_date']
        distributor = request.form['distributor']
        
        # Unique QR ID generation
        unique_suffix = name.encode().hex()[0:6].upper()
        qr_code_id = f"QR-{int(datetime.now().timestamp())}-{unique_suffix}"
        
        # Simulated Blockchain Root
        timestamp = str(datetime.now())
        stage_info = f"Manufactured. Sent to Distributor: {distributor}"
        root_hash = generate_hash(f"ROOT-{qr_code_id}-{timestamp}")
        
        try:
            db_execute('''INSERT INTO medicines 
                            (name, manufacturer, batch_number, mfg_date, exp_date, distributor, qr_code_id) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (name, manufacturer, batch, mfg_date, exp_date, distributor, qr_code_id), commit=True)
            
            # Initial supply chain record (Genesis Block)
            db_execute('''INSERT INTO supply_chain (qr_code_id, stage, timestamp, previous_hash, current_hash) 
                            VALUES (?, ?, ?, ?, ?)''', (qr_id if 'qr_id' in locals() else qr_code_id, stage_info, timestamp, "0", root_hash), commit=True)
        except Exception as e:
            print(f"Generate QR Error: {e}")
            return render_template('generate_qr.html', error="Failed to register medicine. Could be a duplicate ID.")
            
        # Determine the base URL for the QR code
        base_url = get_base_url()
        
        return render_template('generate_qr.html', success=True, qr_code_id=qr_code_id, base_url=base_url)
    return render_template('generate_qr.html')

@app.route('/register', methods=['GET', 'POST'])
def register_medicine():
    if request.method == 'POST':
        name = request.form['name']
        manufacturer = request.form['manufacturer']
        mfg_date = request.form['mfg_date']
        exp_date = request.form['exp_date']
        distributor = request.form['distributor']
        
        # Auto-generate batch if not requested
        batch = f"BAT-{int(datetime.now().timestamp())%100000}"
        
        # Unique QR ID generation
        unique_suffix = name.encode().hex()[0:6].upper()
        qr_code_id = f"QR-{int(datetime.now().timestamp())}-{unique_suffix}"
        
        # Simulated Blockchain Root
        timestamp = str(datetime.now())
        stage_info = f"Manufactured. Sent to Distributor: {distributor}"
        root_hash = generate_hash(f"ROOT-{qr_code_id}-{timestamp}")
        
        try:
            db_execute('''INSERT INTO medicines 
                            (name, manufacturer, batch_number, mfg_date, exp_date, distributor, qr_code_id) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (name, manufacturer, batch, mfg_date, exp_date, distributor, qr_code_id), commit=True)
            
            # Initial supply chain record (Genesis Block)
            db_execute('''INSERT INTO supply_chain (qr_code_id, stage, timestamp, previous_hash, current_hash) 
                            VALUES (?, ?, ?, ?, ?)''', (qr_code_id, stage_info, timestamp, "0", root_hash), commit=True)
        except Exception as e:
            print(f"Register Medicine Error: {e}")
            return render_template('generate_qr.html', error="Failed to register medicine. Could be a duplicate.", is_public=True)
            
        base_url = get_base_url()
        
        return render_template('generate_qr.html', success=True, qr_code_id=qr_code_id, base_url=base_url, is_public=True)
    return render_template('generate_qr.html', is_public=True)

@app.route('/delete_medicine/<path:qr_id>')
def delete_medicine(qr_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    db_execute('DELETE FROM medicines WHERE qr_code_id = ?', (qr_id,), commit=True)
    db_execute('DELETE FROM scan_logs WHERE qr_code_id = ?', (qr_id,), commit=True)
    db_execute('DELETE FROM supply_chain WHERE qr_code_id = ?', (qr_id,), commit=True)
    db_execute('DELETE FROM fake_alerts WHERE qr_code_id = ?', (qr_id,), commit=True)
    
    # Stay on the current page if possible
    referrer = request.referrer
    if referrer and ('manage_medicines' in referrer or 'history' in referrer or 'dashboard' in referrer):
        return redirect(referrer)
    return redirect(url_for('manage_medicines'))

@app.route('/delete_scan/<int:scan_id>')
def delete_scan(scan_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    db_execute('DELETE FROM scan_logs WHERE id = ?', (scan_id,), commit=True)
    
    # Stay on the same page
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for('history'))

@app.route('/manage_medicines')
def manage_medicines():
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    medicines = db_execute('SELECT * FROM medicines ORDER BY id DESC', fetch="all")
    return render_template('manage_medicines.html', medicines=medicines)

@app.route('/history')
def history():
    if not session.get('admin'):
        return redirect(url_for('login'))
    logs = db_execute('SELECT s.*, m.name as medicine_name FROM scan_logs s LEFT JOIN medicines m ON s.qr_code_id = m.qr_code_id ORDER BY s.id DESC', fetch="all")
    return render_template('history.html', logs=logs)

@app.route('/export_history')
def export_history():
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    logs = db_execute('SELECT s.*, m.name as medicine_name FROM scan_logs s LEFT JOIN medicines m ON s.qr_code_id = m.qr_code_id ORDER BY s.id DESC', fetch="all")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'QR ID', 'Medicine Name', 'Location', 'Scanner Type', 'Result', 'Timestamp'])
    
    for row in logs:
        writer.writerow([row['id'], row['qr_code_id'], row['medicine_name'], row['location'], row['scanner_type'], row['result'], row['timestamp']])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=scan_history_export.csv"}
    )

@app.route('/fake_map')
def fake_map():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('fake_map.html')

@app.route('/admin/complaints')
def admin_complaints():
    if not session.get('admin'):
        return redirect(url_for('login'))
    reports = db_execute('SELECT * FROM complaints ORDER BY id DESC', fetch="all")
    return render_template('admin_complaints.html', reports=reports)

@app.route('/complaints', methods=['GET', 'POST'])
def complaints():
    prefill_name = request.args.get('med_name', '')
    prefill_batch = request.args.get('batch', '')
    
    if request.method == 'POST':
        medicine_name = request.form['medicine_name']
        batch = request.form['batch']
        description = request.form['description']
        location = request.form['location']
        
        db_execute('INSERT INTO complaints (medicine_name, batch_number, description, location, timestamp) VALUES (?, ?, ?, ?, ?)',
                     (medicine_name, batch, description, location, str(datetime.now())), commit=True)
        return render_template('complaints.html', success=True)
        
    return render_template('complaints.html', med_name=prefill_name, batch=prefill_batch)

# === API endpoints ===

@app.route('/verify/<path:medicine_id>', methods=['GET'])
def verify_medicine(medicine_id):
    location_coords = request.args.get('location', 'Unknown')
    scanner_type = request.args.get('scannerType', 'Consumer')
    is_damaged = request.args.get('isDamaged') == 'true'
    
    # CHECK BLACKLIST FIRST
    blacklisted = db_execute("SELECT * FROM blacklisted_qrs WHERE qr_code_id = ?", (medicine_id,), fetch="one")
    if blacklisted:
        # CLEAN FAKE ALERT (No admin mention)
        status_msg = "Fake"
        fake_reason = "This QR code has been verified as a COUNTERFEIT. DO NOT CONSUME. Please report this to the authorities immediately."
        med_details = {
            "name": "Confirmed Counterfeit",
            "manufacturer": "N/A",
            "batch_number": "N/A",
            "raw_data": medicine_id,
            "is_fake": True
        }
        if request.args.get('format') == 'json':
            return jsonify({"status": status_msg, "reason": fake_reason, "medicine": med_details, "medicine_id_raw": medicine_id})
        else:
            return render_template('verify.html', status=status_msg, reason=fake_reason, medicine=med_details, supply_chain=[])

    medicine = db_execute("SELECT * FROM medicines WHERE qr_code_id = ?", (medicine_id,), fetch="one")
    
    result = "Unknown"
    timestamp = str(datetime.now())
    is_fake = False
    fake_reason = ""
    med_details = None
    if not medicine:
        # Check simulated Global Database (Exact Match)
        global_med = db_execute("SELECT name, manufacturer, batch_number, mfg_date, exp_date, distributor, trust_source FROM global_medicines WHERE qr_code_id = ?", (medicine_id,), fetch="one")
        
        # If no exact match, check Trusted Domains List (Wildcard Match)
        if not global_med:
            trusted_domains = {
                "verify.novartis.in": ("Novartis Product", "Novartis", "Novartis Secure Portal"),
                "novartis.verify": ("Novartis Product", "Novartis", "Novartis Secure Portal"),
                "sun.psverify.com": ("Sun Pharma Product", "Sun Pharma", "Government Verified / Sun Pharma portal"),
                "verify.pfizer.com": ("Pfizer Product", "Pfizer", "Pfizer Official Portal"),
                "trace.gsk.com": ("GSK Product", "GSK", "GSK Trust Portal"),
                "cipla.com/verify": ("Cipla Product", "Cipla", "Cipla Authentic"),
                "drreddys.com/auth": ("Dr. Reddy's Product", "Dr. Reddy's", "Dr. Reddy's Global"),
                "abbott-authenticator.com": ("Abbott Product", "Abbott", "Abbott Direct")
            }
            
            for domain, info in trusted_domains.items():
                if domain in str(medicine_id):
                    global_med = {
                        "name": info[0] + " (Ext)",
                        "manufacturer": info[1],
                        "batch_number": "EXT-Dynamic",
                        "mfg_date": "N/A",
                        "exp_date": "N/A",
                        "distributor": "Global Verified Dist.",
                        "trust_source": info[2]
                    }
                    break

        if global_med:
            result = "Verified"
            status_msg = "Genuine Medicine (Trusted Global Source)"
            fake_reason = f"Verified via {global_med['trust_source']}"
            med_details = {
                "name": global_med["name"],
                "manufacturer": global_med["manufacturer"],
                "batch_number": global_med["batch_number"],
                "mfg_date": global_med["mfg_date"],
                "exp_date": global_med["exp_date"],
                "distributor": global_med["distributor"],
                "is_external": True,
                "trust_source": global_med['trust_source'],
                "raw_data": medicine_id
            }
        else:
            is_counterfeit = False
            suspicious_keywords = ["psverify", "novartis", "pfizer", "gsk", "cipla", "drreddys", "abbott"]
            for keyword in suspicious_keywords:
                if keyword in str(medicine_id).lower():
                    is_counterfeit = True
                    break
            
            if is_counterfeit:
                result = "Fake"
                is_fake = True
                fake_reason = "This QR code mimics a trusted manufacturer but uses a fake or misspelled domain. Highly likely COUNTERFEIT."
                status_msg = "Fake"
                med_details = {
                    "name": "Potential Counterfeit",
                    "manufacturer": "Unknown",
                    "batch_number": "Unknown",
                    "raw_data": medicine_id,
                    "is_fake": True,
                    "is_external": False,
                    "trust_source": "Counterfeit Filter"
                }
            else:
                result = "Unknown"
                status_msg = "Suspicious / Unregistered Product"
                fake_reason = "This product information is not found in our verified records. It is suspicious and requires manual verification by an administrator."
                med_details = {
                    "name": "Unregistered Product",
                    "manufacturer": "Pending Verification",
                    "batch_number": "N/A",
                    "raw_data": medicine_id,
                    "is_unknown": True,
                    "is_external": False,
                    "trust_source": "N/A"
                }
    else:
        # Populating base med_details for ALL local medicine states
        med_details = {
            "name": medicine["name"],
            "manufacturer": medicine["manufacturer"],
            "batch_number": medicine["batch_number"],
            "mfg_date": medicine["mfg_date"],
            "exp_date": medicine["exp_date"],
            "distributor": medicine["distributor"],
            "is_external": False,
            "trust_source": "Aushadhi Vishwas Internal DB",
            "raw_data": medicine_id
        }

        # Check expiry
        is_expired = False
        if medicine['exp_date'] != 'N/A':
            try:
                exp_date = datetime.strptime(medicine['exp_date'], '%Y-%m-%d')
                if datetime.now() > exp_date:
                    is_expired = True
            except:
                pass 
        
        if is_expired:
            result = "Expired"
            is_fake = True
            fake_reason = "Expired medicine scanned"
            status_msg = "Expired Medicine Warning"
        else:
            scans_count = db_execute("""
                SELECT COUNT(DISTINCT location) FROM scan_logs 
                WHERE qr_code_id = ? AND location != 'Unknown' AND location != ?
            """, (medicine_id, location_coords), fetch="one")[0]
            
            if scans_count >= 1:
                rows = db_execute("SELECT DISTINCT location FROM scan_logs WHERE qr_code_id = ? AND location != 'Unknown' AND location != ?", (medicine_id, location_coords), fetch="all")
                locs = [r['location'] for r in rows]
                result = "Suspicious"
                is_fake = True
                fake_reason = f"QR code scanned in multiple cities/locations: {locs}"
                status_msg = "Suspicious Medicine Alert"
            else:
                result = "Verified"
                status_msg = "Genuine Medicine (Verified Source)"
                fake_reason = "This product information is verified and registered in the Aushadhi Vishwas database."

    # Override if marked as damaged
    if is_damaged:
        result = "Unknown"
        is_fake = False # Don't mark as fake yet, let admin decide
        fake_reason = "QR code reported as blurry or damaged (Potential tampering detected)."
        status_msg = "Suspicious (Possible Tamper)"

    # If consumer scan and verified, add to supply chain
    if result == "Verified" and scanner_type == "Consumer":
        chk = db_execute("SELECT id, current_hash FROM supply_chain WHERE qr_code_id = ? ORDER BY id DESC LIMIT 1", (medicine_id,), fetch="one")
        already_scanned = db_execute("SELECT id FROM supply_chain WHERE qr_code_id = ? AND stage = 'Scanned by Consumer'", (medicine_id,), fetch="one")
        
        if not already_scanned:
            prev_hash = chk['current_hash'] if chk else "0"
            new_hash = generate_hash(f"{prev_hash}-{medicine_id}-Consumer-{timestamp}")
            db_execute('''INSERT INTO supply_chain (qr_code_id, stage, location, timestamp, previous_hash, current_hash) 
                            VALUES (?, ?, ?, ?, ?, ?)''', (medicine_id, 'Scanned by Consumer', location_coords, timestamp, prev_hash, new_hash), commit=True)
            
    # Get supply chain history
    supply_history = []
    if medicine:
        rows = db_execute("SELECT * FROM supply_chain WHERE qr_code_id = ? ORDER BY id ASC", (medicine_id,), fetch="all")
        supply_history = [{"stage": r['stage'], "location": r['location'], "timestamp": r['timestamp'], "hash": r['current_hash']} for r in rows]

    # Insert fake alert if applicable
    if is_fake:
        db_execute('''INSERT INTO fake_alerts (qr_code_id, location, reason, timestamp) 
                        VALUES (?, ?, ?, ?)''', (medicine_id, location_coords, fake_reason, timestamp), commit=True)
    
    # Record scan log
    db_execute('''INSERT INTO scan_logs (qr_code_id, result, location, scanner_type, timestamp) 
                    VALUES (?, ?, ?, ?, ?)''', (medicine_id, result, location_coords, scanner_type, timestamp), commit=True)
    
    if request.args.get('format') == 'json':
        return jsonify({
            "status": status_msg,
            "reason": fake_reason,
            "medicine": med_details,
            "supply_chain": supply_history,
            "medicine_id_raw": medicine_id, 
            "scannerType": scanner_type,
            "isDamaged": is_damaged,
            "is_fake": is_fake
        })
    else:
        return render_template('verify.html', 
                             status=status_msg, 
                             reason=fake_reason, 
                             medicine=med_details, 
                             supply_chain=supply_history,
                             is_fake=is_fake)

@app.route('/api/fake_alerts', methods=['GET'])
def api_fake_alerts():
    alerts = db_execute("SELECT * FROM fake_alerts", fetch="all")
    
    results = []
    for a in alerts:
        results.append({
            "qr_code_id": a["qr_code_id"],
            "location": a["location"],
            "reason": a["reason"],
            "timestamp": a["timestamp"]
        })
    return jsonify(results)

@app.route('/admin/unknown_scans')
def admin_unknown_scans():
    if not session.get('admin'):
        return redirect(url_for('login'))
    # Find unique unknown QR IDs from logs
    unknowns = db_execute("""
        SELECT qr_code_id, MAX(timestamp) as last_seen, COUNT(*) as scan_count, MAX(location) as last_location
        FROM scan_logs 
        WHERE result IN ('Unknown', 'Suspicious') 
        GROUP BY qr_code_id 
        ORDER BY last_seen DESC
    """, fetch="all")
    return render_template('admin_unknown_scans.html', unknowns=unknowns)

@app.route('/admin/blacklist')
def admin_blacklist():
    if not session.get('admin'):
        return redirect(url_for('login'))
    blacklisted = db_execute("SELECT * FROM blacklisted_qrs ORDER BY timestamp DESC", fetch="all")
    return render_template('admin_blacklist.html', blacklisted=blacklisted)

@app.route('/api/blacklist_qr', methods=['POST'])
def blacklist_qr():
    if not session.get('admin'):
        return jsonify({"success": False, "message": "Admin authorization required"}), 403
    
    data = request.json
    qr_id = data.get('qr_code_id')
    reason = data.get('reason', 'Manually blacklisted by Admin')
    
    if not qr_id:
        return jsonify({"success": False, "message": "Missing QR ID"}), 400
        
    try:
        # Using a direct is_postgres check for the complex ON CONFLICT logic
        if DATABASE_URL:
            db_execute("INSERT INTO blacklisted_qrs (qr_code_id, reason, timestamp) VALUES (%s, %s, %s) ON CONFLICT (qr_code_id) DO UPDATE SET reason = EXCLUDED.reason, timestamp = EXCLUDED.timestamp", (qr_id, reason, str(datetime.now())), commit=True)
        else:
            db_execute("INSERT OR REPLACE INTO blacklisted_qrs (qr_code_id, reason, timestamp) VALUES (?, ?, ?)", (qr_id, reason, str(datetime.now())), commit=True)
        
        # [NEW] Auto-cleanup: Update all existing 'Unknown' logs for this QR to 'Fake'
        db_execute("UPDATE scan_logs SET result = 'Fake' WHERE qr_code_id = ? AND result = 'Unknown'", (qr_id,), commit=True)
        
        # Log as fake alert
        db_execute("INSERT OR IGNORE INTO fake_alerts (qr_code_id, location, reason, timestamp) VALUES (?, ?, ?, ?)", (qr_id, "Admin Panel", f"Blacklisted: {reason}", str(datetime.now())), commit=True)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/unblacklist_qr', methods=['POST'])
def unblacklist_qr():
    if not session.get('admin'):
        return jsonify({"success": False, "message": "Admin authorization required"}), 403
    
    data = request.json
    qr_id = data.get('qr_code_id')
    
    if not qr_id:
        return jsonify({"success": False, "message": "Missing QR ID"}), 400
        
    try:
        db_execute("DELETE FROM blacklisted_qrs WHERE qr_code_id = ?", (qr_id,), commit=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/delete_unknown_scan', methods=['POST'])
def delete_unknown_scan():
    if not session.get('admin'):
        return jsonify({"success": False, "message": "Admin authorization required"}), 403
    
    data = request.json
    qr_id = data.get('qr_code_id')
    
    if not qr_id:
        return jsonify({"success": False, "message": "Missing QR ID"}), 400
        
    try:
        # Delete 'Unknown' and 'Suspicious' scans for this QR ID. Genuine/Fake logs remain.
        db_execute("DELETE FROM scan_logs WHERE qr_code_id = ? AND result IN ('Unknown', 'Suspicious')", (qr_id,), commit=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/onboard_external', methods=['POST'])
def onboard_external():
    if not session.get('admin'):
        return jsonify({"success": False, "message": "Admin authorization required"}), 403
    data = request.json
    qr_id = data.get('qr_code_id')
    name = data.get('name', 'External Product')
    manufacturer = data.get('manufacturer', 'Unknown')
    batch = data.get('batch_number')
    if not batch or batch.strip() == "" or batch == "EXT-Dynamic":
        batch = f"BAT-EXT-{int(datetime.now().timestamp())%100000}"
    mfg_date = data.get('mfg_date', 'N/A')
    exp_date = data.get('exp_date', 'N/A')
    distributor = data.get('distributor', 'N/A')
    
    if not qr_id:
        return jsonify({"success": False, "message": "Missing QR ID"}), 400
        
    try:
        db_execute('''INSERT OR IGNORE INTO medicines 
                        (name, manufacturer, batch_number, mfg_date, exp_date, distributor, qr_code_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (name, manufacturer, batch, mfg_date, exp_date, distributor, qr_id), commit=True)
        
        # Add a supply chain entry for verification
        timestamp = str(datetime.now())
        stage_info = "Manually Verified & Onboarded by Consumer"
        root_hash = generate_hash(f"MANUAL-{qr_id}-{timestamp}")
        db_execute('''INSERT OR IGNORE INTO supply_chain (qr_code_id, stage, timestamp, previous_hash, current_hash) 
                        VALUES (?, ?, ?, ?, ?)''', (qr_id, stage_info, timestamp, "0", root_hash), commit=True)
        
        # [NEW] Auto-cleanup: Update all existing 'Unknown' logs for this QR to 'Verified'
        db_execute("UPDATE scan_logs SET result = 'Verified' WHERE qr_code_id = ? AND result = 'Unknown'", (qr_id,), commit=True)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
