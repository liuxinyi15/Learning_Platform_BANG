from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response
import os
import pandas as pd
import requests
import json
# 引入 Service (确保 get_all_categories 被包含在内)
from services.library_service import (
    init_db,
    save_user_upload_with_db,
    get_materials,
    get_all_categories,     # <--- 必须有这个
    delete_material_by_id
)
from services.audio_service import AudioServiceClient

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBRARY_PATH = os.path.join(BASE_DIR, "library")

# 初始化
init_db()
if not os.path.exists(LIBRARY_PATH):
    os.makedirs(LIBRARY_PATH)

# =====================================================
# 🏠 首页 (解决 404 问题)
# =====================================================
@app.route("/")
def index():
    # 恢复这一行，显示主页
    return render_template("index.html")
# =====================================================
# 📅 功能1：备课事项管理 (原 Todo List)
# =====================================================
@app.route("/planner")
def planner():
    return render_template("planner.html")

# =====================================================
# 🔤 功能2：词汇积累与背诵 (新增功能)
# =====================================================
@app.route("/vocabulary")
def vocabulary():
    return render_template("vocab.html")

# =====================================================
# 🔊 API：接收网页词汇表直接生成音频
# =====================================================
@app.route("/api/generate_audio_json", methods=["POST"])
def generate_audio_from_json():
    """
    接收前端发来的 JSON 单词列表，调用音频服务生成 MP3
    数据格式: { "filename": "xxx", "rate": "-10%", "voice": "xxx", "items": [{"English": "apple", "Chinese": "苹果"}, ...] }
    """
    data = request.json
    filename = data.get("filename", "vocab_audio")
    items_raw = data.get("items", [])
    
    # 转换格式以适配 AudioServiceClient
    # 假设 AudioServiceClient 或 8000 端口接受 {"en": "...", "zh": "..."}
    formatted_items = []
    for item in items_raw:
        formatted_items.append({
            "en": str(item.get("English", "")),
            "zh": str(item.get("Chinese", ""))
        })

    # 调用音频生成服务 (假设端口是 8000)
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

        return Response(
            response.iter_content(chunk_size=8192),
            content_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename={filename}.mp3"
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# =====================================================
# 📚 资料管理
# =====================================================
@app.route("/library", methods=["GET", "POST"])
def library():
    success = None
    error = None

    # 1. 处理上传
    if request.method == "POST":
        file = request.files.get("material_file")
        cover = request.files.get("cover_file")
        
        select_mode = request.form.get("category_mode")
        selected_cat = request.form.get("category_select")
        new_cat = request.form.get("category_new")

        final_category = "General"
        if select_mode == "new" and new_cat:
            final_category = new_cat
        elif selected_cat:
            final_category = selected_cat

        if not file or file.filename == "":
            error = "未选择文件"
        else:
            ok = save_user_upload_with_db(file, cover, final_category, LIBRARY_PATH)
            if ok:
                success = "上传成功！"
            else:
                error = "文件类型不被允许"

    # 2. 获取参数
    sort_option = request.args.get('sort', 'newest')
    active_tab = request.args.get('tab', 'official')

    # 3. 查询数据
    official_materials = get_materials(uploader_type='System', sort_by=sort_option)
    user_materials = get_materials(uploader_type='User', sort_by=sort_option)
    categories = get_all_categories() # 这里调用了之前报错的函数

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

# =====================================================
# 🗑️ 删除接口
# =====================================================
@app.route("/library/delete/<int:material_id>")
def delete_material(material_id):
    if delete_material_by_id(material_id):
        return redirect(url_for('library', tab='user'))
    return "删除失败", 400

# =====================================================
# 🖼️ 封面与下载
# =====================================================
@app.route("/library/cover/<int:material_id>")
def get_cover(material_id):
    rows = get_materials()
    target = next((m for m in rows if m['id'] == material_id), None)
            
    if target and target["cover_path"] and os.path.exists(target["cover_path"]):
        directory = os.path.dirname(target["cover_path"])
        filename = os.path.basename(target["cover_path"])
        return send_from_directory(directory, filename)
    return "No Cover", 404

@app.route("/library/download/<int:material_id>")
def download_material(material_id):
    rows = get_materials()
    target = next((m for m in rows if m['id'] == material_id), None)

    if target is None:
        return "File not found", 404

    directory = os.path.dirname(target["file_path"])
    filename = os.path.basename(target["file_path"])
    return send_from_directory(directory, filename, as_attachment=True)

# =====================================================
# 🔊 音频生成接口（给前端 / JS 调用）
# =====================================================

@app.route("/audio")
def audio_page():
    return render_template("audio.html")
@app.route("/generate", methods=["POST"])
def generate_legacy_audio():
    file = request.files.get("file")
    filename = request.form.get("filename", "audio").strip()
    rate = request.form.get("rate", "+0%")
    voice = request.form.get("voice", "zh-CN-XiaoxiaoNeural")
    repeat = int(request.form.get("repeat", 1))

    df = pd.read_excel(file)

    items = []
    for _, row in df.iterrows():
        items.append({
            "en": str(row["English"]),
            "zh": str(row.get("Chinese", ""))
        })

    audio_client = AudioServiceClient()
    response = requests.post(
        "http://127.0.0.1:8000/generate-audio",
        json={
            "items": items,
            "repeat": int(request.form.get("repeat", 1)),
            "rate": request.form.get("rate", "+0%"),
            "voice": request.form.get("voice", "zh-CN-XiaoxiaoNeural")
        },
        stream=True
    )

    # ❗关键：直接把 API 的文件流转发给浏览器
    return Response(
        response.iter_content(chunk_size=8192),
        content_type="audio/mpeg",
        headers={
            "Content-Disposition": f"attachment; filename={filename}.mp3"
        }
    )



# =====================================================
# 启动
# =====================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
