# RETAILMIND

A Flask-based retail management dashboard and API.

## Requirements

- Python 3.9+ (tested on 3.9/3.10)
- Git
- A virtual environment tool (`venv` recommended)
- (Optional) PostgreSQL or other DB as configured in `config.py`

## Quickstart (Windows)

1. Clone the repo and change into the project folder:

```
git clone https://github.com/shahram8708/RetailMind
cd RETAILMIND
```

2. Create and activate a virtual environment:

PowerShell:

```
python -m venv venv
.\venv\Scripts\Activate.ps1
```

CMD:

```
python -m venv venv
venv\Scripts\activate.bat
```

3. Install Python dependencies:

```
pip install -r requirements.txt
```

4. Set required environment variables (example):

PowerShell:

```
$env:FLASK_APP = 'run.py'
$env:FLASK_ENV = 'development'
# set DB URL if needed, e.g. $env:DATABASE_URL = 'postgresql://user:pass@localhost/dbname'
```

CMD:

```
set FLASK_APP=run.py
set FLASK_ENV=development
```

5. Initialize the database and run migrations (if using Flask-Migrate):

```
flask db upgrade
```

If `migrations/` already exists you may skip `flask db init`/`flask db migrate`.

6. Seed initial data (if desired):

```
python -m app.seed
```

## Running (development)

Start the development server:

```
python run.py
# or
flask run --host=0.0.0.0
```

The app should be available at http://127.0.0.1:5000/ by default.

## Running (production)

Use a WSGI server such as `gunicorn` with `wsgi:app`:

```
pip install gunicorn
gunicorn wsgi:app --workers 3 --bind 0.0.0.0:8000
```

## Tests

This project uses `pytest`. Run the test suite with:

```
pytest -q
```

To run a single test file:

```
pytest tests/test_models.py -q
```

## Common commands

- Install deps: `pip install -r requirements.txt`
- Run dev server: `python run.py`
- Run tests: `pytest -q`
- Run migrations: `flask db upgrade`
- Seed DB: `python -m app.seed`

## Notes & Troubleshooting

- If environment variables are not picked up, ensure they are exported in the current shell.
- If migrations fail, check `config.py` for the correct database URL and that the DB is reachable.
- If tests fail due to DB state, try running tests with a separate test database or use transactions/fixtures configured in `tests/`.

## Contributing

1. Create a branch for your feature/fix.
2. Run tests locally.
3. Open a PR with a clear description.

---

If you want, I can also add CI test steps, badges, or fill in production deployment examples for your hosting provider.
