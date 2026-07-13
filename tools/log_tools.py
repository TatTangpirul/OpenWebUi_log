"""
System Log Diagnostic Tools for OpenWebUI.
Paste the contents of this file into OpenWebUI > Workspace > Tools > Create Tool.
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional

LOGS_DIR = "/app/logs"
LOOKBACK_MINUTES = 60

SYSTEM_LOGS = {
    "api-service":   f"{LOGS_DIR}/api-service.log",
    "db-monitor":    f"{LOGS_DIR}/db-monitor.log",
    "auth-service":  f"{LOGS_DIR}/auth-service.log",
    "cache-service": f"{LOGS_DIR}/cache-service.log",
    "scheduler":     f"{LOGS_DIR}/scheduler.log",
}


class Tools:
    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Injects available system names into context before every LLM call."""
        system_list = ", ".join(SYSTEM_LOGS.keys())
        injected = f"\n\nAvailable systems to monitor: {system_list}\nIf the user does not specify a system, ask them which one they want to check.\n"

        messages = body.get("messages", [])
        system_found = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] += injected
                system_found = True
                break
        if not system_found:
            messages.insert(0, {"role": "system", "content": injected})

        body["messages"] = messages
        return body

    def list_systems(self) -> str:
        """
        List all systems available for monitoring.
        :return: Names of all monitorable systems
        """
        available = [name for name, path in SYSTEM_LOGS.items() if os.path.exists(path)]
        if not available:
            return "No system log files found. Make sure the log generator is running."
        return "Available systems: " + ", ".join(available)

    def get_recent_logs(self, system: str, minutes: int = LOOKBACK_MINUTES, level: str = "ALL") -> str:
        """
        Get recent log entries for a specific system.
        :param system: System name to query (e.g. api-service, db-monitor, auth-service, cache-service, scheduler)
        :param minutes: Number of minutes to look back (e.g. 5, 10, 30)
        :param level: Filter by log level: ALL, INFO, ERROR, CRIT
        :return: Matching log entries as formatted text
        """
        log_file = SYSTEM_LOGS.get(system)
        if not log_file:
            return f"Unknown system '{system}'. Call list_systems to see available options."

        minutes = int(minutes)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cutoff_ms = now_ms - (minutes * 60 * 1000)
        results = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", 0) < cutoff_ms:
                            continue
                        if level != "ALL" and entry.get("level") != level:
                            continue
                        results.append(entry.get("message", line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return f"Log file for '{system}' not found. Make sure the log generator is running."
        if not results:
            return f"<<<BEGIN REAL LOG DATA>>>\nNo {level} logs found for '{system}' in the last {minutes} minutes.\n<<<END REAL LOG DATA>>>"
        return f"<<<BEGIN REAL LOG DATA>>>\n" + "\n".join(results[-50:]) + "\n<<<END REAL LOG DATA>>>"

    def count_errors_by_service(self, system: str, minutes: int = LOOKBACK_MINUTES) -> str:
        """
        Count ERROR and CRIT log entries for a specific system over the last N minutes.
        :param system: System name to query (e.g. api-service, db-monitor, auth-service, cache-service, scheduler)
        :param minutes: Number of minutes to look back
        :return: Summary of error counts
        """
        log_file = SYSTEM_LOGS.get(system)
        if not log_file:
            return f"Unknown system '{system}'. Call list_systems to see available options."

        minutes = int(minutes)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cutoff_ms = now_ms - (minutes * 60 * 1000)
        counts = {"ERROR": 0, "CRIT": 0}
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", 0) < cutoff_ms:
                            continue
                        lvl = entry.get("level")
                        if lvl in counts:
                            counts[lvl] += 1
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return f"Log file for '{system}' not found. Make sure the log generator is running."
        if counts["ERROR"] == 0 and counts["CRIT"] == 0:
            return f"<<<BEGIN REAL LOG DATA>>>\nNo errors found for '{system}' in the last {minutes} minutes. System appears healthy.\n<<<END REAL LOG DATA>>>"
        return f"<<<BEGIN REAL LOG DATA>>>\nError summary for '{system}' — last {minutes} minute(s):\n  ERROR: {counts['ERROR']}\n  CRIT:  {counts['CRIT']}\n<<<END REAL LOG DATA>>>"

    def get_log_context(self, system: str, timestamp_ms: int, window_seconds: int = 30) -> str:
        """
        Get log entries around a specific timestamp for a given system.
        :param system: System name to query (e.g. api-service, db-monitor, auth-service, cache-service, scheduler)
        :param timestamp_ms: Unix timestamp in milliseconds to center the window on
        :param window_seconds: Seconds before and after the timestamp to include (default 30)
        :return: Log entries within the time window
        """
        log_file = SYSTEM_LOGS.get(system)
        if not log_file:
            return f"Unknown system '{system}'. Call list_systems to see available options."

        timestamp_ms = int(timestamp_ms)
        window_ms = int(window_seconds) * 1000
        start_ms = timestamp_ms - window_ms
        end_ms = timestamp_ms + window_ms
        results = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        t = entry.get("timestamp", 0)
                        if start_ms <= t <= end_ms:
                            ts_str = datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%H:%M:%S UTC")
                            results.append(f"[{ts_str}] {entry.get('message', line)}")
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return f"Log file for '{system}' not found. Make sure the log generator is running."
        if not results:
            return f"No logs found for '{system}' around timestamp {timestamp_ms}."
        return "\n".join(results)
