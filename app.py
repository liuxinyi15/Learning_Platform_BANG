from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response, jsonify, flash, abort, send_file
import os
import pandas as pd
import requests
import json
import io
import logging
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps

# Import Services
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
    update_user_role,
    admin_reset_password
)
from services.audio_service import AudioServiceClient

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_this'

# ===========================
# 📦 Smart Grading - Global Storage
# ===========================
correction_storage = {
    "error_records": {}, 
    "question_bank": None, 
    "paper_total_score": 0, 
    "col_map": {}, 
    "all_questions_info": [],
    "question_error_counts": {}
}

def clean_ans(val):
    """Handle .0 floats, whitespace and case in Excel"""
    if pd.isna(val): return ""
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s.upper()

# ===========================
# 🔐 Flask-Login Configuration
# ===========================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "error"

class User(UserMixin):
    def __init__(self, id, username, is_admin=0):
        self.id = id
        self.username = username
        self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id):
    row = get_user_by_id(user_id)
    if row: return User(id=row[0], username=row[1], is_admin=row[2])
    return None

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("Permission Denied: Admins only.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ===========================
# Initialization
# ===========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBRARY_PATH = os.path.join(BASE_DIR, "library")
init_db()
if not os.path.exists(LIBRARY_PATH): os.makedirs(LIBRARY_PATH)

# ===========================
# 📝 Smart Grading Routes
# ===========================
@app.route("/correction")
@login_required
def correction_page():
    return render_template("correction.html")

@app.route('/api/correction/upload', methods=['POST'])
@login_required
def correction_upload():
    try:
        files = request.files
        if 'student_ans' not in files or 'combined_bank' not in files:
            return jsonify({"error": "Please ensure both 'Student Answer Sheet' and 'Question Bank' files are uploaded."}), 400

        df_student = pd.read_excel(files['student_ans']).dropna(how='all')
        df_bank = pd.read_excel(files['combined_bank']).dropna(how='all')
        
        # Clean column names
        df_student.columns = df_student.columns.astype(str).str.strip()
        df_bank.columns = df_bank.columns.astype(str).str.strip()
        
        # Map Columns (Keep Chinese keywords for compatibility, add English if needed)
        col_map = {}
        for col in df_bank.columns:
            c = str(col).strip().lower()
            if any(k in c for k in ['题号', 'question', 'q_id', 'no.']): col_map['q_id'] = col
            if any(k in c for k in ['答案', 'answer', 'ans']): col_map['ans'] = col
            if any(k in c for k in ['分值', '分数', '得分', 'score']): col_map['score'] = col

        if len(col_map) < 3:
            return jsonify({"error": "Question Bank columns mismatch! Must include: Question ID, Answer, Score."}), 400

        correction_storage["col_map"] = col_map

        # Filter valid rows
        valid_bank = df_bank[
            df_bank[col_map['q_id']].notna() & 
            (~df_bank[col_map['q_id']].astype(str).str.contains('总分|合计|得分|nan|Total|Score', na=False))
        ].copy()

        ans_map = dict(zip(valid_bank[col_map['q_id']].astype(str), valid_bank[col_map['ans']]))
        score_map = dict(zip(valid_bank[col_map['q_id']].astype(str), valid_bank[col_map['score']]))
        
        paper_total = float(valid_bank[col_map['score']].sum())
        correction_storage["paper_total_score"] = paper_total
        
        # Collect question content
        all_questions_info = []
        q_content_col = next((c for c in df_bank.columns if '题目内容' in str(c) or 'Content' in str(c)), None)

        for q_id in ans_map.keys():
            content = "No Content"
            if q_content_col and q_id in df_bank[col_map['q_id']].astype(str).values:
                q_row = df_bank[df_bank[col_map['q_id']].astype(str) == q_id].iloc[0]
                content = str(q_row[q_content_col]) if pd.notna(q_row[q_content_col]) else "No Content"
            all_questions_info.append({"q_id": q_id, "content": content})
        
        correction_storage["all_questions_info"] = all_questions_info

        # Grading Logic
        error_map = {}
        question_error_counts = {q_id: 0 for q_id in ans_map.keys()}
        name_keywords = ['姓名', 'name', 'student']

        for _, row in df_student.iterrows():
            name_col = [c for c in df_student.columns if any(k in str(c).lower() for k in name_keywords)]
            name = str(row[name_col[0]]).strip() if name_col else str(row.iloc[0]).strip()
            
            if name == 'nan' or not name: continue

            wrongs = []
            total_score = 0
            
            for q_id, correct_ans in ans_map.items():
                student_ans_raw = ""
                if q_id in df_student.columns:
                    student_ans_raw = row[q_id]
                else:
                    # Fuzzy match question ID (e.g. 1 -> Q1)
                    digit_id = ''.join(filter(str.isdigit, q_id))
                    matched_col = [c for c in df_student.columns if digit_id != '' and digit_id == ''.join(filter(str.isdigit, c))]
                    if matched_col: student_ans_raw = row[matched_col[0]]

                if clean_ans(student_ans_raw) == clean_ans(correct_ans):
                    total_score += score_map.get(q_id, 0)
                else:
                    wrongs.append(q_id)
                    question_error_counts[q_id] += 1
            
            error_map[name] = {"wrongs": wrongs, "score": total_score}

        correction_storage["error_records"] = error_map
        correction_storage["question_bank"] = df_bank 
        correction_storage["question_error_counts"] = question_error_counts

        return jsonify({
            "status": "success", 
            "students": list(error_map.keys()),
            "paper_total": paper_total,
            "all_questions_info": all_questions_info,
            "question_error_counts": question_error_counts
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/correction/get_student/<student_name>')
@login_required
def correction_get_student(student_name):
    record = correction_storage["error_records"].get(student_name)
    paper_total = correction_storage.get("paper_total_score", 0)
    if not record: return jsonify({"error": "Record not found"}), 404
    return jsonify({"wrong_questions": record["wrongs"], "total_score": record["score"], "paper_total": paper_total})

@app.route('/api/correction/download/student/<student_name>')
@login_required
def correction_download_student(student_name):
    record = correction_storage["error_records"].get(student_name)
    bank = correction_storage["question_bank"]
    col_map = correction_storage.get("col_map", {})
    if not record or bank is None: return "Data not found", 404
    
    q_id_col = col_map.get('q_id', bank.columns[0])
    personal_df = bank[bank[q_id_col].astype(str).isin(map(str, record["wrongs"]))]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        personal_df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"{student_name}_ErrorBook.xlsx")

@app.route('/api/correction/download/all')
@login_required
def correction_download_all():
    if not correction_storage["error_records"]: return "No data available", 404
    data_list = [{"Name": k, "Score": v["score"]} for k, v in correction_storage["error_records"].items()]
    summary_df = pd.DataFrame(data_list).sort_values(by="Score", ascending=False)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary_df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="Class_Score_Summary.xlsx")

# ===========================
# Standard Routes (Admin, Login, Library)
# ===========================
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    if request.method == "POST":
        new_username = request.form.get("new_username")
        new_password = request.form.get("new_password")
        role = request.form.get("role")
        is_admin_flag = 1 if role == 'admin' else 0
        if create_user(new_username, new_password, is_admin=is_admin_flag): 
            flash(f"User {new_username} created successfully!", "success")
        else: 
            flash("Creation failed: Username already exists.", "error")
        return redirect(url_for('admin_dashboard'))
    users = get_all_users()
    materials = get_materials(uploader_type=None) 
    return render_template("admin.html", users=users, materials=materials)

@app.route("/admin/promote/<int:user_id>")
@admin_required
def admin_promote(user_id):
    if update_user_role(user_id, 1): flash("Promoted to Administrator.", "success")
    else: flash("Operation failed.", "error")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/demote/<int:user_id>")
@admin_required
def admin_demote(user_id):
    if user_id == current_user.id: flash("You cannot demote yourself!", "error")
    elif user_id == 1: flash("Cannot modify Super Admin permissions.", "error")
    else:
        update_user_role(user_id, 0)
        flash("Demoted to Standard User.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/reset_pwd/<int:user_id>")
@admin_required
def admin_reset_pwd(user_id):
    admin_reset_password(user_id, "123456")
    flash(f"Password for ID {user_id} has been reset to: 123456", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_user/<int:user_id>")
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        flash("You cannot delete yourself!", "error")
        return redirect(url_for('admin_dashboard'))
    if delete_user_by_id(user_id): flash("User deleted.", "success")
    else: flash("Cannot delete this user.", "error")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_material/<int:material_id>")
@admin_required
def admin_delete_material(material_id):
    if delete_material_by_id(material_id): flash("Material permanently deleted.", "success")
    else: flash("Delete failed.", "error")
    return redirect(url_for('admin_dashboard'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == "POST":
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')
        if action == 'register':
            if create_user(username, password): flash('Registration successful! Please log in.', 'success')
            else: flash('Username already exists.', 'error')
        elif action == 'login':
            user_data = verify_user(username, password)
            if user_data:
                user = User(user_data['id'], username, user_data['is_admin'])
                login_user(user)
                return redirect(url_for('index'))
            else: flash('Invalid username or password.', 'error')
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

@app.route("/library", methods=["GET", "POST"])
@login_required
def library():
    success = None
    error = None
    if request.method == "POST":
        files = request.files.getlist("material_file")
        cover = request.files.get("cover_file")
        select_mode = request.form.get("category_mode")
        selected_cat = request.form.get("category_select")
        new_cat = request.form.get("category_new")
        final_category = new_cat if (select_mode == "new" and new_cat) else (selected_cat or "General")

        if not files or files[0].filename == "": error = "No file selected."
        else:
            uploader_type = 'System' if current_user.is_admin else 'User'
            success_count = 0
            for file in files:
                if file and file.filename:
                    file.stream.seek(0)
                    if cover: cover.stream.seek(0)
                    if save_user_upload_with_db(file, cover, final_category, LIBRARY_PATH, uploader=uploader_type):
                        success_count += 1
            if success_count > 0: success = f"Successfully uploaded {success_count} files!"
            else: error = "Upload failed."

    sort_option = request.args.get('sort', 'newest')
    active_tab = request.args.get('tab', 'official')
    official_materials = get_materials(uploader_type='System', sort_by=sort_option)
    user_materials = get_materials(uploader_type='User', sort_by=sort_option)
    categories = get_all_categories()
    return render_template("library.html", official_materials=official_materials, user_materials=user_materials, categories=categories, active_tab=active_tab, sort_option=sort_option, success=success, error=error)

@app.route("/library/delete/<int:material_id>")
@login_required
def delete_material(material_id):
    if delete_material_by_id(material_id): return redirect(url_for('library', tab='user'))
    return "Delete failed", 400

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

@app.route("/planner")
@login_required
def planner(): return render_template("planner.html")

@app.route("/vocabulary")
@login_required
def vocabulary(): return render_template("vocab.html")

@app.route("/audio")
@login_required
def audio_page(): return render_template("audio.html")

@app.route("/api/generate_audio_json", methods=["POST"])
@login_required
def generate_audio_from_json():
    data = request.json
    filename = data.get("filename", "vocab_audio")
    items_raw = data.get("items", [])
    formatted_items = [{"en": str(i.get("English","")), "zh": str(i.get("Chinese",""))} for i in items_raw]
    try:
        response = requests.post("http://127.0.0.1:8000/generate-audio", json={"items": formatted_items, "repeat": int(data.get("repeat", 1)), "rate": data.get("rate", "+0%"), "voice": data.get("voice", "zh-CN-XiaoxiaoNeural")}, stream=True)
        if response.status_code != 200: return jsonify({"error": "Audio Service Error", "details": response.text}), response.status_code
        return Response(response.iter_content(chunk_size=8192), content_type="audio/mpeg", headers={"Content-Disposition": f"attachment; filename={filename}.mp3"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/generate", methods=["POST"])
@login_required
def generate_legacy_audio():
    file = request.files.get("file")
    filename = request.form.get("filename", "audio").strip()
    rate = request.form.get("rate", "+0%")
    voice = request.form.get("voice", "zh-CN-XiaoxiaoNeural")
    repeat = int(request.form.get("repeat", 1))
    df = pd.read_excel(file)
    items = [{"en": str(row["English"]), "zh": str(row.get("Chinese", ""))} for _, row in df.iterrows()]
    try:
        response = requests.post("http://127.0.0.1:8000/generate-audio", json={"items": items, "repeat": repeat, "rate": rate, "voice": voice}, stream=True)
        if response.status_code != 200: return f"Error: {response.text}", 500
        return Response(response.iter_content(chunk_size=8192), content_type="audio/mpeg", headers={"Content-Disposition": f"attachment; filename={filename}.mp3"})
    except Exception as e: return f"System Error: {str(e)}", 500

# Settings Route
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        if not new_password or len(new_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("change_password"))
            
        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("change_password"))
        
        from services.library_service import admin_reset_password
        admin_reset_password(current_user.id, new_password)
        
        flash("Password updated successfully! Please log in again.", "success")
        logout_user()
        return redirect(url_for("login"))
        
    return render_template("change_password.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)