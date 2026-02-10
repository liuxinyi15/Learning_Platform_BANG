import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename

# 数据库初始化
def init_db():
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            category TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_time DATETIME,
            uploader TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 获取所有素材（新增：用于给 app.py 提供页面数据）
def get_all_materials():
    conn = sqlite3.connect('platform.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM materials ORDER BY category')
    rows = cursor.fetchall()
    conn.close()
    return rows

# 将文件记录存入数据库
def add_file_to_db(filename, category, file_path, uploader='System'):
    conn = sqlite3.connect('platform.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO materials (filename, category, file_path, upload_time, uploader)
        VALUES (?, ?, ?, ?, ?)
    ''', (filename, category, file_path, datetime.now(), uploader))
    conn.commit()
    conn.close()

# 带数据库记录的上传函数
def save_user_upload_with_db(file, base_path):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'pptx', 'txt'}
    if file and '.' in file.filename and \
       file.filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS:
        
        filename = secure_filename(file.filename)
        category = 'User_Uploads'
        target_dir = os.path.join(base_path, category)
        
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        full_path = os.path.join(target_dir, filename)
        file.save(full_path)
        
        # 同步存入数据库
        add_file_to_db(filename, category, full_path, uploader='User')
        return True
    return False
