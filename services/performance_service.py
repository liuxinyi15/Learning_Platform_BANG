from flask import Flask, render_template, request, jsonify
import pandas as pd
import os

app = Flask(__name__)
HISTORY_FILE = 'history.csv'

# ======= 核心引擎：组装多场考试的对比数据 =======
def generate_unified_response(history_df, selected_exams):
    # 取出被选中的考试数据
    df_selected = history_df[history_df['Exam'].isin(selected_exams)]
    
    # 获取有效的科目（排除掉全班都是0分的无效列）
    exclude_cols = ['Name', 'Exam', 'Total']
    all_subjects = [c for c in history_df.columns if c not in exclude_cols]
    valid_subjects = [sub for sub in all_subjects if sub in df_selected.columns and (df_selected[sub] != 0).any()]

    students = df_selected['Name'].unique().tolist()
    max_scores = {sub: float(history_df[sub].max()) for sub in valid_subjects}

    bar_series = []
    radar_series = []
    student_details = {stu: {} for stu in students}
    class_averages = {}

    # 按照最后选择的一场考试的总分，给全班学生排个序（降序）
    if selected_exams:
        last_exam = selected_exams[-1]
        df_last = df_selected[df_selected['Exam'] == last_exam]
        sorting_totals = []
        for stu in students:
            row = df_last[df_last['Name'] == stu]
            sorting_totals.append(sum(float(row.iloc[0][sub]) for sub in valid_subjects) if not row.empty else 0)
        
        # 绑定学生和分数并排序
        sorted_pairs = sorted(zip(students, sorting_totals), key=lambda x: x[1], reverse=True)
        students = [p[0] for p in sorted_pairs]

    # 遍历每场被选中的考试，生成对比序列
    for exam in selected_exams:
        df_exam = df_selected[df_selected['Exam'] == exam]
        if df_exam.empty: continue

        # 1. 雷达图：该场考试平均分
        avgs = [round(float(df_exam[sub].mean()), 2) if not df_exam[sub].empty else 0 for sub in valid_subjects]
        class_averages[exam] = avgs
        radar_series.append({'value': avgs, 'name': f"{exam} 平均分"})

        # 2. 柱状图：每个学生在该场考试的总分
        totals = []
        for stu in students:
            row = df_exam[df_exam['Name'] == stu]
            if not row.empty:
                totals.append(round(sum(float(row.iloc[0][sub]) for sub in valid_subjects), 2))
                student_details[stu][exam] = {sub: float(row.iloc[0][sub]) for sub in valid_subjects}
            else:
                totals.append(0)  # 缺考算作0
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

@app.route('/')
def index():
    return render_template('index.html')

# 获取历史考试列表与全局趋势
@app.route('/api/exams', methods=['GET'])
def get_exams():
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        exams = df['Exam'].dropna().unique().tolist()
        if not exams:
            return jsonify({'success': True, 'exams': []})
            
        # 计算全局趋势
        exclude_cols = ['Name', 'Exam', 'Total']
        all_subjects = [c for c in df.columns if c not in exclude_cols]
        trend_data = {'exams': exams, 'averages': {}}
        
        for sub in all_subjects:
            if (df[sub] != 0).any():
                trend_data['averages'][sub] = df.groupby('Exam', sort=False)[sub].mean().round(2).tolist()
                
        return jsonify({'success': True, 'exams': exams, 'trend_data': trend_data})
    return jsonify({'success': True, 'exams': []})

# 删除特定的历史考试
@app.route('/api/delete_exam', methods=['POST'])
def delete_exam():
    exam_name = request.json.get('exam_name')
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        df = df[df['Exam'] != exam_name]
        
        if df.empty:
            os.remove(HISTORY_FILE)
        else:
            df.to_csv(HISTORY_FILE, index=False)
        return jsonify({'success': True})
    return jsonify({'error': '未找到历史数据'})

# 接收多个考试名称进行对比
@app.route('/api/compare_exams', methods=['POST'])
def compare_exams():
    exam_names = request.json.get('exam_names', [])
    if not os.path.exists(HISTORY_FILE): return jsonify({'error': '没有历史数据'})
    if not exam_names: return jsonify({'error': '未选择任何考试'})
    
    history_df = pd.read_csv(HISTORY_FILE)
    return jsonify(generate_unified_response(history_df, exam_names))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': '没有找到文件'})
    file = request.files['file']
    filename = file.filename
    exam_name = request.form.get('exam_name', '未命名考试').strip()
    
    if filename == '': return jsonify({'error': '未选择文件'})
    try:
        if filename.endswith('.csv'): df = pd.read_csv(file)
        elif filename.endswith('.xlsx') or filename.endswith('.xls'): df = pd.read_excel(file, engine='openpyxl')
        else: return jsonify({'error': '不支持的文件格式'})
        
        df = df.fillna(0)
        
        # 智能重命名第一列为Name
        df.rename(columns={df.columns[0]: 'Name'}, inplace=True)
        subjects = [col for col in df.columns if col != 'Name']
        
        # 强制将成绩转换为数字，非数字转为0
        for sub in subjects:
            df[sub] = pd.to_numeric(df[sub], errors='coerce').fillna(0)

        df_history_entry = df.copy()
        df_history_entry['Exam'] = exam_name
        
        # 保存并覆盖同名旧数据
        if os.path.exists(HISTORY_FILE):
            history_df = pd.read_csv(HISTORY_FILE)
            history_df = history_df[history_df['Exam'] != exam_name]
            history_df = pd.concat([history_df, df_history_entry], ignore_index=True).fillna(0)
        else:
            history_df = df_history_entry
            
        history_df.to_csv(HISTORY_FILE, index=False)
        return jsonify(generate_unified_response(history_df, [exam_name]))
        
    except Exception as e:
        return jsonify({'error': f'处理文件时出错: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)