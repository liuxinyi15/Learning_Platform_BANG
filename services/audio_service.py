import os
import requests
from typing import List, Dict


class AudioServiceClient:
    """
    Client for the external Proprietary MP3 Generation API.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        storage_dir: str | None = None
    ):
        self.base_url = base_url.rstrip("/")

        # 平台本地存储音频的位置
        self.storage_dir = storage_dir or os.path.join(
            os.getcwd(), "library", "audio"
        )

        os.makedirs(self.storage_dir, exist_ok=True)

    def generate_audio(
        self,
        items: List[Dict[str, str]],
        repeat: int = 1,
        rate: str = "+0%",
        voice: str = "zh-CN-XiaoxiaoNeural"
    ) -> str:
        """
        Call MP3 Generation API, download generated mp3,
        save it locally, and return filename.
        """

        payload = {
            "items": items,
            "repeat": repeat,
            "rate": rate,
            "voice": voice
        }

        # ① 调用 FastAPI
        response = requests.post(
            f"{self.base_url}/generate-audio",
            json=payload,
            timeout=120
        )
        response.raise_for_status()

        data = response.json()
        filename = data["file"]

        # ② 从 MP3 API 下载音频文件
        download_url = f"{self.base_url}/download/{filename}"

        audio_resp = requests.get(download_url, stream=True)
        audio_resp.raise_for_status()

        local_path = os.path.join(self.storage_dir, filename)

        with open(local_path, "wb") as f:
            for chunk in audio_resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # ③ 返回给 app.py（它完全不用知道细节）
        return filename
