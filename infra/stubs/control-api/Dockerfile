FROM python:3.12-alpine

RUN addgroup -S -g 10001 app \
    && adduser -S -D -H -u 10001 -G app app

WORKDIR /app
COPY --chown=10001:10001 server.py /app/server.py

USER 10001:10001
EXPOSE 8000

CMD ["python", "/app/server.py"]
