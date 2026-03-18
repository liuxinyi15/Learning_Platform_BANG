# 🧩 BANG - Building Adaptive Next-Generation Growth Platform
---

## 📖 Introduction 

### BANG is an all-in-one teaching workbench designed to empower language educators.

- **What does BANG stand for?**

  English: Building Adaptive Next-Generation Growth Platform.

  Chinese: The pronunciation echoes "帮" (Help) and "棒" (Excellence).

  This dual meaning symbolizes our core mission: to support ("帮") learners and teachers, helping them achieve excellent ("棒") outcomes through adaptive technology and data-driven insights.

---

## ✨ Modules & Features

### BANG consists of **6** core modules, each distinguished by a unique theme color to represent different aspects of the teaching workflow:

- **📚 Material Library**

  Resource Management: Batch upload and manage teaching materials (PDFs, Docs, Audio).

  Visual Indexing: Auto-generated cover previews and category filtering.

  Smart Sorting: Organize resources by official/personal uploads or timeline.

- **📅 Lesson Planner**

  Kanban Board: Drag-and-drop task management for daily lesson planning.

  Progress Tracking: Mark tasks with priority levels (High/Medium/Low) and completion status.

  Export: One-click export of lesson plans to CSV.

- **🔤 Vocab Master**

  Dual Mode: Switch between Table View for editing and Flashcard View for review.

  Custom Columns: Dynamically add new fields (e.g., Synonyms, Notes) to your word lists.

  Interactive Learning: 3D flip animations for effective vocabulary memorization.

- **🎧 Audio Studio**

  Batch Synthesis: Convert Excel word lists into high-quality MP3 audio files.

  Customization: Adjust speech rate, voice type (Male/Female), and repetition count.

  Powered By: Specialized TTS logic for language learning scenarios.

- **📝 Smart Grading**

  Auto-Correction: Upload student answer sheets and question banks for instant grading.

  Fuzzy Matching: Intelligent recognition of question IDs (e.g., matching "Q1" with "QQ1").

  Error Analysis: Automatic generation of error distribution charts and personal error books.

- **📊 Performance Analysis**

  Multi-Level Dashboard: Switch between Grade Overview, Class Trends, and Student Tracker.

  Visual Data: Integrated ECharts for trend lines, radar charts (ability models), and ranking bars.

  Historical Tracking: Compare performance across multiple exams to identify growth patterns.
---

## 🛠️ Tech Stack 
- **Backend**: Python 3, Flask, Pandas, SQLite

- **Frontend**: HTML5, Tailwind CSS, Vue.js 3, ECharts, SheetJS

- **Authentication**: Flask-Login
---

## 🚀 Quick Start
1. Clone the Repository
```Bash
git clone https://github.com/your-username/bang-platform.git
cd bang-platform
```
2. Set Up Virtual Environment
```Bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```
3. Install Dependencies
```Bash
pip install -r requirements.txt
```
4. Run the Platform
  The database (platform.db) and necessary folders will be initialized automatically on the first run.

```Bash
python app.py
```
5. Access
  Open your browser and visit: http://127.0.0.1:5000

  Before first use, set a strong session secret:
```Bash
# Windows PowerShell
$env:BANG_SECRET_KEY = "replace-with-a-long-random-secret"
```

  Optional: bootstrap the first admin account from environment variables:
```Bash
# Windows PowerShell
$env:BANG_INIT_ADMIN_USERNAME = "admin"
$env:BANG_INIT_ADMIN_PASSWORD = "replace-with-a-strong-password"
```
---
## 📂 Project Structure
```Bash
BANG-Platform/
├── app.py                  # Main Application Entry & Routes
├── services/               # Business Logic
│   ├── library_service.py  # Database & User Management
│   ├── audio_service.py    # Audio Generation Logic
│   └── performance_service.py # Data Analysis Logic
├── templates/              # Frontend Templates (Jinja2)
│   ├── base.html           # Global Layout
│   ├── index.html          # Dashboard
│   ├── performance.html    # Performance Module
│   └── ...
├── library/                # Static Resource Storage
├── performance_data/       # CSV Data for Analysis
├── platform.db             # SQLite Database
└── README.md
```
---

## 📢 License 
### **Project License**

This project is licensed under the MIT License.

### **Special Credits**: Audio Module

The Audio Studio module (including audio_service.py and the underlying text-to-speech logic) is derived from and powered by the open-source project:
```Bash
Source: EN-CH-word-transform-to-mp3
Author: Xinyi_LIU (@liuxinyi15)
```

---

## BANG - Helping Learners Grow. 🚀
