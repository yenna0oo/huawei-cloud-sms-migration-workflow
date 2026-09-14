#!/usr/bin/env python3
"""
SMS Task Monitoring Script

Continuously polls SMS migration tasks every 60 seconds, reports state
changes to console, detects stuck tasks (speed=0 for 30 min), and flags
failures for the troubleshooting skill.

Usage:
    python3 monitor_tasks.py --region ap-southeast-3
    python3 monitor_tasks.py --region ap-southeast-3 --interval 60

Exits when all tasks reach a terminal state (success or failure).
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime

# ── Constants ──

POLL_INTERVAL = 60          # seconds
STUCK_THRESHOLD = 1800      # 30 minutes in seconds
TERMINAL_STATES = {
    "MIGRATE_SUCCESS", "SYNC_SUCCESS",
    "MIGRATE_FAIL", "SYNC_FAIL", "ABORT",
}
SUCCESS_STATES = {"MIGRATE_SUCCESS", "SYNC_SUCCESS"}
FAILURE_STATES = {"MIGRATE_FAIL", "SYNC_FAIL"}


def run_hcloud(args, timeout=30):
    try:
        r = subprocess.run(["hcloud"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def list_tasks(region):
    out, err, rc = run_hcloud(["SMS", "ListTasks", f"--cli-region={region}"])
    if rc != 0:
        return None, f"ListTasks failed: {err}"
    try:
        data = json.loads(out)
        return data.get("tasks", []), None
    except json.JSONDecodeError:
        return None, f"Parse error: {out[:200]}"


def show_task(region, task_id):
    out, err, rc = run_hcloud([
        "SMS", "ShowTask", f"--cli-region={region}", f"--task_id={task_id}"
    ])
    if rc != 0:
        return None, f"ShowTask failed: {err}"
    try:
        return json.loads(out), None
    except json.JSONDecodeError:
        return None, f"Parse error: {out[:200]}"


def format_elapsed(ms):
    if not ms or ms <= 0:
        return "N/A"
    seconds = int(ms / 1000)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h{m}m{s}s"
    return f"{m}m{s}s"


def format_eta(eta_ms):
    if not eta_ms or eta_ms <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(eta_ms / 1000).strftime("%H:%M:%S")
    except (ValueError, OSError):
        return "N/A"


def report_change(task_name, old_state, new_state, task_detail):
    """Print a state change report to console."""
    now = datetime.now().strftime("%H:%M:%S")
    elapsed = 0
    if task_detail.get("start_date"):
        elapsed = int(time.time() * 1000) - task_detail["start_date"]

    eta = task_detail.get("estimate_complete_time", 0)
    speed = task_detail.get("migrate_speed", 0)
    error = task_detail.get("error_json", "")

    print(f"\n[{now}] STATE CHANGE: {task_name}")
    print(f"  {old_state} -> {new_state}")
    print(f"  Elapsed: {format_elapsed(elapsed)}")
    print(f"  ETA: {format_eta(eta)}")
    print(f"  Speed: {speed} Mbit/s")
    if error:
        print(f"  Error: {error}")
    print()


def report_stuck(task_name, duration_min):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] STUCK ALERT: {task_name}")
    print(f"  Migration speed has been 0 for {duration_min} minutes")
    print(f"  Action: Call huawei-cloud-sms-troubleshooting skill")
    print()


def report_failure(task_name, state, error):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] FAILURE: {task_name}")
    print(f"  State: {state}")
    print(f"  Error: {error or 'No error details available'}")
    print(f"  Action: Call huawei-cloud-sms-troubleshooting skill")
    print(f"  Monitoring paused. Resolve the issue, then monitoring will resume.")
    print()


def report_success(task_name, state, elapsed_ms):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] SUCCESS: {task_name}")
    print(f"  State: {state}")
    print(f"  Total time: {format_elapsed(elapsed_ms)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Monitor SMS migration tasks")
    parser.add_argument("--region", required=True, help="Huawei Cloud region")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL,
                        help=f"Poll interval in seconds (default: {POLL_INTERVAL})")
    args = parser.parse_args()

    # Per-task tracking state
    task_states = {}        # task_id -> last known state
    task_speed_zero_since = {}  # task_id -> timestamp when speed first hit 0
    completed_tasks = set()     # task_ids that reached terminal state

    print(f"SMS Task Monitoring started")
    print(f"Region: {args.region}")
    print(f"Poll interval: {args.interval}s")
    print(f"Stuck threshold: {STUCK_THRESHOLD}s ({STUCK_THRESHOLD // 60} min)")
    print(f"Press Ctrl+C to stop.\n")

    try:
        while True:
            tasks, err = list_tasks(args.region)
            if err:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Error listing tasks: {err}")
                time.sleep(args.interval)
                continue

            if not tasks:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No tasks found.")
                time.sleep(args.interval)
                continue

            active_count = 0

            for task in tasks:
                task_id = task.get("id", "")
                task_name = task.get("name", task_id)
                current_state = task.get("state", "UNKNOWN")

                if task_id in completed_tasks:
                    continue

                if current_state in TERMINAL_STATES:
                    # Get full details for terminal report
                    detail, _ = show_task(args.region, task_id)
                    if not detail:
                        detail = task

                    elapsed = 0
                    if detail.get("finish_date") and detail.get("start_date"):
                        elapsed = detail["finish_date"] - detail["start_date"]

                    if current_state in SUCCESS_STATES:
                        report_success(task_name, current_state, elapsed)
                    elif current_state in FAILURE_STATES:
                        error = detail.get("error_json", "")
                        report_failure(task_name, current_state, error)

                    completed_tasks.add(task_id)
                    task_states[task_id] = current_state
                    continue

                active_count += 1

                # Get detailed status for active tasks
                detail, _ = show_task(args.region, task_id)
                if not detail:
                    detail = task

                # Check for state change
                old_state = task_states.get(task_id)
                if old_state != current_state:
                    report_change(task_name, old_state or "NEW", current_state, detail)
                    task_states[task_id] = current_state

                # Stuck detection: speed = 0 for 30 minutes
                speed = detail.get("migrate_speed", 0)
                now_ts = time.time()

                if speed == 0 and current_state == "RUNNING":
                    if task_id not in task_speed_zero_since:
                        task_speed_zero_since[task_id] = now_ts
                    else:
                        zero_duration = now_ts - task_speed_zero_since[task_id]
                        if zero_duration >= STUCK_THRESHOLD:
                            mins = int(zero_duration / 60)
                            report_stuck(task_name, mins)
                            # Reset to avoid repeated alerts every cycle
                            task_speed_zero_since[task_id] = now_ts
                else:
                    task_speed_zero_since.pop(task_id, None)

            # Check if all tasks are done
            if active_count == 0 and len(completed_tasks) > 0:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] All tasks reached terminal state.")
                print(f"  Completed: {len(completed_tasks)}")
                print(f"  Monitoring complete.\n")
                break

            if active_count == 0 and len(completed_tasks) == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No active tasks. Waiting...")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\nMonitoring stopped by user.")
        print(f"  Completed tasks: {len(completed_tasks)}")
        print(f"  Active tasks: {active_count}")


if __name__ == "__main__":
    main()
