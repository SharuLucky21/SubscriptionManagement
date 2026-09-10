# Subscription Management System (Flask)

This is a minimal, runnable Subscription Management System built with Flask, SQLite, Bootstrap, and Chart.js.
It implements core MVP features: user/admin roles, plan CRUD (admin), subscribe/upgrade/cancel (user), and a simple admin analytics page.

## Run locally
1. Create a Python virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Initialize DB and run:
   ```bash
   export FLASK_APP=app.py
   flask run
   ```
   On Windows (PowerShell):
   ```powershell
   $env:FLASK_APP = "app.py"
   flask run
   ```
3. Open http://127.0.0.1:5000

## Default demo accounts
- Admin: username `admin`, password `admin123`
- User: username `user1`, password `user123`

## Notes
- Payment is simulated/out-of-scope.
- This is a starter project; extend it as needed for security/hardening/production.
