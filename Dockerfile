FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# The package must exist before pip builds its wheel.
COPY pyproject.toml ./
COPY app ./app
COPY tools ./tools

# Install python dependencies
RUN pip install --no-cache-dir .

# Build a fresh schedule database from Excel, never from local student data.
# These parsing settings are required by app.config but unused by this importer.
# Finalize WAL so reading the seed never needs writable sidecar files.
RUN PARSING_YEAR=build PARSING_SEMESTER=0 DB_PATH=/opt/vsuet/schedule.sqlite3 \
    python -m tools.schedule_import --strict \
    && python -c "import sqlite3; db = sqlite3.connect('/opt/vsuet/schedule.sqlite3'); assert db.execute('PRAGMA journal_mode=DELETE').fetchone() == ('delete',); db.close()"

ENV DB_PATH=/data/rating.sqlite3
ENTRYPOINT ["python", "-m", "tools.schedule_import.bootstrap"]

# Expose FastAPI port
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=3)"

# Start FastAPI application with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
