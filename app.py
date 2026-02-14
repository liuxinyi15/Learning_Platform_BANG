from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response, jsonify, flash, abort, send_file
import os
import pandas as pd
import requests
import json
import io
import logging
import glob
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
# 📊 Performance Analysis Logic
# ===========================
# 定义成绩数据存储目录
PERFORMANCE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'performance_data')
if not os.path.exists(PERFORMANCE_DIR):
    os.makedirs(PERFORMANCE_DIR)

def get_class_file_path(class_name):
    """Helper: Get CSV path for a specific class"""
    safe_name = "".join([c for c in class_name if c.isalpha() or c.isdigit() or c==' ']).strip()
    return os.path.join(PERFORMANCE_DIR, f"{safe_name}.csv")

def generate_unified_performance_response(history_df, selected_exams):
    """Core Engine: Generate comparison data for multiple exams"""
    if history_df.empty: return {'error': 'No data'}
    
    # Filter selected exams
    df_selected = history_df[history_df['Exam'].isin(selected_exams)]
    if df_selected.empty: return {'error': 'Selected exams not found'}
    
    exclude_cols = ['Name', 'Exam', 'Total']
    all_subjects = [c for c in history_df.columns if c not in exclude_cols]
    # Filter columns that actually exist and have non-zero values
    valid_subjects = [sub for sub in all_subjects if sub in df_selected.columns and (pd.to_numeric(df_selected[sub], errors='coerce').fillna(0) != 0).any()]

    students = df_selected['Name'].unique().tolist()
    
    # Calc max scores
    max_scores = {}
    for sub in valid_subjects:
        try: max_scores[sub] = float(history_df[sub].max())
        except: max_scores[sub] = 100

    bar_series = []
    radar_series = []
    student_details = {stu: {} for stu in students}
    class_averages = {}

    # Sort students by total score of the last exam
    if selected_exams:
        last_exam = selected_exams[-1]
        df_last = df_selected[df_selected['Exam'] == last_exam]
        sorting_totals = []
        for stu in students:
            row = df_last[df_last['Name'] == stu]
            sorting_totals.append(sum(float(row.iloc[0][sub]) for sub in valid_subjects) if not row.empty else 0)
        sorted_pairs = sorted(zip(students, sorting_totals), key=lambda x: x[1], reverse=True)
        students = [p[0] for p in sorted_pairs]

    for exam in selected_exams:
        df_exam = df_selected[df_selected['Exam'] == exam]
        if df_exam.empty: continue

        avgs = [round(float(df_exam[sub].mean()), 2) if not df_exam[sub].empty else 0 for sub in valid_subjects]
        class_averages[exam] = avgs
        radar_series.append({'value': avgs, 'name': f"{exam} Avg"})

        totals = []
        for stu in students:
            row = df_exam[df_exam['Name'] == stu]
            if not row.empty:
                t = sum(float(row.iloc[0][sub]) for sub in valid_subjects if sub in row.columns)
                totals.append(round(t, 2))
                student_details[stu][exam] = {sub: float(row.iloc[0][sub]) for sub in valid_subjects if sub in row.columns}
            else:
                totals.append(0)
                student_details[stu][exam] = {sub: 0 for sub in valid_subjects}

        bar_series.append({
            'name': exam, 'type': 'bar', 'data': totals,
            'label': {'show': True, 'position': 'top'}
        })

    return {
        'success': True, 'exam_names': selected_exams, 'students': students,
        'valid_subjects': valid_subjects, 'max_scores': max_scores,
        'bar_series': bar_series, 'radar_series': radar_series,
        'student_details': student_details, 'class_averages': class_averages
    }

# ===========================
# 📦 Smart Grading Storage
# ===========================
correction_storage = {
    "error_records": {}, "question_bank": None, "paper_total_score": 0, 
    "col_map": {}, "all_questions_info": [], "question_error_counts": {}
}
def clean_ans(val):
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

class User(UserMixin):
    def __init__(self, id, username, is_admin=0):
        self.id = id; self.username = username; self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id):
    row = get_user_by_id(user_id)
    return User(row[0], row[1], row[2]) if row else None

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
# Init (已修复缺失变量)
# ===========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBRARY_PATH = os.path.join(BASE_DIR, "library")  # 🔥 补回了这一行

init_db()
if not os.path.exists(LIBRARY_PATH): os.makedirs(LIBRARY_PATH)

# ===========================
# 📊 Performance Routes
# ===========================
@app.route("/performance")
@login_required
def performance_page():
    return render_template("performance.html")

