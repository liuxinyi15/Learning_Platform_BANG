from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import io
import logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__, template_folder='.')
CORS(app)

# 全局存储（建议仅用于本地演示）
storage = {"error_records": {}, "question_bank": None}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_data', methods=['POST'])
def upload_data():
    try:
        files = request.files
        df_student = pd.read_excel(files['student_ans'])
        df_bank = pd.read_excel(files['combined_bank'])
        
        # 1. 深度清洗表头
        df_student.columns = df_student.columns.astype(str).str.strip()
        df_bank.columns = df_bank.columns.astype(str).str.strip()
        
        # 2. 智能定位题库列
        col_map = {}
        for col in df_bank.columns:
            if '题号' in col: col_map['q_id'] = col
            if '正确答案' in col or '答案' in col: col_map['ans'] = col
            if '分值' in col or '分数' in col: col_map['score'] = col

        # 3. 建立标准答案映射
        ans_map = dict(zip(df_bank[col_map['q_id']].astype(str), df_bank[col_map['ans']].astype(str)))
        score_map = dict(zip(df_bank[col_map['q_id']].astype(str), df_bank[col_map['score']]))
        
        error_map = {}
        for _, row in df_student.iterrows():
            # 找到“姓名”列，如果没有则取第一列
            name_col = [c for c in df_student.columns if '姓名' in c]
            name = str(row[name_col[0]]).strip() if name_col else str(row.iloc[0]).strip()
            
            wrongs = []
            total_score = 0
            
            # 4. 智能匹配题号（解决 Q1 vs QQ1 问题）
            for q_id, correct_ans in ans_map.items():
                # 尝试直接找 (Q1)，找不到则尝试模糊找包含数字的列 (如 QQ1)
                student_ans = ""
                if q_id in df_student.columns:
                    student_ans = str(row[q_id]).strip()
                else:
                    # 尝试寻找包含该数字后缀的列，例如 q_id是"Q1"，匹配答题卡的"QQ1"
                    digit_id = ''.join(filter(str.isdigit, q_id))
                    matched_col = [c for c in df_student.columns if digit_id == ''.join(filter(str.isdigit, c))]
                    if matched_col:
                        student_ans = str(row[matched_col[0]]).strip()

                # 5. 判分
                if student_ans.upper() == correct_ans.upper():
                    total_score += score_map.get(q_id, 0)
                else:
                    wrongs.append(q_id)
            
            error_map[name] = {"wrongs": wrongs, "score": total_score}

        storage["error_records"] = error_map
        storage["question_bank"] = df_bank 

        return jsonify({"status": "success", "students": list(error_map.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_errors/<student_name>', methods=['GET'])
def get_errors(student_name):
    record = storage["error_records"].get(student_name)
    if not record:
        return jsonify({"error": "未找到记录"}), 404
    return jsonify({
        "wrong_questions": record["wrongs"],
        "total_score": record["score"]
    })

@app.route('/download_error_book/<student_name>', methods=['GET'])
def download_error_book(student_name):
    record = storage["error_records"].get(student_name)
    bank = storage["question_bank"]
    
    if not record or bank is None:
        return "数据丢失，请重新上传", 404

    # 筛选该生错题，保留题库中所有的列（包含解析、题目内容等）
    personal_df = bank[bank['题号'].astype(str).isin(map(str, record["wrongs"]))]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        personal_df.to_excel(writer, index=False)
    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{student_name}_个人错题本.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)