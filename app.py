from flask import request, send_file
import pandas as pd
import tempfile
import os
import asyncio
from flask import Flask, render_template, send_from_directory

# ===== Services =====
from services.library_service import (
    init_db,
    save_user_upload_with_db,
    get_all_materials
)
from services.audio_service import AudioServiceClient

app = Flask(__name__)

# =====================================================
# 路径配置
# =====================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBRARY_PATH = os.path.join(BASE_DIR, "library")

# =====================================================
# 初始化
# =====================================================
init_db()

if not os.path.exists(LIBRARY_PATH):
    os.makedirs(LIBRARY_PATH)

# 音频服务客户端
audio_client = AudioServiceClient(base_url="http://127.0.0.1:8000")

# =====================================================
# 首页
# =====================================================
@app.route("/")
def index():
    return render_template("index.html")

# =====================================================
# 📚 资料管理（上传 + 入库 + 列表）
# =====================================================
@app.route("/library", methods=["GET", "POST"])
def library():
    success = None
    error = None

    # ---------- 处理上传 ----------
    if request.method == "POST":
        file = request.files.get("material_file")

        if not file or file.filename == "":
            error = "未选择文件"
        else:
            ok = save_user_upload_with_db(file, LIBRARY_PATH)
            if ok:
                success = "文件上传并成功入库"
            else:
                error = "文件类型不被允许（pdf / docx / xlsx / pptx / txt）"

    # ---------- 查询数据库 ----------
    materials = get_all_materials()

    # ⚠️ 这里是关键：直接把 materials 传给 Jinja
    return render_template(
        "library.html",
        materials=materials,
        success=success,
        error=error
    )

# =====================================================
# ⬇️ 下载资料
# =====================================================
@app.route("/library/download/<int:material_id>")
def download_material(material_id):
    """
    根据数据库 id 下载文件
    """
    materials = get_all_materials()
    target = None

    for m in materials:
        if m["id"] == material_id:
            target = m
            break

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

    # 1️⃣ 调 API 生成
    generated_file = audio_client.generate_audio(
        items=items,
        repeat=repeat,
        rate=rate,
        voice=voice
    )

    # 2️⃣ 直接从 MP3 API 拉流
    download_url = f"http://127.0.0.1:8000/download/{generated_file}"
    r = requests.get(download_url, stream=True)
    r.raise_for_status()

    # 3️⃣ 直接返回给浏览器（触发下载）
    return Response(
        r.iter_content(chunk_size=8192),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.mp3"',
            "Content-Type": "audio/mpeg"
        }
    )



# =====================================================
# 启动
# =====================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