# --- Class Management ---
@app.route('/api/performance/classes', methods=['GET'])
@login_required
def get_classes():
    files = glob.glob(os.path.join(PERFORMANCE_DIR, "*.csv"))
    classes = [os.path.basename(f).replace('.csv', '') for f in files]
    classes.sort()
    return jsonify({'classes': classes})

@app.route('/api/performance/classes', methods=['POST'])
@login_required
def create_class():
    class_name = request.json.get('class_name', '').strip()
    if not class_name: return jsonify({'error': 'Invalid name'})
    path = get_class_file_path(class_name)
    if os.path.exists(path): return jsonify({'error': 'Class already exists'})
    # Create empty DF with header
    pd.DataFrame(columns=['Name', 'Exam']).to_csv(path, index=False)
    return jsonify({'success': True})

# --- Exam Management ---
@app.route('/api/performance/exams', methods=['GET'])
@login_required
def get_performance_exams():
    class_name = request.args.get('class_name')
    if not class_name: return jsonify({'error': 'Class name required'})
    
    path = get_class_file_path(class_name)
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if df.empty or 'Exam' not in df.columns: return jsonify({'success': True, 'exams': []})
            
            exams = df['Exam'].dropna().unique().tolist()
            if not exams: return jsonify({'success': True, 'exams': []})
            
            exclude_cols = ['Name', 'Exam', 'Total']
            all_subjects = [c for c in df.columns if c not in exclude_cols]
            trend_data = {'exams': exams, 'averages': {}}
            
            for sub in all_subjects:
                if pd.to_numeric(df[sub], errors='coerce').notna().any():
                    avgs = df.groupby('Exam', sort=False)[sub].mean().round(2)
                    trend_data['averages'][sub] = [avgs.get(e, 0) for e in exams]
                    
            return jsonify({'success': True, 'exams': exams, 'trend_data': trend_data})
        except Exception: return jsonify({'success': True, 'exams': []})
    return jsonify({'success': True, 'exams': []})

@app.route('/api/performance/delete', methods=['POST'])
@login_required
def delete_performance_exam():
    data = request.json
    class_name = data.get('class_name')
    exam_name = data.get('exam_name')
    path = get_class_file_path(class_name)
    
    if os.path.exists(path):
        df = pd.read_csv(path)
        df = df[df['Exam'] != exam_name]
        df.to_csv(path, index=False)
        return jsonify({'success': True})
    return jsonify({'error': 'File not found'})

@app.route('/api/performance/compare', methods=['POST'])
@login_required
def compare_performance_exams():
    data = request.json
    class_name = data.get('class_name')
    exam_names = data.get('exam_names', [])
    path = get_class_file_path(class_name)
    
    if not os.path.exists(path): return jsonify({'error': 'Class data not found'})
    return jsonify(generate_unified_performance_response(pd.read_csv(path), exam_names))

@app.route('/api/performance/upload', methods=['POST'])
@login_required
def upload_performance_file():
    if 'file' not in request.files: return jsonify({'error': 'No file found'})
    file = request.files['file']
    exam_name = request.form.get('exam_name', 'Unnamed Exam').strip()
    class_name = request.form.get('class_name', '').strip()
    
    if not class_name: return jsonify({'error': 'Class not specified'})
    path = get_class_file_path(class_name)
    
    try:
        if file.filename.endswith('.csv'): df = pd.read_csv(file)
        elif file.filename.endswith(('.xlsx', '.xls')): df = pd.read_excel(file, engine='openpyxl')
        else: return jsonify({'error': 'Unsupported format'})
        
        df = df.fillna(0)
        df.rename(columns={df.columns[0]: 'Name'}, inplace=True)
        
        subjects = [col for col in df.columns if col != 'Name']
        for sub in subjects: 
            df[sub] = pd.to_numeric(df[sub], errors='coerce').fillna(0)

        df['Exam'] = exam_name
        
        if os.path.exists(path):
            history = pd.read_csv(path)
            history = history[history['Exam'] != exam_name]
            history = pd.concat([history, df], ignore_index=True).fillna(0)
        else: 
            history = df
            
        history.to_csv(path, index=False)
        return jsonify(generate_unified_performance_response(history, [exam_name]))
    except Exception as e: return jsonify({'error': f'Error: {str(e)}'})

# --- Grade Dashboard ---
@app.route('/api/performance/grade_overview', methods=['GET'])
@login_required
def get_grade_overview():
    files = glob.glob(os.path.join(PERFORMANCE_DIR, "*.csv"))
    all_exams = set()
    for f in files:
        try:
            df = pd.read_csv(f)
            if 'Exam' in df.columns:
                all_exams.update(df['Exam'].dropna().unique())
        except: pass
    return jsonify({'exams': sorted(list(all_exams))})

