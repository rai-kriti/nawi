# WeighCert

WeighCert is a Django web application for managing non-automatic weighing instrument inspections. It supports instrument and reference-weight registers, guided inspections, role-based review and approval, certificate generation, and public report verification.

## Features

- Admin, inspector, and officer workflows with role-based access.
- Instrument registry and test-weight management.
- Guided inspection workflow with OIML R 76-1:2006 rule calculations.
- Approval, report revisions, PDF certificates, QR codes, and public verification.
- SQLite for application records and optional MongoDB integration for audit/report snapshots.

## Requirements

- Python 3.12 or newer.
- MongoDB for audit and report snapshot features.

## Local setup

Run these commands from the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .\weighcert\.env.example .\weighcert\.env
```

Edit `weighcert\.env` and set a unique `SECRET_KEY` and strong values for `DEMO_ADMIN_PASSWORD`, `DEMO_INSPECTOR_PASSWORD`, and `DEMO_OFFICER_PASSWORD`. Keep `.env` private; it is ignored by Git. Configure `MONGODB_URI` and `MONGODB_DB_NAME` there if MongoDB is not using the local defaults.

Then start the application:

```powershell
Set-Location .\weighcert
python manage.py migrate
python manage.py setup_weighcert
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/login/>. The demo setup creates the three staff accounts; their passwords are the values configured in your local `.env`.

## Tests

From the repository root:

```powershell
python -m pytest .\weighcert\rules\tests_golden.py
```

Run the Django workflow tests from the application directory:

```powershell
Set-Location .\weighcert
python manage.py test
```

## Configuration and data

The Django project is in [`weighcert/`](./weighcert/). Local environment files, the SQLite database, uploaded media, generated static files, and caches are excluded from version control. The local project workflow and design/report documents are also kept out of the public repository.

Production deployments should use a separate secret key, `DEBUG=false`, production host settings, and appropriately secured database and MongoDB services.
