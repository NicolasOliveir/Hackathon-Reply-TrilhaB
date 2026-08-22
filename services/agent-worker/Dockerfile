FROM python:3.12-alpine

RUN addgroup -S -g 10001 worker \
    && adduser -S -D -H -u 10001 -G worker worker

WORKDIR /app
COPY --chown=10001:10001 worker.py /app/worker.py

USER 10001:10001

ENTRYPOINT ["python", "/app/worker.py"]
