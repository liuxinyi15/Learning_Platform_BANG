from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import io

app = Flask(__name__, template_folder='.') # 注意：这表示在当前文件夹找HTML
CORS(app)

storage = {"student_results": None, "error_records": {}, "question_bank": None}

@app.route('/')
def index():
    # 确保这里的文件名和你文件夹里的一模一样
    return render_template('index.html')

@app.route('/upload_data', methods=['POST'])
def upload_data():
    try:
        files = request.files
        df_student = pd.read_excel(files['student_ans'])
        df_standard = pd.read_excel(files['standard_ans'])
        
        # 清洗列名，防止空格报错
        df_student.columns = df_student.columns.str.strip()
        df_standard.columns = df_standard.columns.str.strip()
        
        error_map = {}
        scored_data = []

        for _, row in df_student.iterrows():
            name = str(row['姓名']).strip()
            total_score = 0
            wrongs = []
            for _, std in df_standard.iterrows():
                q_id = str(std['题号']).strip()
                correct_ans = str(std['正确答案']).strip()
                student_ans = str(row.get(q_id, "")).strip()
                if student_ans == correct_ans:
                    total_score += std['分值']
                else:
                    wrongs.append(q_id)
            error_map[name] = wrongs
            scored_data.append({"姓名": name, "总分": total_score})

        storage["error_records"] = error_map
        if 'question_bank' in files:
            storage["question_bank"] = pd.read_excel(files['question_bank'])

        return jsonify({"message": "Success", "students": list(error_map.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_errors/<student_name>', methods=['GET'])
def get_errors(student_name):
    wrongs = storage["error_records"].get(student_name, [])
    return jsonify({"wrong_questions": wrongs})

@app.route('/download_error_book/<student_name>', methods=['GET'])
def download_error_book(student_name):
    wrongs = storage["error_records"].get(student_name, [])
    bank = storage["question_bank"]
    if bank is None: return "未上传题库", 404
    bank.columns = bank.columns.str.strip()
    personal_df = bank[bank['题号'].astype(str).isin(map(str, wrongs))]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        personal_df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"{student_name}_错题本.xlsx")

if __name__ == '__main__':
    # 强制在 5000 端口启动
    print("--- 程序正在启动，请不要关闭此窗口 ---")
    app.run(host='127.0.0.1', port=5000, debug=True)