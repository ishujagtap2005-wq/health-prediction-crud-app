# Health Prediction Records (Desktop App)

Python + Tkinter desktop app with SQLite storage. Stores patient blood test results and
generates an AI remark using the Google Gemini API.

## Features
- Add / View / Update / Delete patient records
- Validation: name, date of birth (dd/mm/yyyy, not in future), email format and uniqueness,
  numeric blood test values
- AI-generated "Remarks" for every record

## Run
```bash
pip install -r requirements.txt
# Windows:  set GEMINI_API_KEY=your_key
# Mac/Linux: export GEMINI_API_KEY=your_key
python health_app.py
```
API key is read from an environment variable; it is not stored in the code.
