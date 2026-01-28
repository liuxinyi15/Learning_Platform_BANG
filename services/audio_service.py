import requests
from typing import List, Dict

class AudioServiceClient:
    """
    Client for the external Proprietary MP3 Generation API.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def generate_audio(
        self,
        items: List[Dict[str, str]],
        repeat: int = 1,
        rate: str = "+0%",
        voice: str = "zh-CN-XiaoxiaoNeural"
    ) -> str:
        """
        Call MP3 Generation API and return generated mp3 filename.

        items example:
        [
            {"en": "apple", "zh": "苹果"},
            {"en": "banana", "zh": "香蕉"}
        ]
        """

        payload = {
            "items": items,
            "repeat": repeat,
            "rate": rate,
            "voice": voice
        }

        response = requests.post(
            f"{self.base_url}/generate-audio",
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()
        return data["file"]
