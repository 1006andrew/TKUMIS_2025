# python_firebase_project

A scaffolded FastAPI + Firebase project with your uploaded frontend integrated.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Then open http://127.0.0.1:8000/

## Firebase Setup

Place your service account JSON at `config/firebase_cred.json`. The file is ignored by git by default.

## Project Structure

```
python_firebase_project/
├── README.md
├── .gitignore
├── requirements.txt
├── main.py
├── config/
│   └── firebase_cred.json        # (add your key here)
├── src/
│   ├── __init__.py
│   ├── app.py
│   ├── web/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── templates/            # HTML templates (from your upload)
│   │   └── static/               # Frontend assets (from your upload)
│   ├── firebase/
│   │   ├── __init__.py
│   │   ├── init_firebase.py
│   │   ├── firestore_service.py
│   │   └── auth_service.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── helpers.py
│   └── models/
│       ├── __init__.py
│       └── user.py
├── tests/
│   └── test_smoke.py
├── docs/
└── data/
```

## Notes

- All non-HTML assets from your upload were placed under `src/web/static/` preserving folder structure.
- HTML files were placed in `src/web/templates/`. Resource paths inside HTML were rewritten to use `{{ url_for('static', path='...') }}` where applicable.
- Routes:
  - `/` renders `index.html` if present
  - `/{page}` renders `{page}.html` if such a template exists