@app.route('/api/performance/compare_grade', methods=['POST'])
@login_required
def compare_grade_performance():
    exam_name = request.json.get('exam_name')
    files = glob.glob(os.path.join(PERFORMANCE_DIR, "*.csv"))
    
    class_stats = []
    
    for f in files:
        class_name = os.path.basename(f).replace('.csv', '')
        try:
            df = pd.read_csv(f)
            df_exam = df[df['Exam'] == exam_name]
            
            if not df_exam.empty:
                exclude = ['Name', 'Exam', 'Total']
                subjects = [c for c in df.columns if c not in exclude]
                
                if 'Total' not in df_exam.columns:
                    df_exam['Total'] = df_exam[subjects].sum(axis=1)
                
                avg_total = df_exam['Total'].mean()
                max_total = df_exam['Total'].max()
                
                class_stats.append({
                    'class': class_name,
                    'avg_total': round(avg_total, 2),
                    'max_total': round(max_total, 2),
                    'student_count': len(df_exam)
                })
        except: pass
        
    return jsonify({'exam': exam_name, 'stats': class_stats})

# ===========================
# 📝 Grading Routes
# ===========================
@app.route('/api/correction/upload', methods=['POST'])
@login_required
def correction_upload():
    try:
        files = request.files
        if 'student_ans' not in files or 'combined_bank' not in files:
            return jsonify({"error": "Missing files"}), 400
        
        # 读取文件
        df_s = pd.read_excel(files['student_ans']).dropna(how='all')
        df_b = pd.read_excel(files['combined_bank']).dropna(how='all')
        
        # 1. 清洗列名 (去除空格，转字符串)
        df_s.columns = df_s.columns.astype(str).str.strip()
        df_b.columns = df_b.columns.astype(str).str.strip()
        
        # 2. 智能映射题库列名 (针对您的文件做了优化)
        col_map = {}
        for c in df_b.columns:
            cl = str(c).strip().lower()
            # 识别题号
            if any(k in cl for k in ['题号', 'question', 'q_id', 'no.', 'id']): 
                col_map['q_id'] = c
            # 识别答案 (加入 '正确答案')
            if any(k in cl for k in ['正确答案', '答案', 'answer', 'ans', 'key']): 
                col_map['ans'] = c
            # 识别分数 (加入 '得分')
            if any(k in cl for k in ['分值', '分数', '得分', 'score', 'points']): 
                col_map['score'] = c
        
        # 检查是否缺少关键列
        if len(col_map) < 3:
            missing = []
            if 'q_id' not in col_map: missing.append("题号")
            if 'ans' not in col_map: missing.append("答案")
            if 'score' not in col_map: missing.append("得分")
            return jsonify({"error": f"题库文件缺少关键列: {', '.join(missing)}"}), 400
            
        correction_storage["col_map"] = col_map
        
        # 3. 提取有效题目数据
        # 过滤掉总分行或无效行
        valid_b = df_b[df_b[col_map['q_id']].notna()].copy()
        
        # 构建映射字典
        # ans_map: { 'Q1': 'A', 'Q2': 'B' ... }
        ans_map = dict(zip(valid_b[col_map['q_id']].astype(str), valid_b[col_map['ans']]))
        # score_map: { 'Q1': 5, 'Q2': 5 ... }
        score_map = dict(zip(valid_b[col_map['q_id']].astype(str), valid_b[col_map['score']]))
        
        correction_storage["paper_total_score"] = float(valid_b[col_map['score']].sum())
        
        # 4. 收集题目内容 (用于前端展示)
        all_info = []
        # 尝试寻找题目内容列
        q_content_col = next((c for c in df_b.columns if any(k in str(c) for k in ['内容', 'content', 'text', 'title'])), None)
        
        for qid in ans_map:
            c = "No Content"
            if q_content_col:
                r = df_b[df_b[col_map['q_id']].astype(str) == qid]
                if not r.empty: 
                    c = str(r.iloc[0][q_content_col])
            all_info.append({"q_id": qid, "content": c})
        correction_storage["all_questions_info"] = all_info

        # 5. 核心批改逻辑 (重点修改了这里的匹配算法)
        err_map = {}
        q_err_counts = {q: 0 for q in ans_map}
        
        # 预处理：建立 "纯数字 -> 答题卡列名" 的映射
        # 例如：您的答题卡有 'QQ1', 'QQ2'。我们将建立映射 { '1': 'QQ1', '2': 'QQ2' ... }
        student_cols_map = {}
        for col in df_s.columns:
            # 提取列名中的数字
            digits = ''.join(filter(str.isdigit, col))
            if digits:
                student_cols_map[digits] = col

        for _, row in df_s.iterrows():
            # 假设第一列始终是学生姓名
            name = str(row.iloc[0]).strip()
            if not name or name.lower() == 'nan': continue
            
            wrongs = []
            score = 0
            
            for qid_bank, corr_ans in ans_map.items():
                u_ans = ""
                
                # 策略 A: 直接匹配 (如果题库是 Q1，答题卡也是 Q1)
                if qid_bank in df_s.columns:
                    u_ans = row[qid_bank]
                else:
                    # 策略 B: 纯数字匹配 (解决 Q1 与 QQ1 不对应的问题)
                    # 提取题库题号的数字 (Q1 -> 1)
                    bank_digit = ''.join(filter(str.isdigit, str(qid_bank)))
                    
                    # 在答题卡中找对应数字的列
                    if bank_digit in student_cols_map:
                        target_col = student_cols_map[bank_digit]
                        u_ans = row[target_col]
                
                # 判分
                if clean_ans(u_ans) == clean_ans(corr_ans):
                    score += score_map.get(qid_bank, 0)
                else:
                    wrongs.append(qid_bank)
                    q_err_counts[qid_bank] += 1
            
            err_map[name] = {"wrongs": wrongs, "score": score}
        
        correction_storage.update({
            "error_records": err_map, 
            "question_bank": df_b, 
            "question_error_counts": q_err_counts
        })
        
        return jsonify({
            "status": "success", 
            "students": list(err_map.keys()), 
            "paper_total": correction_storage["paper_total_score"], 
            "question_error_counts": q_err_counts
        })
        
    except Exception as e:
        logging.error(f"Upload Error: {str(e)}")
        return jsonify({"error": f"处理失败: {str(e)}"}), 500
        
