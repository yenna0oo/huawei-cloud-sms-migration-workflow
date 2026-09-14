# SMS Task Creation — Detailed Reference

> API parameters sourced from Huawei Cloud SMS API snapshot (local)
> and official documentation:
> - CreateTask: POST /v3/tasks
> - UpdateTaskStatus: POST /v3/tasks/{task_id}/action
> - ShowServer: GET /v3/sources/{source_id}
> - ListServers: GET /v3/sources
> - API example: https://support.huaweicloud.com/api-sms/sms_api_0011.html

---

## Table of Contents

1. [Input JSON Format](#1-input-json-format)
2. [CreateTask API](#2-createtask-api)
3. [UpdateTaskStatus API](#3-updatetaskstatus-api)
4. [Task State Lifecycle](#4-task-state-lifecycle)
5. [hcloud CLI Commands](#5-hcloud-cli-commands)
6. [Naming Conventions](#6-naming-conventions)
7. [Error Codes](#7-error-codes)

---

## 1. Input JSON Format

Target ECS instances are created beforehand by a separate Terraform skill.
This skill links existing source servers to existing target servers — no
template creation, no auto-create.

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
        },
        {
            "hostname": "server-02",
            "source_server_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxx0002",
            "os_type": "WINDOWS",
            "migration_type": "MIGRATE_BLOCK",
            "target_vm_id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyy0003",
            "target_vm_name": "server-02-target"
        }
    ]
}
```

### Field Documentation

#### Shared fields (region/project level)

| Field | Description | Required | Source |
|-------|-------------|----------|--------|
| region_id | Target region ID | Yes | Huawei Cloud console |
| region_name | Target region name | Yes | Huawei Cloud console |
| project_id | Target project ID | Yes | My Credentials page |
| project_name | Target project name | Yes | My Credentials page |

#### Per-server fields (one task per entry)

| Field | Description | Required | Source |
|-------|-------------|----------|--------|
| hostname | Source server hostname | Yes | User input |
| source_server_id | SMS source server ID | Yes | `hcloud SMS ListServers` |
| os_type | LINUX or WINDOWS | Yes | ListServers or user input |
| migration_type | MIGRATE_FILE or MIGRATE_BLOCK | No | Default: MIGRATE_FILE |
| target_vm_id | Existing target ECS VM ID | Yes | Terraform output / ECS console |
| target_vm_name | Existing target ECS name | Yes | Terraform output / ECS console |

> Disk info (disk_id, size, physical_volumes) is fetched automatically
> via `hcloud SMS ShowServer` at runtime — no need to provide in input.

---

## 2. CreateTask API

**Endpoint**: `POST /v3/tasks`
**Description**: Create a migration task linking a source server to an existing target server

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| name | string | Task name (max 64 chars) |
| type | string | MIGRATE_FILE or MIGRATE_BLOCK |
| os_type | string | LINUX or WINDOWS |
| source_server.id | string | Source server ID (from ListServers) |
| target_server.name | string | Existing target server name |
| target_server.vm_id | string | Existing target ECS VM ID |
| target_server.disks | array | Disk info (from ShowServer) |
| region_name | string | Region name |
| region_id | string | Region ID |
| project_name | string | Project name |
| project_id | string | Project ID |

### Critical Parameters (must set explicitly)

| Parameter | Value | Reason |
|-----------|-------|--------|
| syncing | false | Skip incremental sync (avoids 80% vols_map errors) |
| use_public_ip | false | Private network only (no EIP) |
| start_target_server | true | Start target after migration |

### NOT Used (existing target servers)

| Parameter | Reason |
|-----------|--------|
| vm_template_id | Not auto-creating ECS. Target already exists. |
| clonevm_template_id | Not cloning. |

### Target Server Disk Info

Disk info is fetched from `hcloud SMS ShowServer`:

```json
{
    "disks": [{
        "name": "/dev/vda",
        "disk_id": "xxx-xxx-xxx",
        "size": 42949672960,
        "device_use": "BOOT",
        "physical_volumes": [{
            "uuid": null,
            "index": 0,
            "name": "/dev/vda1",
            "device_use": "OS",
            "file_system": "ext4",
            "mount_point": "/",
            "size": 42947575808,
            "used_size": 5346484224
        }]
    }]
}
```

### Response

```json
{ "id": "xxxxxxxxxxxxxxxxxxxxxxxx00000001" }
```

The returned `id` is the task ID, used for UpdateTaskStatus.

---

## 3. UpdateTaskStatus API

**Endpoint**: `POST /v3/tasks/{task_id}/action`
**Description**: Start, stop, or manage a migration task

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| operation | string | Action to perform |

### Operation Values

| Value | Description |
|-------|-------------|
| start | Start the migration task |
| stop | Stop the migration task |
| cutover | Start cutover (launch target server) |
| restart | Restart the task |

### Example

```bash
hcloud SMS UpdateTaskStatus --cli-region=<region> --task_id=<task_id> --operation=start
```

---

## 4. Task State Lifecycle

```
READY -> RUNNING -> MIGRATE_FAIL / SYNCING / CUTOVER_READY
```

| State | Description |
|-------|-------------|
| READY | Task created, waiting to start |
| RUNNING | Migration in progress |
| MIGRATE_FAIL | Migration failed |
| SYNCING | Incremental sync in progress |
| CUTOVER_READY | Ready for cutover |

---

## 5. hcloud CLI Commands

### 5.1 List Source Servers

```bash
hcloud SMS ListServers --cli-region=<region>
```

### 5.2 Show Source Server Details (get disk info)

```bash
hcloud SMS ShowServer --cli-region=<region> --source_id=<source_server_id>
```

### 5.3 Create Task (link to existing target server)

```bash
hcloud SMS CreateTask --cli-region=<region> \
  --name="<hostname>_<MMDD>" \
  --type="MIGRATE_FILE" \
  --os_type="LINUX" \
  --syncing=false \
  --use_public_ip=false \
  --start_target_server=true \
  --region_name="<region_name>" \
  --region_id="<region_id>" \
  --project_name="<project_name>" \
  --project_id="<project_id>" \
  --source_server.id="<source_server_id>" \
  --target_server.name="<target_vm_name>" \
  --target_server.vm_id="<target_vm_id>" \
  --target_server.disks.1.disk_id="<disk_id>" \
  --target_server.disks.1.name="/dev/vda" \
  --target_server.disks.1.size=<size> \
  --target_server.disks.1.device_use="BOOT"
```

> No `--vm_template_id` — target ECS already exists.
> No `--template.publicip.*` — private network only.

### 5.4 Start Task

```bash
hcloud SMS UpdateTaskStatus --cli-region=<region> \
  --task_id=<task_id> \
  --operation=start
```

### 5.5 Show Task Status

```bash
hcloud SMS ShowTask --cli-region=<region> --task_id=<task_id>
```

---

## 6. Naming Conventions

| Resource | Format | Example |
|----------|--------|---------|
| Migration task | `{hostname}_{MMDD}` | `server-01_0915` |

- `{MMDD}` = current date month + day (e.g. September 15 = `0915`)
- `{hostname}` = source server hostname from input JSON

---

## 7. Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| SMS.6030 | Illegal source id | Check source_server_id from ListServers |
| SMS.6031 | Missing target_server info | Add target_server parameters |
| SMS.6032 | Missing vm_id | Add target_server.vm_id (existing ECS ID) |
| SMS.6033 | Missing disk info | Fetch disk info from ShowServer |
| SMS.6539 | Target disk too small | Increase target disk size |
| SMS.6601 | Invalid OS type | Set os_type to LINUX or WINDOWS |
| SMS.6610 | Task type / OS type mismatch | Match migration_type with os_type |
| SMS.7602 | Source server does not exist | Verify agent registered, check ListServers |
| SMS.7711 | Illegal task name | Use valid chars: letters, digits, underscore, hyphen |
| SMS.7712 | Illegal task type | Use MIGRATE_FILE or MIGRATE_BLOCK |

> On any error: call `huawei-cloud-sms-troubleshooting` skill,
> report to user, wait for approval before any action.
