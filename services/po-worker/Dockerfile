FROM python:3.12-alpine

RUN addgroup -S -g 10001 worker && adduser -S -D -H -u 10001 -G worker worker
WORKDIR /app
COPY --chown=10001:10001 services/po-worker/po_worker.py /app/po_worker.py
COPY --chown=10001:10001 packages/contracts/schemas/v1/po-output.schema.json /app/contracts/po-output.schema.json
USER 10001:10001
ENTRYPOINT ["python", "/app/po_worker.py"]
