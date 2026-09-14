---
name: huawei-cloud-sms-task-creation
description: Create Huawei Cloud SMS (Server Migration Service) migration tasks to link source servers to existing target servers for migration. Creates one migration task per source server using hcloud CLI. Target ECS instances must already exist (created by a separate Terraform skill). Always uses private network (no EIP). Requires explicit user approval before creating tasks and again before starting them. Use when the user asks to: (1) create SMS migration tasks, (2) link source servers to target servers, (3) batch create migration tasks, (4) start migration tasks. Triggers on phrases like "create migration task", "创建迁移任务", "create SMS task", "batch create migration tasks", "start migration task", "启动迁移任务".
---

# huawei-cloud-sms-task-creation

## Overview

Create SMS migration tasks that link source servers (with agents already
installed) to existing target ECS instances on Huawei Cloud. Uses hcloud CLI
to call SMS APIs. One task is created per source server.

Target ECS instances are created beforehand by a separate Terraform skill.
This skill does NOT create templates or auto-create ECS.

This skill is part of a migration workflow:
1. `huawei-cloud-sms-agent-installation` — install agents on source hosts
2. Target server creation skill (Terraform) — create target ECS instances
3. **This skill** — create tasks linking source to existing target, start with approval
4. Monitoring skill (future) — monitor task progress

## Safety Rules

1. **No EIP creation** — Always use private network. Set `use_public_ip=false`
   in all tasks. Never include `publicip` parameters.
2. **Two approval gates**:
   - Gate 1: Show task summary before creation -> wait for user "ok"
   - Gate 2: After tasks created (READY state) -> wait for user "ok" before start
3. **No deletion without approval** — Never delete or modify anything on
   Huawei Cloud without explicit user approval.
4. **Report, don't fix** — On any error, call `huawei-cloud-sms-troubleshooting`
   skill, report to user, wait for approval before any action.
5. **Private network only** — `syncing=false`, `use_public_ip=false` always.
6. **Existing target servers only** — Do NOT auto-create ECS. Target VM IDs
   must be provided in the input JSON.

## Naming Conventions

| Resource | Format | Example |
|----------|--------|---------|
| Migration task | `{hostname}_{MMDD}` | `server-01_0915` |

`{MMDD}` = current date (month + day). `{hostname}` = source server hostname.

## Input Format

JSON file with region/project info and source-target server mapping.
See references/TASK_CREATION_REFERENCE.md section 1 for full field documentation.

```json
{
    "region_id": "ap-southeast-3",
    "region_name": "Singapore",
    "project_id": "0215ef11e49d4743be23dd97a1561xxx",
    "project_name": "Singapore",
    "source_servers": [
        {
            "hostname": "server-01",
            "source_server_id": "dcdbe339-b02d-4578-95a1-9c9c547dxxxx",
            "os_type": "LINUX",
            "migration_type": "MIGRATE_FILE",
            "target_vm_id": "6dac09d8-5835-4888-xxxx-787453c4e1d4",
            "target_vm_name": "server-01-target"
        }
    ]
}
```

> `source_server_id` comes from `hcloud SMS ListServers` after agent registration.
> `target_vm_id` and `target_vm_name` come from the Terraform target server creation skill.
> Disk info is fetched automatically via `hcloud SMS ShowServer`.

## Workflow

### Step 1: Read JSON Input

Parse the input file. Validate required fields:
- Top level: `region_id`, `region_name`, `project_id`, `project_name`
- Per server: `hostname`, `source_server_id`, `os_type`, `target_vm_id`, `target_vm_name`

### Step 2: Fetch Source Server Disk Info

For each source server, fetch disk information via hcloud CLI:

```bash
hcloud SMS ShowServer --cli-region=<region> --source_id=<source_server_id>
```

The script `scripts/create_tasks.py --fetch-disks` does this automatically.

### Step 3: Generate Commands and Show Summary

```bash
python3 scripts/create_tasks.py --input tasks.json --fetch-disks
```