@app.route('/api/correction/get_student/<name>')
@login_required
def correction_get_student(name):
    rec = correction_storage["error_records"].get(name)
    if not rec: return jsonify({"error":"Not found"}),404
    return jsonify({"wrong_questions":rec["wrongs"], "total_score":rec["score"], "paper_total":correction_storage["paper_total_score"]})

@app.route('/api/correction/download/student/<name>')
@login_required
def correction_dl_student(name):
    rec = correction_storage["error_records"].get(name)
    bank = correction_storage["question_bank"]
    if not rec or bank is None: return "Error",404
    col_q = correction_storage["col_map"].get('q_id', bank.columns[0])
    df = bank[bank[col_q].astype(str).isin(map(str, rec["wrongs"]))]
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w: df.to_excel(w, index=False)
    out.seek(0)
    return send_file(out, as_attachment=True, download_name=f"{name}_Errors.xlsx")

@app.route('/api/correction/download/all')
@login_required
def correction_dl_all():
    if not correction_storage["error_records"]: return "No data",404
    data = [{"Name":k, "Score":v["score"]} for k,v in correction_storage["error_records"].items()]
    df = pd.DataFrame(data).sort_values(by="Score", ascending=False)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w: df.to_excel(w, index=False)
    out.seek(0)
    return send_file(out, as_attachment=True, download_name="Class_Scores.xlsx")

# ===========================
# Standard Routes
# ===========================
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    if request.method=="POST":
        u, p, r = request.form.get("new_username"), request.form.get("new_password"), request.form.get("role")
        if create_user(u, p, 1 if r=='admin' else 0): flash("Created!", "success")
        else: flash("Exists!", "error")
        return redirect(url_for('admin_dashboard'))
    return render_template("admin.html", users=get_all_users(), materials=get_materials(None))

@app.route("/admin/promote/<int:uid>")
@admin_required
def admin_promote(uid): update_user_role(uid,1); return redirect(url_for('admin_dashboard'))

@app.route("/admin/demote/<int:uid>")
@admin_required
def admin_demote(uid):
    if uid==1 or uid==current_user.id: flash("Cannot demote", "error")
    else: update_user_role(uid,0)
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_user/<int:uid>")
@admin_required
def admin_del_u(uid):
    if uid==1 or uid==current_user.id: flash("Cannot delete", "error")
    else: delete_user_by_id(uid)
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
    if request.method=="POST":
        act, u, p = request.form.get('action'), request.form.get('username'), request.form.get('password')
        if act=='register':
            if create_user(u,p): flash('Registered!', 'success')
            else: flash('Username taken', 'error')
        else:
            data = verify_user(u,p)
            if data: login_user(User(data['id'], u, data['is_admin'])); return redirect(url_for('index'))
            else: flash('Invalid credentials', 'error')
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route("/")
@login_required
def index(): return render_template("index.html", user=current_user)

