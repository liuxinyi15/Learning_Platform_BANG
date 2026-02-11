from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response, jsonify, flash, abort
import os
import pandas as pd
import requests
import json
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps

# 引入 Service
from services.library_service import (
    init_db,
    save_user_upload_with_db,
    get_materials,
    get_all_categories,
    delete_material_by_id,
    create_user,
    verify_user,
    get_user_by_id,
    get_all_users,
    delete_user_by_id,
    update_user_role,      # 权限管理
    admin_reset_password   # 密码重置
)
from services.audio_service import AudioServiceClient

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_this'  # 🔐 Session加密密钥

# ===========================
# 🔐 Flask-Login 配置
# ===========================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 未登录时自动跳转的视图函数名

class User(UserMixin):
    def __init__(self, id, username, is_admin=0):
        self.id = id
        self.username = username
        self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id):
    row = get_user_by_id(user_id)
    if row:
        # row结构: (id, username, is_admin)
        return User(id=row[0], username=row[1], is_admin=row[2])
    return None

# 自定义装饰器：只允许管理员访问
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("权限不足：你需要管理员权限才能访问。", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ===========================
# 路径配置与初始化
# ===========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBRARY_PATH = os.path.join(BASE_DIR, "library")
init_db()  # 初始化数据库
if not os.path.exists(LIBRARY_PATH):
    os.makedirs(LIBRARY_PATH)

# =====================================================
# 👑 Admin 后台管理 (功能增强版)
# =====================================================
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    # 处理新建管理员/用户请求
    if request.method == "POST":
        new_username = request.form.get("new_username")
        new_password = request.form.get("new_password")
        role = request.form.get("role") # 'admin' or 'user'
        
        is_admin_flag = 1 if role == 'admin' else 0
        
        if create_user(new_username, new_password, is_admin=is_admin_flag):
            flash(f"用户 {new_username} 创建成功！", "success")
        else:
            flash("创建失败：用户名已存在。", "error")
        return redirect(url_for('admin_dashboard'))

    users = get_all_users()
    materials = get_materials(uploader_type=None) 
    return render_template("admin.html", users=users, materials=materials)

# 🔥 切换权限：设为管理员
@app.route("/admin/promote/<int:user_id>")
@admin_required
def admin_promote(user_id):
    if update_user_role(user_id, 1):
        flash("该用户已升级为管理员。", "success")
    else:
        flash("操作失败。", "error")
    return redirect(url_for('admin_dashboard'))

# 🔥 切换权限：降级为普通用户
@app.route("/admin/demote/<int:user_id>")
@admin_required
def admin_demote(user_id):
    if user_id == current_user.id:
        flash("你不能降级你自己！", "error")
    elif user_id == 1:
        flash("无法修改超级管理员权限。", "error")
    else:
        update_user_role(user_id, 0)
        flash("该用户已降级为普通用户。", "success")
    return redirect(url_for('admin_dashboard'))

# 🔥 重置密码
@app.route("/admin/reset_pwd/<int:user_id>")
@admin_required
def admin_reset_pwd(user_id):
    # 重置为默认密码 123456
    admin_reset_password(user_id, "123456")
    flash(f"用户ID {user_id} 的密码已重置为: 123456", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_user/<int:user_id>")
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        flash("你不能删除你自己！", "error")
        return redirect(url_for('admin_dashboard'))
        
    if delete_user_by_id(user_id): 
        flash("用户已删除", "success")
    else: 
        flash("无法删除该用户", "error")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_material/<int:material_id>")
@admin_required
def admin_delete_material(material_id):
    if delete_material_by_id(material_id): 
        flash("素材已强制删除", "success")
    else: 
        flash("删除失败", "error")
    return redirect(url_for('admin_dashboard'))

# =====================================================
# 🔐 认证路由
# =====================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "POST":
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')

        if action == 'register':
            if create_user(username, password):
                flash('注册成功！请直接登录。', 'success')
            else:
                flash('用户名已存在。', 'error')
        
        elif action == 'login':
            user_data = verify_user(username, password)
            if user_data:
                user = User(user_data['id'], username, user_data['is_admin'])
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('用户名或密码错误。', 'error')

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# =====================================================
# 🏠 首页
# =====================================================
@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

# =====================================================
# 📚 资料库 (支持批量上传)
# =====================================================
@app.route("/library", methods=["GET", "POST"])
@login_required
def library():
    success = None
    error = None

    # ---------- 1. 处理批量上传 ----------
    if request.method == "POST":
        # 🔥 使用 getlist 获取多个文件
        files = request.files.getlist("material_file")
        cover = request.files.get("cover_file")
        
        select_mode = request.form.get("category_mode")
        selected_cat = request.form.get("category_select")
        new_cat = request.form.get("category_new")

        final_category = "General"
        if select_mode == "new" and new_cat:
            final_category = new_cat
        elif selected_cat:
            final_category = selected_cat

        # 检查是否真的选了文件
        if not files or files[0].filename == "":
            error = "未选择任何文件"
        else:
            uploader_type = 'System' if current_user.is_admin else 'User'
            success_count = 0
            fail_count = 0

            # 🔥 循环处理每一个文件
            for file in files:
                if file and file.filename:
                    # 重置文件指针，防止多文件处理时 cover 指针跑偏
                    file.stream.seek(0)
                    if cover: cover.stream.seek(0)
                    
                    ok = save_user_upload_with_db(file, cover, final_category, LIBRARY_PATH, uploader=uploader_type)
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
            
            # 生成反馈信息
            if success_count > 0:
                base_msg = f"成功上传 {success_count} 个文件！"
                if fail_count > 0:
                    base_msg += f" (另有 {fail_count} 个失败)"
                
                if current_user.is_admin:
                    success = f"官方入库：{base_msg} 分类: [{final_category}]"
                else:
                    success = base_msg
            else:
                error = "所有文件上传失败（格式不支持？）"

    # ---------- 2. 获取数据 ----------
    sort_option = request.args.get('sort', 'newest')
    active_tab = request.args.get('tab', 'official')

    official_materials = get_materials(uploader_type='System', sort_by=sort_option)
    user_materials = get_materials(uploader_type='User', sort_by=sort_option)
    categories = get_all_categories()

    return render_template(
        "library.html",
        official_materials=official_materials,
        user_materials=user_materials,
        categories=categories,
        active_tab=active_tab,
        sort_option=sort_option,
        success=success,
        error=error
    )

@app.route("/library/delete/<int:material_id>")
@login_required
def delete_material(material_id):
    if delete_material_by_id(material_id):
        return redirect(url_for('library', tab='user'))
    return "删除失败", 400

@app.route("/library/cover/<int:material_id>")
@login_required
def get_cover(material_id):
    rows = get_materials()
    target = next((m for m in rows if m['id'] == material_id), None)
    if target and target["cover_path"] and os.path.exists(target["cover_path"]):
        return send_from_directory(os.path.dirname(target["cover_path"]), os.path.basename(target["cover_path"]))
    return "No Cover", 404

@app.route("/library/download/<int:material_id>")
@login_required
def download_material(material_id):
    rows = get_materials()
    target = next((m for m in rows if m['id'] == material_id), None)
    if target is None: return "File not found", 404
    return send_from_directory(os.path.dirname(target["file_path"]), os.path.basename(target["file_path"]), as_attachment=True)

# =====================================================
# 其他业务路由
# =====================================================

@app.route("/planner")
@login_required
def planner():
    return render_template("planner.html")

@app.route("/vocabulary")
@login_required
def vocabulary():
    return render_template("vocab.html")

@app.route("/audio")
@login_required
def audio_page():
    return render_template("audio.html")

@app.route("/api/generate_audio_json", methods=["POST"])
@login_required
def generate_audio_from_json():
    data = request.json
    filename = data.get("filename", "vocab_audio")
    items_raw = data.get("items", [])
    
    formatted_items = []
    for item in items_raw:
        formatted_items.append({
            "en": str(item.get("English", "")),
            "zh": str(item.get("Chinese", ""))
        })

    try:
        response = requests.post(
            "http://127.0.0.1:8000/generate-audio",
            json={
                "items": formatted_items,
                "repeat": int(data.get("repeat", 1)),
                "rate": data.get("rate", "+0%"),
                "voice": data.get("voice", "zh-CN-XiaoxiaoNeural")
            },
            stream=True
        )
        if response.status_code != 200:
            return jsonify({"error": "Audio Service Error", "details": response.text}), response.status_code

        return Response(
            response.iter_content(chunk_size=8192),
            content_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={filename}.mp3"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate", methods=["POST"])
@login_required
def generate_legacy_audio():
    file = request.files.get("file")
    filename = request.form.get("filename", "audio").strip()
    rate = request.form.get("rate", "+0%")
    voice = request.form.get("voice", "zh-CN-XiaoxiaoNeural")
    repeat = int(request.form.get("repeat", 1))

    df = pd.read_excel(file)
    items = []
    for _, row in df.iterrows():
        items.append({"en": str(row["English"]), "zh": str(row.get("Chinese", ""))})

    try:
        response = requests.post(
            "http://127.0.0.1:8000/generate-audio",
            json={"items": items, "repeat": repeat, "rate": rate, "voice": voice},
            stream=True
        )
        if response.status_code != 200:
             return f"Error: {response.text}", 500

        return Response(
            response.iter_content(chunk_size=8192),
            content_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={filename}.mp3"}
        )
    except Exception as e:
        return f"System Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)