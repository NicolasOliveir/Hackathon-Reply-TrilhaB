from __future__ import annotations

import json
import os
import socket
from pathlib import Path


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False


result = {
    "uid": os.getuid(),
    "docker_socket_present": Path("/var/run/docker.sock").exists(),
    "database_url_present": bool(os.getenv("DATABASE_URL")),
    "docker_host_present": bool(os.getenv("DOCKER_HOST")),
    "postgres_resolves": resolves("postgres"),
    "postgres_reachable": reachable("postgres", 5432),
    "control_api_reachable": reachable("control-api", 8000),
}

passed = (
    result["uid"] == 10001
    and not result["docker_socket_present"]
    and not result["database_url_present"]
    and not result["docker_host_present"]
    and not result["postgres_resolves"]
    and not result["postgres_reachable"]
    and result["control_api_reachable"]
)
result["result"] = "PASS" if passed else "FAIL"
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if passed else 1)
