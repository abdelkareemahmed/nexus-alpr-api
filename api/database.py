import psycopg2
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id SERIAL PRIMARY KEY,
            plate_number TEXT UNIQUE NOT NULL,
            owner_name TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visits (
            id SERIAL PRIMARY KEY,
            plate_number TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            status TEXT DEFAULT 'inside',
            fee REAL DEFAULT 0
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("PostgreSQL Database initialized successfully! ☁️")

def log_entry(plate_number):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM visits WHERE plate_number = %s AND status = 'inside'", (plate_number,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return {"status": "warning", "message": "Vehicle is already inside the parking lot."}
        
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO visits (plate_number, entry_time) VALUES (%s, %s)", (plate_number, now))
    
    cursor.execute("SELECT owner_name FROM subscribers WHERE plate_number = %s", (plate_number,))
    sub = cursor.fetchone()
    
    conn.commit()
    cursor.close()
    conn.close()
    
    if sub:
        return {"status": "success", "is_vip": True, "message": f"Welcome VIP member: {sub[0]}", "entry_time": now}
    else:
        return {"status": "success", "is_vip": False, "message": "New visitor entry logged successfully.", "entry_time": now}

def checkout_vehicle(plate_number):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, entry_time FROM visits WHERE plate_number = %s AND status = 'inside'", (plate_number,))
    record = cursor.fetchone()
    
    if not record:
        cursor.close()
        conn.close()
        return {"status": "error", "message": "Vehicle is not logged as currently inside the parking lot."}
        
    visit_id, entry_time_str = record
    now = datetime.now()
    entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
    hours = (now - entry_time).total_seconds() / 3600
    
    cursor.execute("SELECT id FROM subscribers WHERE plate_number = %s", (plate_number,))
    is_sub = cursor.fetchone()
    
    fee = 0
    if is_sub:
        message = "VIP Checkout - No fees applied."
    else:
        fee = max(10, round(hours * 20, 2))
        message = "Visitor Checkout - Please pay the required fee."
        
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE visits SET exit_time = %s, status = 'outside', fee = %s WHERE id = %s", (now_str, fee, visit_id))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        "status": "success",
        "duration_hours": round(hours, 4),
        "fee_egp": fee,
        "message": message,
        "exit_time": now_str
    }

def add_new_subscriber(plate_number, owner_name):
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO subscribers (plate_number, owner_name) VALUES (%s, %s)", 
            (plate_number, owner_name)
        )
        conn.commit()
        response = {"status": "success", "message": f"Successfully added VIP: {owner_name} with plate [{plate_number}]"}
    except psycopg2.IntegrityError:
        conn.rollback()
        response = {"status": "error", "message": f"Plate number [{plate_number}] is already registered as VIP."}
    finally:
        cursor.close()
        conn.close()
        
    return response

def get_all_visits():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plate_number, entry_time, exit_time, status, fee FROM visits ORDER BY id DESC")
    rows = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return rows