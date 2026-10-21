# Crowd Event Management System

A college mini-project designed to streamline event organization and monitor crowd density during campus events.

## Project Overview

The **Crowd Event Management System** is built incrementally:
- **Event Organizers** submit event requests, venue preferences, and schedules, and upload periodic images during active events.
- **College Administrator** reviews requests, assigns/modifies venues and schedules, and monitors crowd alerts.
- **AI Crowd Counting (Stage 6/7)**: Uses a dedicated CSRNet deep-learning density estimation model to calculate crowd numbers per image. (Face recognition, biometric identification, and CCTV tracking are strictly out of scope).
- **Alerts & Reporting**: Notifies administrator and organizers when crowd count exceeds safe venue thresholds, and generates summary reports using the maximum observed crowd count.

> **Current Implementation: STAGE 1 — PROJECT FOUNDATION**
> Stage 1 sets up the clean project architecture, an isolated Python virtual environment, Flask API service, MySQL connection placeholder, health check endpoint (`/api/health`), and a modern responsive frontend dashboard.

---

## Project Structure

```
code/
├── .gitignore                  # Excludes venv, pycache, .env from version control
├── README.md                   # Complete documentation and setup guide
├── backend/
│   ├── venv/                   # Project-specific isolated Python virtual environment
│   ├── .env                    # Local environment variables
│   ├── requirements.txt        # Backend dependencies (Flask, PyMySQL, Flask-CORS, Pillow)
│   ├── app.py                  # Flask entrypoint & CORS configuration
│   ├── config/                 # Settings, DB connection, initialization
│   ├── db/                     # Schema, migrations, seed data
│   ├── models/                 # Domain models (events, venues, users, crowd analysis)
│   ├── routes/                 # API routes (auth, venues, events, dashboards, public)
│   └── tests/                  # Automated test suites
└── frontend/                   # Modern React Single Page Application (Vite + React)
    ├── package.json            # React & Vite dependencies and scripts
    ├── vite.config.js          # Vite development server configuration (Port 3000)
    ├── index.html              # HTML5 host container for React SPA
    └── src/
        ├── main.jsx            # React root DOM mount
        ├── App.jsx             # Router, role protection guards, shell layout
        ├── context/            # AuthContext (state, login, session retention)
        ├── services/           # Centralized API service layer
        ├── pages/              # Home, Login, Register, Dashboards (Organizer, Administrator)
        ├── components/         # Modals, Navbar, Sidebar, StatCards, Badges
        └── styles.css          # Design system, glassmorphism, responsive layout
```

---

## Prerequisites

- **Python**: Version 3.10+ (tested with Python 3.14)
- **Web Browser**: Any modern browser (Chrome, Edge, Firefox)
- **MySQL Server**: (Optional for Stage 1; required in Stage 2 for database tables)

---

## Installation Steps

### 1. Set Up the Python Virtual Environment
Navigate to the project directory and create the virtual environment inside `backend/venv` (if not already created):

```powershell
# In the project root (c:\Users\vishn\OneDrive\Pictures\Mini project 3\code):
python -m venv backend\venv
```

### 2. Activate the Virtual Environment

**On Windows (PowerShell):**
```powershell
.\backend\venv\Scripts\Activate.ps1
```

*(Or on Command Prompt):*
```cmd
backend\venv\Scripts\activate.bat
```

### 3. Install Dependencies
Install the Stage 1 backend packages inside the virtual environment:

```powershell
.\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

---

## Environment Configuration

Configuration is managed via `.env` in the `backend/` directory:

1. Copy `.env.example` to `.env` if it doesn't already exist:
   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```
2. The default values in `backend/.env` are:
   ```env
   HOST=127.0.0.1
   PORT=5000
   DEBUG=True
   SECRET_KEY=change_this_to_a_secure_random_key_in_production

   # MySQL Database Configuration (Placeholder for Stage 2)
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=
   DB_NAME=crowd_event_db

   # CORS Origins
   CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
   ```

---

## How to Start the Backend

From the project root directory, run:

```powershell
.\backend\venv\Scripts\python.exe backend\app.py
```

Or if the virtual environment is already activated:

```powershell
cd backend
python app.py
```

The server will start on `http://127.0.0.1:5000`.

---

## How to Start the Frontend

Serve the `frontend/` directory using Python's built-in HTTP server:

```powershell
python -m http.server 3000 --directory frontend
```

Then open your browser and navigate to:
```
http://127.0.0.1:3000
```

---

## How to Test the Health Endpoint

### 1. Using a Web Browser
Open your browser and visit:
```
http://127.0.0.1:5000/api/health
```

### 2. Using PowerShell
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/health -Method Get | ConvertTo-Json
```

### 3. Using cURL
```bash
curl http://127.0.0.1:5000/api/health
```

### Expected Response:
```json
{
  "database": {
    "message": "MySQL connection placeholder configured for 'crowd_event_db' on localhost:3306 (Database will be initialized in Stage 2). ...",
    "status": "placeholder_ready"
  },
  "project": "Crowd Event Management System",
  "service": "Crowd Event Management System API",
  "status": "healthy",
  "timestamp": "2026-09-13T10:58:30.123456+00:00",
  "version": "1.0.0"
}
```

---

## Stage 1 Verification Checklist

- [x] Project structure separated into `frontend/` and `backend/`.
- [x] Isolated virtual environment `backend/venv` with zero global package pollution.
- [x] Backend configuration loaded cleanly from `.env` without hardcoded secrets.
- [x] MySQL database connection placeholder established.
- [x] `GET /api/health` returns valid JSON status.
- [x] Modern, modular frontend communicates with backend via fetch with timeout.
- [x] Live backend connectivity status, latency, and graceful error handling displayed in UI.
- [x] No out-of-scope Stage 2+ features implemented yet.
