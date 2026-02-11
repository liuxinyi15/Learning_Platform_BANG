import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ===========================
# 1. 数据库初始化
# ===========================
def init_db():
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            category TEXT NOT NULL,
            file_path TEXT NOT NULL,
            cover_path TEXT,
            upload_time DATETIME,
            uploader TEXT
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
    
    # 自动创建默认管理员
    try:
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            p_hash = generate_password_hash("admin123")
            cursor.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                           ('admin', p_hash, 1))
            print(">>> 默认管理员已创建: admin / admin123")
    except Exception as e:
        print("Admin check error:", e)

    conn.commit()
    conn.close()

# ===========================
# 2. 用户管理 (核心升级)
# ===========================

# 🔥 升级：增加 is_admin 参数，允许直接创建管理员
def create_user(username, password, is_admin=0):
    conn = sqlite3.connect('platform.db')
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
    conn = sqlite3.connect('platform.db')
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
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, is_admin FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_all_users():
    conn = sqlite3.connect('platform.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_user_by_id(user_id):
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    # 保护机制：ID为1的超级管理员不能删
    if user_id == 1:
        return False
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True

# 🔥 新增：修改用户角色 (提权/降权)
def update_user_role(user_id, is_admin):
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    if user_id == 1: # 保护超级管理员
        return False
    cursor.execute('UPDATE users SET is_admin = ? WHERE id = ?', (is_admin, user_id))
    conn.commit()
    conn.close()
    return True

# 🔥 新增：管理员强制重置密码
def admin_reset_password(user_id, new_password):
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    p_hash = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (p_hash, user_id))
    conn.commit()
    conn.close()
    return True

# ===========================
# 3. 素材管理 (保持不变)
# ===========================
def get_all_categories():
    conn = sqlite3.connect('platform.db')
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

def get_materials(uploader_type=None, sort_by='newest'):
    conn = sqlite3.connect('platform.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = "SELECT * FROM materials"
    params = []
    if uploader_type:
        sql += " WHERE uploader = ?"
        params.append(uploader_type)
    if sort_by == 'newest': sql += " ORDER BY upload_time DESC"
    elif sort_by == 'oldest': sql += " ORDER BY upload_time ASC"
    elif sort_by == 'a-z': sql += " ORDER BY filename ASC"
    else: sql += " ORDER BY category, upload_time DESC"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_material_by_id(material_id):
    conn = sqlite3.connect('platform.db')
    conn.row_factory = sqlite3.Row
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

def add_file_to_db(filename, category, file_path, cover_path=None, uploader='System'):
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO materials (filename, category, file_path, cover_path, upload_time, uploader)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (filename, category, file_path, cover_path, datetime.now(), uploader))
    conn.commit()
    conn.close()

def save_user_upload_with_db(file, cover_file, category_input, base_path, uploader='User'):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'pptx', 'txt'}
    ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif'}
    if not file or '.' not in file.filename: return False
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS: return False
    target_dir = os.path.join(base_path, "User_Uploads")
    if not os.path.exists(target_dir): os.makedirs(target_dir)
    filename = secure_filename(file.filename)
    full_path = os.path.join(target_dir, filename)
    file.save(full_path)
    final_cover_path = None
    if cover_file and cover_file.filename != '':
        img_ext = cover_file.filename.rsplit('.', 1)[1].lower()
        if img_ext in ALLOWED_IMG:
            cover_filename = f"cover_{os.path.splitext(filename)[0]}.{img_ext}"
            cover_full_path = os.path.join(target_dir, cover_filename)
            cover_file.save(cover_full_path)
            final_cover_path = cover_full_path
    add_file_to_db(filename, category_input, full_path, final_cover_path, uploader=uploader)
    return True