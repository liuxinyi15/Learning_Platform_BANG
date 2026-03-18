import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


DB_PATH = 'platform.db'


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ===========================
# 1. Database Initialization
# ===========================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            category TEXT NOT NULL,
            file_path TEXT NOT NULL,
            cover_path TEXT,
            upload_time DATETIME,
            uploader TEXT,
            user_id INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0 
        )
    ''')
    
    cursor.execute("PRAGMA table_info(materials)")
    material_columns = {row["name"] for row in cursor.fetchall()}
    if "user_id" not in material_columns:
        cursor.execute("ALTER TABLE materials ADD COLUMN user_id INTEGER")

    init_admin_username = os.environ.get("BANG_INIT_ADMIN_USERNAME", "").strip()
    init_admin_password = os.environ.get("BANG_INIT_ADMIN_PASSWORD", "").strip()

    if init_admin_username and init_admin_password:
        cursor.execute("SELECT id FROM users WHERE username = ?", (init_admin_username,))
        if not cursor.fetchone():
            p_hash = generate_password_hash(init_admin_password)
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                (init_admin_username, p_hash, 1)
            )
            print(f">>> Initial admin created from environment: {init_admin_username}")

    conn.commit()
    conn.close()

# ===========================
# 2. User Management
# ===========================

def create_user(username, password, is_admin=0):
    if not username or not password or len(password) < 8:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        p_hash = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)', 
                       (username, p_hash, is_admin))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, is_admin FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        user_id, p_hash, is_admin = row
        if check_password_hash(p_hash, password):
            return {"id": user_id, "is_admin": is_admin}
    return None

def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, is_admin FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id == 1:
        return False
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True

def update_user_role(user_id, is_admin):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id == 1: 
        return False
    cursor.execute('UPDATE users SET is_admin = ? WHERE id = ?', (is_admin, user_id))
    conn.commit()
    conn.close()
    return True

def admin_reset_password(user_id, new_password):
    if not new_password or len(new_password) < 8:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    p_hash = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (p_hash, user_id))
    conn.commit()
    conn.close()
    return True

# ===========================
# 3. Material Management
# ===========================
def get_all_categories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT DISTINCT category FROM materials')
        rows = cursor.fetchall()
        categories = [row[0] for row in rows]
    except: categories = []
    finally: conn.close()
    defaults = ["Chinese", "English", "French"]
    for d in defaults:
        if d not in categories: categories.append(d)
    return categories

def get_materials(uploader_type=None, sort_by='newest', user_id=None, include_all=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM materials"
    clauses = []
    params = []
    if uploader_type:
        clauses.append("uploader = ?")
        params.append(uploader_type)
    if user_id is not None and not include_all:
        if uploader_type == 'User':
            clauses.append("user_id = ?")
            params.append(user_id)
        elif uploader_type is None:
            clauses.append("(uploader = 'System' OR (uploader = 'User' AND user_id = ?))")
            params.append(user_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    if sort_by == 'newest': sql += " ORDER BY upload_time DESC"
    elif sort_by == 'oldest': sql += " ORDER BY upload_time ASC"
    elif sort_by == 'a-z': sql += " ORDER BY filename ASC"
    else: sql += " ORDER BY category, upload_time DESC"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_material_by_id(material_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM materials WHERE id = ?", (material_id,))
    row = cursor.fetchone()
    if row:
        if row['file_path'] and os.path.exists(row['file_path']):
            try: os.remove(row['file_path']) 
            except: pass
        if row['cover_path'] and os.path.exists(row['cover_path']):
            try: os.remove(row['cover_path']) 
            except: pass
        cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def add_file_to_db(filename, category, file_path, cover_path=None, uploader='System', user_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO materials (filename, category, file_path, cover_path, upload_time, uploader, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (filename, category, file_path, cover_path, datetime.now(), uploader, user_id))
    conn.commit()
    conn.close()

def save_user_upload_with_db(file, cover_file, category_input, base_path, uploader='User', user_id=None):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'pptx', 'txt'}
    ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif'}
    if not file or '.' not in file.filename: return False
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS: return False
    target_dir = os.path.join(base_path, "User_Uploads")
    if not os.path.exists(target_dir): os.makedirs(target_dir)
    original_name = secure_filename(file.filename)
    stem, suffix = os.path.splitext(original_name)
    filename = original_name
    full_path = os.path.join(target_dir, filename)
    counter = 1
    while os.path.exists(full_path):
        filename = f"{stem}_{counter}{suffix}"
        full_path = os.path.join(target_dir, filename)
        counter += 1
    file.save(full_path)
    final_cover_path = None
    if cover_file and cover_file.filename != '':
        img_ext = cover_file.filename.rsplit('.', 1)[1].lower()
        if img_ext in ALLOWED_IMG:
            cover_filename = f"cover_{os.path.splitext(filename)[0]}.{img_ext}"
            cover_full_path = os.path.join(target_dir, cover_filename)
            cover_counter = 1
            while os.path.exists(cover_full_path):
                cover_filename = f"cover_{os.path.splitext(filename)[0]}_{cover_counter}.{img_ext}"
                cover_full_path = os.path.join(target_dir, cover_filename)
                cover_counter += 1
            cover_file.save(cover_full_path)
            final_cover_path = cover_full_path
    add_file_to_db(filename, category_input, full_path, final_cover_path, uploader=uploader, user_id=user_id)
    return True
