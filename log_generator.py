import json
import os
import random
import time
from datetime import datetime, timezone

SERVICES = ["api-service", "db-monitor", "auth-service", "cache-service", "scheduler"]
LOGS_DIR = "logs"


def make_entry(level, service, message):
    return {
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "level": level,
        "logGroupName": f"/aws/ec2/{service}",
        "logStreamName": f"i-{random.randint(0x100000, 0xFFFFFF):x}",
        "message": f"{level} [{service}] {message}",
    }


def generate_normal(service):
    msg = random.choice([
        "Health check passed",
        f"Request processed in {random.randint(10, 200)}ms",
        f"CPU usage: {random.randint(5, 40)}%",
        f"Memory usage: {random.randint(20, 60)}%",
        "Connection pool healthy",
        f"Scheduled task completed in {random.randint(50, 500)}ms",
    ])
    return make_entry("INFO", service, msg)


if __name__ == "__main__":
    os.makedirs(LOGS_DIR, exist_ok=True)
    print(f"Writing logs to {LOGS_DIR}/<service>.log — Ctrl+C to stop")
    log_files = {svc: open(f"{LOGS_DIR}/{svc}.log", "a") for svc in SERVICES}
    try:
        while True:
            service = random.choice(SERVICES)
            entry = generate_normal(service)
            line = json.dumps(entry)
            log_files[service].write(line + "\n")
            log_files[service].flush()
            print(line)
            time.sleep(random.uniform(0.5, 2.0))
    finally:
        for f in log_files.values():
            f.close()
