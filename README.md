
# 🎓 AI-Powered Language Education Platform - BANG

This is a modular education platform designed to assist teachers and students in English language education. The system integrates AI-generated exercises, audio generation, student performance tracking, and personalized error review — aiming to streamline lesson preparation and student progress management.

## 🔍 Project Overview

The platform is built around four core modules:

### 1. 🔊 MP3 Vocabulary Audio Generator
Generate high-quality MP3 vocabulary audio from Excel files with English-Chinese pairs.
- Adjustable speed, repetition, and pause settings.
- Based on Microsoft's Edge TTS API.
- **👉 This module is developed as a standalone project** and integrated via the repository:  
  [`liuxinyi15/EN-CH-word-transform-to-mp3`](https://github.com/liuxinyi15/EN-CH-word-transform-to-mp3)

### 2. 📊 Student Score Tracking & Personalized Error Review
Upload students' detailed results and automatically identify weak points:
- Compares student scores with full marks per question.
- Auto-generates each student's **personal error book** (错题本).
- Supports visualized performance tracking over time (future version).

### 3. 📚 Teacher Knowledge Base
A lightweight, searchable content management system to store and tag:
- Lesson prep materials (videos, images, exercises).
- Teaching plans and annotations.
- Curriculum-aligned documents and knowledge references.

### 4. 🧠 AI Exercise Generator (Planned)
Automatically generate custom practice questions based on:
- A topic input
- A reference passage or vocabulary list
- Configurable question types (fill-in-the-blank, translation, grammar)

> This module will connect to an AI API (e.g. OpenAI, Azure, or local models) and allow teachers to generate tailored exercises in seconds.

---

## 💡 Use Cases

- 🧑‍🏫 Teachers preparing multi-level lesson packs.
- 🎯 Students receiving individualized feedback.
- 📈 Schools managing assessment-based improvement loops.

---

## 📁 Project Structure

```
📦 education-platform
├── mp3_audio/         # Linked submodule for vocabulary-to-audio
├── error_analysis/    # CSV/Excel parser and wrong-question extractor
├── knowledge_base/    # Teacher resource manager
├── ai_question_gen/   # Placeholder for AI API-based generation (WIP)
├── templates/         # HTML templates (if Flask/Streamlit UI exists)
├── app.py             # Main app controller
└── requirements.txt   # Required packages
```

---

## ⚙️ Installation

```bash
# Clone the main repository
git clone https://github.com/YOUR_USERNAME/education-platform.git
cd education-platform

# Clone the MP3 module sub-repo (or install it via pip if published)
git submodule add https://github.com/liuxinyi15/EN-CH-word-transform-to-mp3 mp3_audio

# Install dependencies
pip install -r requirements.txt
```

---

## 🛠 Technologies Used

- Python 3.10+
- Flask or Streamlit (for UI)
- pandas, openpyxl
- edge-tts
- GitHub Actions (for deployment/CI, optional)
- CSV/Excel import/export

---

## 📌 License

For commercial usage of the MP3 generator, please consult the license terms in [`EN-CH-word-transform-to-mp3`](https://github.com/liuxinyi15/EN-CH-word-transform-to-mp3).

---

## ✨ Future Improvements

- ✍️ Editable student feedback and teacher annotations
- 📈 Score dashboards with plots
- 🧑‍🎓 Student login system
- 🤖 Fully integrated AI content generation

---

## 📬 Contact

Feel free to reach out via GitHub Issues or email for suggestions, contributions, or educational collaboration opportunities.