Outputs a JSON summary with task creation commands (one per source server).

### Step 4: Approval Gate 1 — Before Creation

Present the summary to the user:

```
About to create:
  Tasks: 3
    server-01_0915: source xxx -> target yyy (LINUX, MIGRATE_FILE)
    server-02_0915: source xxx -> target yyy (WINDOWS, MIGRATE_BLOCK)
    server-03_0915: source xxx -> target yyy (LINUX, MIGRATE_FILE)
  Network: Private (no EIP)
  All tasks will be in READY state after creation (not started)

Confirm? (ok / cancel)
```

Wait for explicit user confirmation ("ok", "确认", "continue").

### Step 5: Create Tasks (one per source server)

For each source server, execute CreateTask:

```bash
hcloud SMS CreateTask --cli-region=<region> \
  --name="<hostname>_<MMDD>" \
  --type=MIGRATE_FILE \
  --os_type=LINUX \
  --syncing=false \
  --use_public_ip=false \
  --start_target_server=true \
  --region_name=<region_name> --region_id=<region_id> \
  --project_name=<project_name> --project_id=<project_id> \
  --source_server.id=<source_server_id> \
  --target_server.name=<target_vm_name> \
  --target_server.vm_id=<target_vm_id> \
  --target_server.disks.1.disk_id=<disk_id> \
  --target_server.disks.1.name=/dev/vda \
  --target_server.disks.1.size=<size> \
  --target_server.disks.1.device_use=BOOT
```

> No `--vm_template_id` — target ECS already exists.
> No `--template.publicip.*` — private network only.

Save each returned task ID. If any task creation fails, call
`huawei-cloud-sms-troubleshooting` skill and report to user.

### Step 6: Approval Gate 2 — Before Start

After all tasks are created (state=READY), present:

```
Tasks created successfully:
  server-01_0915 -> task_id: xxx (READY)
  server-02_0915 -> task_id: xxx (READY)
  server-03_0915 -> task_id: xxx (READY)

Start all tasks? (ok / cancel)
```

Wait for explicit user confirmation.

### Step 7: Start Tasks

For each task:

```bash
hcloud SMS UpdateTaskStatus --cli-region=<region> --task_id=<task_id> --operation=start
```

After starting, report task IDs to user. Monitoring is a separate skill.

## Error Handling

When any step fails:

1. **Do NOT operate anything** on Huawei Cloud.
2. **Call `huawei-cloud-sms-troubleshooting`** skill to check for known issues.
3. **Report to user**: describe the issue, possible causes, potential resolutions.
4. **Wait for approval**: user decides whether to proceed with resolution.
5. **Record new issues** in the troubleshooting skill's KNOWN_ISSUES.md.

## hcloud CLI Quick Reference

| Action | Command |
|--------|---------|
| List sources | `hcloud SMS ListServers --cli-region=<region>` |
| Show source | `hcloud SMS ShowServer --cli-region=<region> --source_id=<id>` |
| Create task | `hcloud SMS CreateTask --cli-region=<region> ...` |
| Start task | `hcloud SMS UpdateTaskStatus --cli-region=<region> --task_id=<id> --operation=start` |
| Show task | `hcloud SMS ShowTask --cli-region=<region> --task_id=<id>` |

See references/TASK_CREATION_REFERENCE.md section 5 for full command templates.

## File Structure

```
huawei-cloud-sms-task-creation/
├── SKILL.md                              ← This file
├── references/
│   └── TASK_CREATION_REFERENCE.md        ← API params, CLI commands, error codes
└── scripts/
    └── create_tasks.py                   ← Command generation script
```

## Companion Skills

- **huawei-cloud-sms-troubleshooting**: Error handling and issue tracking
- **huawei-cloud-sms-agent-installation**: Prior step — agent installation
- Target server creation skill (Terraform, future): Prior step — create target ECS
- Monitoring skill (future): Next step — monitor task progress
