---
name: huawei-cloud-sms-task-monitoring
description: Monitor Huawei Cloud SMS (Server Migration Service) migration tasks continuously. Polls all migration tasks every 60 seconds, reports state changes to console, detects stuck tasks (migration speed at 0 for 30 minutes), and calls the troubleshooting skill on failures. Stops monitoring a task when it reaches MIGRATE_SUCCESS (full data replication complete). Use when the user asks to: (1) monitor migration tasks, (2) check migration progress, (3) watch SMS tasks, (4) track migration status. Triggers on phrases like "monitor migration tasks", "监控迁移任务", "check migration status", "查看迁移进度", "watch SMS tasks", "track migration".
---

# huawei-cloud-sms-task-monitoring

## Overview

Continuously monitors all SMS migration tasks by polling `hcloud SMS ListTasks`
every 60 seconds. Reports state changes to console only (no log files).
Detects stuck tasks and calls the troubleshooting skill on failures.

This skill is part of a migration workflow:
1. `huawei-cloud-sms-agent-installation` — install agents on source hosts
2. Target server creation skill (Terraform) — create target ECS instances
3. `huawei-cloud-sms-task-creation` — create tasks, start with approval
4. **This skill** — monitor task progress until completion
5. `huawei-cloud-sms-troubleshooting` — error handling (companion)

## Safety Rules

1. **Report, don't fix** — On any failure or stuck task, report to user and
   call `huawei-cloud-sms-troubleshooting` skill. Do NOT auto-restart or
   auto-fix anything.
2. **Read-only monitoring** — This skill only queries task status (ListTasks,
   ShowTask). It does NOT modify, delete, or create anything on Huawei Cloud.
3. **Stop on failure** — When a task fails (MIGRATE_FAIL), monitoring pauses
   until the issue is resolved. The user drives the resolution.
4. **Console only** — All reports go to stdout. No log files, no notifications.

## Task States

| State | Description | Terminal? |
|-------|-------------|-----------|
| READY | Waiting to start | No |
| RUNNING | Migration in progress | No |
| SYNCING | Incremental sync | No |
| MIGRATE_SUCCESS | Data replication complete | Yes (success) |
| SYNC_SUCCESS | Sync complete | Yes (success) |
| MIGRATE_FAIL | Migration failed | Yes (failure) |
| SYNC_FAIL | Sync failed | Yes (failure) |
| ABORT | Aborted | Yes |

> Full state list in references/MONITORING_REFERENCE.md section 1.

## Workflow

### Step 1: Start Monitoring

```bash
python3 scripts/monitor_tasks.py --region <region>
```

Options:
- `--interval 60` — poll interval in seconds (default: 60)
- `--region` — Huawei Cloud region (required)

The script runs continuously until all tasks reach a terminal state,
or until interrupted with Ctrl+C.

### Step 2: Poll Loop (every 60 seconds)

Each cycle:

1. **List all tasks**: `hcloud SMS ListTasks --cli-region=<region>`
2. **For each active task** (not in terminal state):
   - **Show task details**: `hcloud SMS ShowTask --cli-region=<region> --task_id=<id>`
   - **Check state change**: If state changed since last poll, report to console:
     ```
     [14:32:15] STATE CHANGE: server-01_0915
       RUNNING -> MIGRATE_SUCCESS
       Elapsed: 45m30s
       ETA: N/A
       Speed: 0 Mbit/s
     ```
   - **Check stuck**: If `migrate_speed == 0` and state is `RUNNING` for 30
     consecutive minutes, report stuck alert:
     ```
     [14:32:15] STUCK ALERT: server-01_0915
       Migration speed has been 0 for 30 minutes
       Action: Call huawei-cloud-sms-troubleshooting skill
     ```
3. **Sleep** for 60 seconds
4. **Repeat**

### Step 3: On State Change — Report to Console

Only report when a task's state changes (not every poll cycle):

```
[14:30:15] STATE CHANGE: server-01_0915
  READY -> RUNNING
  Elapsed: 0m0s
  ETA: 15:05:22
  Speed: 12.5 Mbit/s
```

Report includes:
- Task name
- Old state -> new state
- Elapsed time (from start_date)
- Estimated completion time
- Migration speed (Mbit/s)
- Error details (if any)

### Step 4: On Failure — Call Troubleshooting

When a task reaches `MIGRATE_FAIL` or `SYNC_FAIL`:

```
[14:35:22] FAILURE: server-02_0915
  State: MIGRATE_FAIL
  Error: SMS.0515 vols_map NoneType
  Action: Call huawei-cloud-sms-troubleshooting skill
  Monitoring paused. Resolve the issue, then monitoring will resume.
```

Then:
1. Call `huawei-cloud-sms-troubleshooting` skill to check for known issues
2. Report to user with possible causes and resolutions
3. **Wait** for user to resolve the issue
4. After resolution, monitoring resumes automatically on next poll cycle

### Step 5: On Success — Report and Stop Monitoring That Task

When a task reaches `MIGRATE_SUCCESS`:

```
[15:05:30] SUCCESS: server-01_0915
  State: MIGRATE_SUCCESS
  Total time: 35m15s
```

The task is marked complete and no longer monitored.

### Step 6: Exit When All Tasks Complete

When all tasks have reached a terminal state:

```
[15:10:45] All tasks reached terminal state.
  Completed: 3
  Monitoring complete.
```

The script exits.

## Stuck Detection

A task is "stuck" if:
- `migrate_speed == 0`
- `state == RUNNING`
- Duration of zero speed >= 30 minutes (1800 seconds)

When detected:
- Report stuck alert to console
- Call `huawei-cloud-sms-troubleshooting` skill
- Reset the 30-minute timer (to avoid repeated alerts every cycle)

When speed becomes > 0 again, the timer resets.

## hcloud CLI Commands

| Action | Command |
|--------|---------|
| List all tasks | `hcloud SMS ListTasks --cli-region=<region>` |
| Show task detail | `hcloud SMS ShowTask --cli-region=<region> --task_id=<id>` |

> This skill only uses read-only API calls. No mutations.

## File Structure

```
huawei-cloud-sms-task-monitoring/
├── SKILL.md                              ← This file
├── references/
│   └── MONITORING_REFERENCE.md           ← Task states, API fields, stuck logic
└── scripts/
    └── monitor_tasks.py                  ← Continuous polling script
```

## Companion Skills

- **huawei-cloud-sms-troubleshooting**: Called on failures and stuck tasks
- **huawei-cloud-sms-task-creation**: Prior step — creates and starts tasks
- **huawei-cloud-sms-agent-installation**: Earlier step — agent installation
