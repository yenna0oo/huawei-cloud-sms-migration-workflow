---
name: huawei-cloud-sms-migration-workflow
description: Orchestrate the complete Huawei Cloud SMS server migration workflow end-to-end. Drives a 4-step sequential pipeline: (1) install SMS agents on source hosts, (2) create target ECS instances via Terraform, (3) create SMS migration tasks linking source to target, (4) monitor migration task progress. A companion troubleshooting skill is available on-demand at any step. Each step requires explicit user approval before proceeding to the next. Use when the user asks to: (1) migrate servers to Huawei Cloud, (2) run the full SMS migration workflow, (3) orchestrate server migration, (4) start migration pipeline. Triggers on phrases like "migrate servers", "迁移服务器", "run migration workflow", "执行迁移流程", "start SMS migration", "full migration", "端到端迁移".
---

# huawei-cloud-sms-migration-workflow

## Overview

Active driver for the complete SMS server migration workflow. When triggered,
guides the agent through 4 sequential steps, asking for user approval between
each step. A companion troubleshooting skill is called on-demand when any
step encounters an error.

```
Step 1: Install SMS Agents          → huawei-cloud-sms-agent-installation
    ↓ (user approval)
Step 2: Create Target ECS           → huawei-cloud-sms-target-server-creation
    ↓ (user approval)
Step 3: Create Migration Tasks      → huawei-cloud-sms-task-creation
    ↓ (user approval)
Step 4: Monitor Task Progress       → huawei-cloud-sms-task-monitoring

On-demand: Troubleshoot Errors      → huawei-cloud-sms-troubleshooting
```

## Safety Rules

1. **Approval between every step** — After each step completes, show a summary
   and wait for explicit user "ok" / "确认" before starting the next step.
2. **Sequential only** — Steps run one at a time. No parallel execution.
3. **Per-step inputs** — Each step has its own input file. The user provides
   the input location (OBS path or local file) at the start of each step.
4. **Report, don't auto-fix** — On any error, call
   `huawei-cloud-sms-troubleshooting` skill, report to user, wait for approval.
5. **Source VMs are read-only** — No modifications to source servers except
   the SMS Agent installation itself.

## Workflow

### Step 1: Install SMS Agents on Source Hosts

**Skill**: `huawei-cloud-sms-agent-installation`

**Input**: User provides the location of a JSON file with source host details
(hostname, IP, OS, SSH key, region, SMS domain, OBS path for agent package).

```
Agent: "Step 1 — Install SMS Agents. Where is the input JSON file?"
User:   "obs://my-bucket/agent-install-input.json"
Agent:  [reads input, runs pre-checks, installs agents, verifies connectivity]
Agent:  "Step 1 complete. 3 agents installed and connected.
         Proceed to Step 2 (create target ECS)? (ok / cancel)"
User:   "ok"
```

**What happens**:
1. Read input JSON (source host details)
2. Run pre-installation checks (CPU, memory, disk, OS, components)
3. Check for existing agents (skip if already installed)
4. Download agent package from OBS
5. Install and start agent with safe credential passing
6. Verify agent connectivity to SMS service
7. Report summary, wait for approval

**Output**: Source servers registered in SMS console (visible via
`hcloud SMS ListServers`). Source server IDs are available for step 3.

---

### Step 2: Create Target ECS Instances

**Skill**: `huawei-cloud-sms-target-server-creation`

**Input**: User provides the location of a JSON file with per-server ECS specs
(flavor, image, VPC/subnet/SG by name, disk sizes, password).

```
Agent: "Step 2 — Create Target ECS. Where is the input JSON file?"
User:   "obs://my-bucket/target-server-specs.json"
Agent:  [reads input, generates Terraform, runs terraform plan]
Agent:  [shows plan output]
Agent:  "Review the plan. Apply? (ok / cancel)"
User:   "ok"
Agent:  [terraform apply, extracts VM IDs, generates output JSON]
Agent:  "Step 2 complete. 3 ECS instances created.
         Where should I upload the output JSON for step 3?"
User:   "obs://my-bucket/task-creation-input.json"
Agent:  [uploads to OBS]
Agent:  "Output JSON uploaded. Fill in the blank fields (hostname,
         source_server_id, etc.) and update the file.
         Proceed to Step 3 (create migration tasks)? (ok / cancel)"
User:   "ok"
```

**What happens**:
1. Read input JSON (ECS specs)
2. Generate Terraform configs (data sources for existing VPC/subnet/SG)
3. Run `terraform init` + `terraform plan`
4. **Approval gate**: show plan, wait for "ok"
5. Run `terraform apply`
6. Extract VM IDs from Terraform output
7. Generate output JSON matching task-creation input format
   (source server fields left blank)
8. Ask user for OBS path, upload output JSON
9. Wait for approval before step 3

**Output**: JSON file on OBS with target VM IDs/names, blank source fields.
User fills in `hostname`, `source_server_id`, `migration_type`,
`region_name`, `project_id`, `project_name`.

---

### Step 3: Create SMS Migration Tasks

