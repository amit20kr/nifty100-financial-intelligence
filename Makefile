.PHONY: load ratios migrate test report dashboard api clean setup validate db-check clean-db coverage

setup:
	python -m venv .venv
	.venv/Scripts/pip install -r requirements.txt
	pre-commit install

load:
	python -m src.etl.loader

validate: load

db-check:
	python scripts/verify_db.py

ratios:
	.venv/Scripts/python -m src.analytics.ratio_engine

migrate:
	.venv/Scripts/python db/migrations/migrate.py

test:
	.venv/Scripts/pytest tests/ -v

coverage:
	.venv/Scripts/pytest tests/ --cov=src --cov-report=html:reports/htmlcov --cov-report=term-missing

report:
	python -m src.reporting.pdf_generator

dashboard:
	streamlit run src/dashboard/app.py

api:
	uvicorn src.api.main:app --reload --port 8000

clean-db:
	python -c "import os; [os.remove(f) for f in ['db/nifty100.db', 'output/load_audit.csv', 'output/validation_failures.csv'] if os.path.exists(f)]"

clean: clean-db
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	python -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"
