from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import io
import logging

# 初始化配置
logging.basicConfig(level=logging.INFO)
app = Flask(__name__, template_folder='.', static_folder='static')
CORS(app)

# 全局存储
storage = {"error_records": {}, "question_bank": None, "paper_total_score": 0, "col_map": {}, "all_questions_info": []}

def clean_ans(val):
    """处理 Excel 中的 .0 浮点数、空格和大小写"""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s.upper()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_data', methods=['POST'])
def upload_data():
    try:
        files = request.files
        if 'student_ans' not in files or 'combined_bank' not in files:
            return jsonify({"error": "请确保上传了学生答题卡和综合题库两个文件"}), 400

        df_student = pd.read_excel(files['student_ans']).dropna(how='all')
        df_bank = pd.read_excel(files['combined_bank']).dropna(how='all')
        
        df_student.columns = df_student.columns.astype(str).str.strip()
        df_bank.columns = df_bank.columns.astype(str).str.strip()
        
        col_map = {}
        for col in df_bank.columns:
            c = str(col).strip().lower() # 统一转小写去空格
            if any(k in c for k in ['题号', 'question', 'q_id', 'no.']): 
                col_map['q_id'] = col
            if any(k in c for k in ['答案', 'answer', 'ans']): 
                col_map['ans'] = col
            if any(k in c for k in ['分值', '分数', '得分', 'score']): 
                col_map['score'] = col

        if len(col_map) < 3:
            return jsonify({"error": "题库列名不匹配！请确保包含：题号、正确答案、分值（或得分）"}), 400

        storage["col_map"] = col_map

        valid_bank = df_bank[
            df_bank[col_map['q_id']].notna() & 
            (~df_bank[col_map['q_id']].astype(str).str.contains('总分|合计|得分|nan|统计', na=False))
        ].copy()

        ans_map = dict(zip(valid_bank[col_map['q_id']].astype(str), valid_bank[col_map['ans']]))
        score_map = dict(zip(valid_bank[col_map['q_id']].astype(str), valid_bank[col_map['score']]))
        
        paper_total = float(valid_bank[col_map['score']].sum())
        storage["paper_total_score"] = paper_total
        
        # --- 新增：收集所有题目的信息，用于错题分布图 ---
        all_questions_info = []
        q_content_col = [c for c in df_bank.columns if '题目内容' in str(c) or 'Content' in str(c)][0] if [c for c in df_bank.columns if '题目内容' in str(c) or 'Content' in str(c)] else None

        for q_id in ans_map.keys():
            content = "无题目内容"
            if q_content_col and q_id in df_bank[col_map['q_id']].astype(str).values:
                # 找到对应题号的行
                q_row = df_bank[df_bank[col_map['q_id']].astype(str) == q_id].iloc[0]
                content = str(q_row[q_content_col]) if pd.notna(q_row[q_content_col]) else "无题目内容"
            
            all_questions_info.append({"q_id": q_id, "content": content})
        
        storage["all_questions_info"] = all_questions_info
        # --- 结束新增 ---

        error_map = {}
        # --- 批改逻辑 ---
        # 用于统计每道题的错误人数
        question_error_counts = {q_id: 0 for q_id in ans_map.keys()}

        # 姓名列的匹配关键词
        name_keywords = ['姓名', 'name', 'student']

        for _, row in df_student.iterrows():
            name_col = [c for c in df_student.columns if any(k in str(c).lower() for k in name_keywords)]
            name = str(row[name_col[0]]).strip() if name_col else str(row.iloc[0]).strip()
            
            if name == 'nan' or not name: continue

            wrongs = []
            total_score = 0
            
            for q_id, correct_ans in ans_map.items():
                student_ans_raw = ""
                # 题号模糊匹配
                if q_id in df_student.columns:
                    student_ans_raw = row[q_id]
                else:
                    digit_id = ''.join(filter(str.isdigit, q_id))
                    matched_col = [c for c in df_student.columns if digit_id != '' and digit_id == ''.join(filter(str.isdigit, c))]
                    if matched_col:
                        student_ans_raw = row[matched_col[0]]

                if clean_ans(student_ans_raw) == clean_ans(correct_ans):
                    total_score += score_map.get(q_id, 0)
                else:
                    wrongs.append(q_id)
                    question_error_counts[q_id] += 1 # 统计错误人数
            
            error_map[name] = {"wrongs": wrongs, "score": total_score}

        storage["error_records"] = error_map
        storage["question_bank"] = df_bank 
        storage["question_error_counts"] = question_error_counts # 存储错误统计

        return jsonify({
            "status": "success", 
            "students": list(error_map.keys()),
            "paper_total": paper_total,
            "all_questions_info": all_questions_info, # 返回所有题目信息
            "question_error_counts": question_error_counts # 返回错误统计
        })
    except Exception as e:
        logging.error(f"处理失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_errors/<student_name>', methods=['GET'])
def get_errors(student_name):
    record = storage["error_records"].get(student_name)
    paper_total = storage.get("paper_total_score", 0)
    if not record: return jsonify({"error": "未找到记录"}), 404
    return jsonify({"wrong_questions": record["wrongs"], "total_score": record["score"], "paper_total": paper_total})

@app.route('/download_error_book/<student_name>', methods=['GET'])
def download_error_book(student_name):
    record = storage["error_records"].get(student_name)
    bank = storage["question_bank"]
    col_map = storage.get("col_map", {})
    if not record or bank is None: return "数据不存在", 404
    q_id_col = col_map.get('q_id', bank.columns[0])
    personal_df = bank[bank[q_id_col].astype(str).isin(map(str, record["wrongs"]))]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        personal_df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"{student_name}_错题本.xlsx")

@app.route('/download_all_scores', methods=['GET'])
def download_all_scores():
    if not storage["error_records"]: return "暂无数据", 404
    data_list = [{"姓名": k, "总分": v["score"]} for k, v in storage["error_records"].items()]
    summary_df = pd.DataFrame(data_list).sort_values(by="总分", ascending=False)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary_df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="全班成绩汇总表.xlsx")

@app.route('/clear_data', methods=['POST'])
def clear_data():
    storage.update({"error_records": {}, "question_bank": None, "paper_total_score": 0, "col_map": {}, "all_questions_info": [], "question_error_counts": {}})
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)