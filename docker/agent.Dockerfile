FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY shared/ shared/
COPY collector/ collector/
COPY agent/ agent/

RUN pip install --no-cache-dir .

CMD ["python", "-m", "agent.main"]
