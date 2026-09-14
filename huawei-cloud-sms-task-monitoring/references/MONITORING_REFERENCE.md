# SMS Task Monitoring — Detailed Reference

> API parameters sourced from Huawei Cloud SMS API snapshot (local):
> - ListTasks: GET /v3/tasks
> - ShowTask: GET /v3/tasks/{task_id}
> - UpdateTaskStatus: POST /v3/tasks/{task_id}/action

---

## Table of Contents

1. [Task States](#1-task-states)
2. [ShowTask Response Fields](#2-showtask-response-fields)
3. [Sub-task Sequence](#3-sub-task-sequence)
4. [Stuck Detection Logic](#4-stuck-detection-logic)
5. [hcloud CLI Commands](#5-hcloud-cli-commands)

---

## 1. Task States

All possible task state values from the SMS API:

| State | Description | Terminal? | Action |
|-------|-------------|-----------|--------|
| READY | Task created, waiting to start | No | Monitor |
| RUNNING | Migration in progress | No | Monitor |
| SYNCING | Incremental sync in progress | No | Monitor |
| MIGRATE_SUCCESS | Full data replication complete | Yes | Report success, stop monitoring |
| SYNC_SUCCESS | Sync complete | Yes | Report success, stop monitoring |
| MIGRATE_FAIL | Migration failed | Yes | Call troubleshooting skill |
| SYNC_FAIL | Sync failed | Yes | Call troubleshooting skill |
| ABORTING | Abort in progress | No | Monitor |
| ABORT | Aborted | Yes | Report to user |
| SKIPPING | Skipping in progress | No | Monitor |
| DELETING | Deletion in progress | No | Monitor |
| RESETING | Reset in progress | No | Monitor |

### Terminal States (monitoring stops for this task)

```
MIGRATE_SUCCESS, SYNC_SUCCESS, MIGRATE_FAIL, SYNC_FAIL, ABORT
```

### Success States

```
MIGRATE_SUCCESS, SYNC_SUCCESS
```

### Failure States

```
MIGRATE_FAIL, SYNC_FAIL
```

---

## 2. ShowTask Response Fields

Key fields from `GET /v3/tasks/{task_id}` response:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Task ID |
| name | string | Task name |
| state | string | Current state (see section 1) |
| create_date | integer | Creation timestamp (ms since epoch) |
| start_date | integer | Start timestamp (ms since epoch) |
| finish_date | integer | Finish timestamp (ms since epoch) |
| estimate_complete_time | integer | Estimated completion timestamp (ms) |
| migrate_speed | number | Migration speed in Mbit/s |
| error_json | string | Error details (JSON string, empty if no error) |
| total_time | integer | Total elapsed time (ms) |
| remain_seconds | integer | Estimated remaining seconds |
| sub_tasks | array | Sub-task list with progress |
| subtask_info | string | Current sub-task name and progress |
| connected | boolean | Agent connection status |
| total_cpu_usage | number | Host CPU usage (%) |
| agent_cpu_usage | number | Agent CPU usage (%) |
| total_mem_usage | number | Host memory usage (MB) |
| agent_mem_usage | number | Agent memory usage (MB) |
| total_disk_io | number | Host disk I/O (Mbit/s) |
| agent_disk_io | number | Agent disk I/O (Mbit/s) |

### Elapsed Time Calculation

```
elapsed = now - start_date    (if task is running)
elapsed = finish_date - start_date    (if task is finished)
```

Both timestamps are in milliseconds since epoch.

### Estimated Completion Time

`estimate_complete_time` is a timestamp in milliseconds. Convert to human-readable:

```python
from datetime import datetime
eta = datetime.fromtimestamp(estimate_complete_time / 1000)
```

---

## 3. Sub-task Sequence

Sub-tasks for Linux file-level migration:

| Order | Sub-task | Description |
|-------|----------|-------------|
| 1 | CREATE_CLOUD_SERVER | Create/target cloud server |
| 2 | SSL_CONFIG | SSL configuration |
| 3 | ATTACH_AGENT_IMAGE | Attach agent image |
| 4 | FORMAT_DISK_LINUX_FILE | Format disk |
| 5 | MIGRATE_LINUX_FILE | Migrate files (main data transfer) |

Each sub-task has:
- `progress`: 0-100 (percentage)
- `start_date`: start timestamp
- `end_date`: end timestamp (empty if not finished)

> The `MIGRATE_LINUX_FILE` sub-task is the main data replication phase.
> When this sub-task reaches 100%, the task is near MIGRATE_SUCCESS.

---

## 4. Stuck Detection Logic

A task is considered "stuck" if:

```
migrate_speed == 0  AND  state == RUNNING  AND  duration >= 30 minutes
```

Where `duration` is the time since `migrate_speed` first dropped to 0.

### Implementation

Track per-task:
- `last_nonzero_speed_time`: timestamp when speed was last > 0
- If `migrate_speed == 0` and `now - last_nonzero_speed_time >= 1800` (30 min):
  - Report stuck alert to console
  - Call `huawei-cloud-sms-troubleshooting` skill

### Reset Condition

When `migrate_speed` becomes > 0 again, reset `last_nonzero_speed_time`.

---

## 5. hcloud CLI Commands

### 5.1 List All Tasks

```bash
hcloud SMS ListTasks --cli-region=<region>
# Returns: { "count": N, "tasks": [ { "id": "...", "name": "...", "state": "..." }, ... ] }
```

### 5.2 Show Task Details

```bash
hcloud SMS ShowTask --cli-region=<region> --task_id=<task_id>
# Returns full task details: state, speed, ETA, sub-tasks, errors, etc.
```

### 5.3 Restart a Failed Task (if user approves)

```bash
hcloud SMS UpdateTaskStatus --cli-region=<region> --task_id=<task_id> --operation=restart
```

> Only execute after user approval. The monitoring skill reports the failure
> and calls the troubleshooting skill — it does NOT auto-restart.
