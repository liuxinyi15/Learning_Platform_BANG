import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename

# ===========================
# 数据库初始化
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
    conn.commit()
    conn.close()

# ===========================
# 获取所有分类 (解决 NameError 的关键)
# ===========================
def get_all_categories():
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT DISTINCT category FROM materials')
        rows = cursor.fetchall()
        categories = [row[0] for row in rows]
    except:
        categories = []
    finally:
        conn.close()
    
    # 确保默认分类存在
    defaults = ["Chinese", "English", "French"]
    for d in defaults:
        if d not in categories:
            categories.append(d)
    return categories

# ===========================
# 获取素材 (支持筛选和排序)
# ===========================
def get_materials(uploader_type=None, sort_by='newest'):
    conn = sqlite3.connect('platform.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = "SELECT * FROM materials"
    params = []

    # 1. 筛选 (官方 vs 用户)
    if uploader_type:
        sql += " WHERE uploader = ?"
        params.append(uploader_type)

    # 2. 排序逻辑
    if sort_by == 'newest':
        sql += " ORDER BY upload_time DESC"
    elif sort_by == 'oldest':
        sql += " ORDER BY upload_time ASC"
    elif sort_by == 'a-z':
        sql += " ORDER BY filename ASC"
    else:
        sql += " ORDER BY category, upload_time DESC"

    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return rows

# ===========================
# 删除素材
# ===========================
def delete_material_by_id(material_id):
    conn = sqlite3.connect('platform.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM materials WHERE id = ?", (material_id,))
    row = cursor.fetchone()
    
    if row:
        # 删除物理文件
        if row['file_path'] and os.path.exists(row['file_path']):
            try: os.remove(row['file_path']) 
            except: pass
        # 删除封面
        if row['cover_path'] and os.path.exists(row['cover_path']):
            try: os.remove(row['cover_path']) 
            except: pass

        # 删除数据库记录
        cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

# ===========================
# 存入数据库
# ===========================
def add_file_to_db(filename, category, file_path, cover_path=None, uploader='System'):
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO materials (filename, category, file_path, cover_path, upload_time, uploader)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (filename, category, file_path, cover_path, datetime.now(), uploader))
    conn.commit()
    conn.close()

# ===========================
# 处理上传 (强制存入 User_Uploads)
# ===========================
def save_user_upload_with_db(file, cover_file, category_input, base_path):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'pptx', 'txt'}
    ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif'}

    if not file or '.' not in file.filename:
        return False
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False

    # 这里的路径改为 User_Uploads，与你的文件夹结构匹配
    target_dir = os.path.join(base_path, "User_Uploads")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

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

    add_file_to_db(filename, category_input, full_path, final_cover_path, uploader='User')
    return True