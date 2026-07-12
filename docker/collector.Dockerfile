FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY shared/ shared/
COPY collector/ collector/
COPY agent/ agent/
COPY alembic.ini ./

RUN pip install --no-cache-dir .

EXPOSE 8000

# Migrations run explicitly (docs/adr/016-database-migration-strategy.md),
# never implicitly at import time; the container entrypoint applies them
# before serving so a fresh compose stack comes up schema-complete.
CMD ["sh", "-c", "alembic upgrade head && python -m collector.main"]