**Skill**: `huawei-cloud-sms-task-creation`

**Input**: User provides the location of the updated JSON file from step 2
(now with source server fields filled in).

```
Agent: "Step 3 — Create Migration Tasks. Where is the input JSON file?"
User:   "obs://my-bucket/task-creation-input.json"
Agent:  [reads input, fetches disk info via ShowServer, generates commands]
Agent:  [shows task summary]
Agent:  "Review the tasks. Create? (ok / cancel)"
User:   "ok"
Agent:  [creates tasks via hcloud CLI]
Agent:  "3 tasks created (READY state).
         Start all tasks? (ok / cancel)"
User:   "ok"
Agent:  [starts tasks via UpdateTaskStatus --operation=start]
Agent:  "Step 3 complete. 3 tasks started.
         Proceed to Step 4 (monitor)? (ok / cancel)"
User:   "ok"
```

**What happens**:
1. Read input JSON (source-target mapping)
2. Fetch disk info via `hcloud SMS ShowServer`
3. Generate task creation commands
4. **Approval gate 1**: show task summary, wait for "ok"
5. Create tasks via `hcloud SMS CreateTask` (one per source server)
6. **Approval gate 2**: wait for "ok" before starting
7. Start tasks via `hcloud SMS UpdateTaskStatus --operation=start`
8. Wait for approval before step 4

**Output**: Migration tasks in RUNNING state. Task IDs available for monitoring.

---

### Step 4: Monitor Migration Task Progress

**Skill**: `huawei-cloud-sms-task-monitoring`

**Input**: Region only (monitors all tasks via `hcloud SMS ListTasks`).

```
Agent: "Step 4 — Monitor Migration Tasks."
Agent:  [starts continuous polling, 60s interval]
Agent:  [reports state changes as they happen]
Agent:  [alerts on failures or stuck tasks]
...
Agent:  "All tasks reached terminal state.
         3 succeeded, 0 failed.
         Migration workflow complete."
```

**What happens**:
1. Poll `hcloud SMS ListTasks` every 60 seconds
2. For each active task, call `hcloud SMS ShowTask` for details
3. Report state changes to console (only on changes)
4. Detect stuck tasks (speed = 0 for 30 minutes)
5. On failure: call `huawei-cloud-sms-troubleshooting`, pause, wait for user
6. On success (MIGRATE_SUCCESS): report, stop monitoring that task
7. Exit when all tasks reach terminal state

**Output**: Migration complete. All tasks at MIGRATE_SUCCESS.

---

### On-Demand: Troubleshooting

**Skill**: `huawei-cloud-sms-troubleshooting`

Called by any step when an error occurs:

```
Agent: "Error in Step X: [error description]
         Possible causes: [causes]
         Potential resolution: [resolution]
         Checking known issues..."
Agent:  [calls troubleshooting skill]
Agent:  "This issue has been seen before. Resolution: [steps]
         Proceed with this resolution? (ok / cancel)"
User:   "ok"
Agent:  [executes resolution]
Agent:  "Issue resolved. Resuming Step X."
```

**What happens**:
1. Check `huawei-cloud-sms-troubleshooting` known issues
2. Report issue + possible resolution to user
3. Wait for user approval before any action
4. Execute resolution
5. Resume the interrupted step
6. Record new issues for future reference

> Note: Step 2 (Terraform) errors do NOT call the troubleshooting skill.
> Terraform errors are reported directly to the user with suggested fixes.

## Data Flow

```
User                    Step 1              Step 2              Step 3
  │                 (agent install)    (target ECS)      (task creation)
  │
  ├─ input JSON ──→ [source hosts]
  │                                    [ECS specs] ←── input JSON
  │                                    output JSON ──→ OBS
  │                                    (VM IDs, blank
  │                                     source fields)
  │                                                      ↓
  ├─ fill blanks ─────────────────────────────────────→ updated JSON
  │                                                      ↓
  │                                                      [tasks]
  │
  └─ approval between each step
```

## Approval Gates Summary

| Gate | Where | What user approves |
|------|-------|-------------------|
| 1 | After step 1 | Agents installed, proceed to create targets? |
| 2 | During step 2 | Terraform plan looks correct, apply? |
| 3 | After step 2 | Targets created, proceed to create tasks? |
| 4 | During step 3 | Task summary looks correct, create? |
| 5 | During step 3 | Tasks created, start them? |
| 6 | After step 3 | Tasks started, proceed to monitor? |

## Skills Used

| Step | Skill | Input | Output |
|------|-------|-------|--------|
| 1 | `huawei-cloud-sms-agent-installation` | Source host JSON | Agents registered in SMS |
| 2 | `huawei-cloud-sms-target-server-creation` | ECS specs JSON | Output JSON on OBS (VM IDs) |
| 3 | `huawei-cloud-sms-task-creation` | Updated JSON (source+target) | Migration tasks started |
| 4 | `huawei-cloud-sms-task-monitoring` | Region | Migration complete |
| * | `huawei-cloud-sms-troubleshooting` | Error details | Resolution (on-demand) |
