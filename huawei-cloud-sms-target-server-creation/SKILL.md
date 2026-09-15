---
name: huawei-cloud-sms-target-server-creation
description: Create target ECS instances on Huawei Cloud using Terraform for SMS server migration. Reads a JSON input file with per-server ECS specs, generates Terraform configs that reference existing VPC/subnet/security group by name, runs terraform plan/apply with user approval, and outputs VM IDs as a JSON file to OBS — ready for huawei-cloud-sms-task-creation to consume. Use when the user asks to:ECS for migration", "create target servers", "创建目的端服务器", "prepare target ECS", "生成目标ECS". Triggers on phrases like "create target ECS", "创建目的端", "create target servers for migration", "prepare target servers", "生成迁移目标服务器".
---

# huawei-cloud-sms-target-server-creation

## Overview

Create target ECS instances on Huawei Cloud using Terraform, as part of the
SMS migration workflow. Reads a JSON input with per-server specs, generates
Terraform configs that reference existing VPC/subnet/security group by name
(via Terraform data sources), runs plan/apply with approval, and outputs
VM IDs as a JSON file to OBS for the task-creation skill to consume.

This skill is part of a migration workflow:
1. `huawei-cloud-sms-agent-installation` — install agents on source hosts
2. **This skill** — create target ECS instances via Terraform
3. `huawei-cloud-sms-task-creation` — create tasks linking source to target
4. `huawei-cloud-sms-task-monitoring` — monitor task progress
5. `huawei-cloud-sms-troubleshooting` — error handling (companion)

## Safety Rules

1. **Approval gate** — Show `terraform plan` output, wait for user "ok"
   before `terraform apply`. No auto-apply.
2. **Existing infrastructure only** — VPC, subnet, security group must already
    exist. This skill only creates ECS instances. If a named resource doesn't
    exist, terraform plan will fail — report to user, do not auto-create.
3. **Error handling** — On Terraform errors, report the error and suggested
   resolution to user, ask approval for any action. Do NOT call
   `huawei-cloud-sms-troubleshooting` (errors are Terraform-related, not SMS).
4. **Single Terraform state** — All ECS in the batch share one state file.
   Batch-level management only.
5. **Output to OBS** — After apply, output JSON is uploaded to OBS at a
   user-specified path. The task-creation skill reads from the same path.

## Input Format

JSON file with region and per-server full specs. See
references/TARGET_SERVER_REFERENCE.md section 1 for full documentation.

```json
{
    "region": "ap-southeast-3",
    "servers": [
        {
            "ecs_name": "server-01-target",
            "availability_zone": "ap-southeast-3a",
            "flavor_id": "s6.large.2",
            "image_id": "xxx",
            "vpc_name": "vpc-migration",
            "subnet_name": "subnet-migration",
            "security_group_name": "sg-migration",
            "system_disk_size": 40,
            "system_disk_type": "SAS",
            "data_disk_size": 100,
            "data_disk_type": "SAS",
            "admin_password": "********",
            "os_type": "LINUX"
        }
    ]
}
```

> VPC, subnet, security group are referenced by **name** (not ID).
> Terraform data sources resolve names to IDs at plan time.

## Workflow

### Step 1: Read JSON Input

Parse the input file. Validate required fields per server:
`ecs_name`, `availability_zone`, `flavor_id`, `image_id`, `vpc_name`,
`subnet_name`, `security_group_name`, `system_disk_size`, `system_disk_type`,
`admin_password`, `os_type`.

All servers in the batch must share the same VPC/subnet/security group.

### Step 2: Generate Terraform Files

The script generates three files in the working directory:

- **providers.tf** — Huawei Cloud provider configuration
- **variables.tf** — Variable definitions (region, credentials, VPC/subnet/SG names)
- **main.tf** — Data sources for existing VPC/subnet/SG + one
  `huaweicloud_compute_instance` resource per server + outputs for VM IDs
- **terraform.tfvars** — Variable values from the JSON input

Templates referenced from `huawei-cloud-terraform-generator/assets/ecs/basic/`.

### Step 3: Terraform Init + Plan

```bash
python3 scripts/create_target_servers.py --input servers.json --workdir /tmp/tf-targets
```

This runs `terraform init` and `terraform plan`, then displays the plan.

### Step 4: Approval Gate

Show the `terraform plan` output to the user. Wait for explicit "ok" / "确认"
before proceeding to apply.

### Step 5: Terraform Apply

After user approval:

```bash
python3 scripts/create_target_servers.py --input servers.json --workdir /tmp/tf-targets --apply
```

This runs `terraform apply -auto-approve` and creates all ECS instances.

### Step 6: Extract VM IDs + Generate Output JSON

After apply, the script:
1. Runs `terraform output -json` to extract VM IDs
2. Generates an output JSON matching `huawei-cloud-sms-task-creation` input format
3. Source server fields (`hostname`, `source_server_id`, `migration_type`,
   `region_name`, `project_id`, `project_name`) are left **blank** for the
   user to fill in

### Step 7: Upload to OBS

The script asks the user for an OBS path:
```
Enter OBS path for output file (e.g. obs://my-bucket/task-creation-input.json):
```

Then uploads the output JSON to the specified OBS path using `hcloud OBS PutObject`.

### Step 8: Show Summary

```
=== Resource Creation Summary ===
  ECS instances created: 2
    server-01-target -> VM ID: xxx-xxx-xxx (LINUX)
    server-02-target -> VM ID: yyy-yyy-yyy (WINDOWS)

  Output JSON uploaded to: obs://my-bucket/task-creation-input.json
  (Source server fields left blank for user to fill in)

Next step: Fill in blank fields (hostname, source_server_id, etc.)
Then run huawei-cloud-sms-task-creation with this file as input.
```

## Error Handling

On any Terraform error (`init`, `plan`, or `apply` failure):

1. **Report the error** — Show the full error output to the user
2. **Suggest resolution** — Based on the error type:
   - Resource not found → check VPC/subnet/SG names
   - Insufficient quota → check ECS quota in the region
   - Invalid flavor/image → verify flavor_id and image_id
   - Auth failure → check AK/SK credentials
3. **Ask approval** — Wait for user to decide how to proceed
4. **Do NOT call `huawei-cloud-sms-troubleshooting`** — these are Terraform
   errors, not SMS migration errors

## Output JSON Format

The output JSON matches `huawei-cloud-sms-task-creation` input:

```json
{
    "region_id": "ap-southeast-3",
    "region_name": "",
    "project_id": "",
    "project_name": "",
    "source_servers": [
        {
            "hostname": "",
            "source_server_id": "",
            "os_type": "LINUX",
            "migration_type": "",
            "target_vm_id": "actual-vm-id",
            "target_vm_name": "server-01-target"
        }
    ]
}
```

See references/TARGET_SERVER_REFERENCE.md section 3 for field documentation.

## File Structure

```
huawei-cloud-sms-target-server-creation/
├── SKILL.md                              ← This file
├── references/
│   └── TARGET_SERVER_REFERENCE.md        ← Input/output formats, TF template, OBS
└── scripts/
    └── create_target_servers.py          ← Terraform generation + apply + output
```

## Companion Skills

- **huawei-cloud-terraform-generator**: Source of Terraform templates (referenced, not copied)
- **huawei-cloud-sms-task-creation**: Next step — reads the output JSON from OBS
- **huawei-cloud-sms-agent-installation**: Earlier step — agent installation
- **huawei-cloud-sms-task-monitoring**: Later step — monitor migration