@app.route("/library", methods=["GET", "POST"])
@login_required
def library():
    success = None
    error = None
    
    # 1. 处理上传逻辑 (保持不变)
    if request.method == "POST":
        files = request.files.getlist("material_file")
        cover = request.files.get("cover_file")
        select_mode = request.form.get("category_mode")
        selected_cat = request.form.get("category_select")
        new_cat = request.form.get("category_new")
        final_category = new_cat if (select_mode == "new" and new_cat) else (selected_cat or "General")

        if not files or files[0].filename == "":
            error = "No file selected."
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

    # 2. 获取数据 & 🔥 核心修复：将 SQLite Row 转为字典 (Dict)
    sort_option = request.args.get('sort', 'newest')
    active_tab = request.args.get('tab', 'official')
    
    # 获取原始数据
    raw_official = get_materials(uploader_type='System', sort_by=sort_option)
    raw_user = get_materials(uploader_type='User', sort_by=sort_option)
    
    # 🔥 强制转换为字典列表，否则前端 Vue 无法解析 (tojson 会报错)
    official_materials = [dict(row) for row in raw_official]
    user_materials = [dict(row) for row in raw_user]
    
    categories = get_all_categories()
    
    return render_template("library.html", 
                         official_materials=official_materials, 
                         user_materials=user_materials, 
                         categories=categories, 
                         active_tab=active_tab, 
                         sort_option=sort_option, 
                         success=success, 
                         error=error)

# ===========================
# 📚 Library 下载功能 (修复版)
# ===========================
# ===========================
# 📚 Library 下载功能 (修复版)
# ===========================
@app.route("/library/download/<int:material_id>")
@login_required
def download_material(material_id):
    try:
        # 1. 获取所有素材并查找目标 ID
        # 传入 None 表示获取所有类型(Official/User)
        rows = get_materials(None)
        
        # 转换为字典并查找
        target = next((dict(m) for m in rows if m['id'] == material_id), None)
        
        if target is None:
            return "错误：数据库中找不到该文件记录", 404
            
        # 2. 获取并修复文件路径
        file_path = target["file_path"]
        
        # 🔥 关键修复：确保路径是绝对路径
        # 如果数据库存的是相对路径，我们需要把它拼接到项目的根目录下
        if not os.path.isabs(file_path):
            base_dir = os.path.abspath(os.path.dirname(__file__))
            file_path = os.path.join(base_dir, file_path)
        
        # 3. 检查服务器上文件是否真的存在
        if not os.path.exists(file_path):
            return f"错误：服务器物理文件丢失 (路径: {file_path})", 404

        # 4. 获取文件名并处理
        filename = os.path.basename(file_path)
        
        # 5. 发送文件
        # 使用 send_file 是最稳妥的方式，它可以自动处理大部分流媒体和下载头
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            conditional=True  # 支持断点续传，防止大文件下载中断
        )
        
    except Exception as e:
        logging.error(f"Library Download Error: {e}")
        return f"下载服务出错: {str(e)}", 500
        
@app.route("/planner")
@login_required
def planner(): return render_template("planner.html")

@app.route("/vocabulary")
@login_required
def vocabulary(): return render_template("vocab.html")

@app.route("/audio")
@login_required
def audio_page(): return render_template("audio.html")
@app.route("/correction")
@login_required
def correction_page(): return render_template("correction.html")

@app.route("/api/generate_audio_json", methods=["POST"])
@login_required
def gen_audio_json():
    d = request.json
    try:
        r = requests.post("http://127.0.0.1:8000/generate-audio", json={"items":[{"en":i.get("English"),"zh":i.get("Chinese")} for i in d.get("items",[])], "repeat":d.get("repeat",1), "rate":d.get("rate","+0%"), "voice":d.get("voice")}, stream=True)
        return Response(r.iter_content(8192), content_type="audio/mpeg", headers={"Content-Disposition": f"attachment; filename={d.get('filename')}.mp3"})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/generate", methods=["POST"])
@login_required
def gen_audio_legacy():
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

@app.route("/change_password", methods=["GET","POST"])
@login_required
def change_password():
    if request.method=="POST":
        np, cp = request.form.get("new_password"), request.form.get("confirm_password")
        if len(np)<6 or np!=cp: flash("Invalid password", "error")
        else: 
            admin_reset_password(current_user.id, np)
            logout_user()
            flash("Password changed", "success")
            return redirect(url_for("login"))
    return render_template("change_password.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)