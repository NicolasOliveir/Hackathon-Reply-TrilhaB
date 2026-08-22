FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CONTRACTS_DIR=/app/packages/contracts

WORKDIR /app

COPY pyproject.toml README.md ./
RUN python -m pip install --no-cache-dir ".[control-api]"

COPY packages/contracts ./packages/contracts
COPY services/control-api ./services/control-api

WORKDIR /app/services/control-api

EXPOSE 8000

# Uma única instância mantém um único laço de scheduler no MVP. A migration é
# idempotente e termina antes de a API ficar saudável.
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
