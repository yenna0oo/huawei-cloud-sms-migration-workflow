# Target Server Creation — Detailed Reference

> Terraform templates referenced from:
> `huawei-cloud-terraform-generator/assets/ecs/basic/`
>
> Huawei Cloud Terraform provider docs:
> https://registry.terraform.io/providers/huaweicloud/huaweicloud/latest/docs

---

## Table of Contents

1. [Input JSON Format](#1-input-json-format)
2. [Terraform Template Structure](#2-terraform-template-structure)
3. [Output JSON Format](#3-output-json-format)
4. [OBS Upload](#4-obs-upload)
5. [Existing Resource Lookup](#5-existing-resource-lookup)

---

## 1. Input JSON Format

Each server has its full spec. VPC, subnet, and security group are referenced
by name (existing resources — Terraform data sources resolve names to IDs).

```json
{
    "region": "ap-southeast-3",
    "servers": [
        {
            "ecs_name": "server-01-target",
            "availability_zone": "ap-southeast-3a",
            "flavor_id": "s6.large.2",
            "image_id": "xxx-xxx-xxx",
            "vpc_name": "vpc-migration",
            "subnet_name": "subnet-migration",
            "security_group_name": "sg-migration",
            "system_disk_size": 40,
            "system_disk_type": "SAS",
            "data_disk_size": 100,
            "data_disk_type": "SAS",
            "admin_password": "********",
            "os_type": "LINUX"
        },
        {
            "ecs_name": "server-02-target",
            "availability_zone": "ap-southeast-3a",
            "flavor_id": "s6.xlarge.2",
            "image_id": "yyy-yyy-yyy",
            "vpc_name": "vpc-migration",
            "subnet_name": "subnet-migration",
            "security_group_name": "sg-migration",
            "system_disk_size": 40,
            "system_disk_type": "SAS",
            "data_disk_size": 0,
            "data_disk_type": "SAS",
            "admin_password": "********",
            "os_type": "WINDOWS"
        }
    ]
}
```

### Field Documentation

| Field | Description | Required | Example |
|-------|-------------|----------|---------|
| region | Huawei Cloud region | Yes | `ap-southeast-3` |
| servers | Array of server specs | Yes | |
| ecs_name | Target ECS name (user-defined) | Yes | `server-01-target` |
| availability_zone | AZ for the ECS | Yes | `ap-southeast-3a` |
| flavor_id | ECS flavor ID | Yes | `s6.large.2` |
| image_id | Image ID matching source OS | Yes | `xxx-xxx-xxx` |
| vpc_name | Existing VPC name | Yes | `vpc-migration` |
| subnet_name | Existing subnet name | Yes | `subnet-migration` |
| security_group_name | Existing security group name | Yes | `sg-migration` |
| system_disk_size | System disk size in GB | Yes | `40` |
| system_disk_type | System disk type | Yes | `SAS` |
| data_disk_size | Data disk size in GB (0 = none) | Yes | `100` |
| data_disk_type | Data disk type | No | `SAS` |
| admin_password | ECS admin password | Yes | `********` |
| os_type | LINUX or WINDOWS (for output) | Yes | `LINUX` |

---

## 2. Terraform Template Structure

This skill generates a single Terraform project with one state file for all
ECS in the batch. The template uses **data sources** to look up existing
VPC/subnet/SG by name, and creates only `huaweicloud_compute_instance` resources.

### providers.tf

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.50.0"
    }
  }
}

provider "huaweicloud" {
  region     = var.region
  access_key = var.access_key
  secret_key = var.secret_key
}
```

### main.tf (generated per batch)

```hcl
# Data sources: look up existing VPC, subnet, security group by name
data "huaweicloud_vpc_vpc" "vpc" {
  name = var.vpc_name
}

data "huaweicloud_vpc_subnet" "subnet" {
  name   = var.subnet_name
  vpc_id = data.huaweicloud_vpc_vpc.vpc.id
}

data "huaweicloud_networking_secgroup" "sg" {
  name = var.security_group_name
}

# ECS instance: server-01-target
resource "huaweicloud_compute_instance" "server_01_target" {
  name              = "server-01-target"
  availability_zone = "ap-southeast-3a"
  flavor_id         = "s6.large.2"
  image_id          = "xxx-xxx-xxx"
  admin_pass        = "********"
  security_group_ids = [
    data.huaweicloud_networking_secgroup.sg.id
  ]

  network {
    uuid = data.huaweicloud_vpc_subnet.subnet.id
  }

  system_disk_type = "SAS"
  system_disk_size = 40

  data_disks {
    type = "SAS"
    size = 100
  }
}

# Output: VM IDs for task-creation input
output "vm_ids" {
  value = {
    "server-01-target" = huaweicloud_compute_instance.server_01_target.id
  }
}
```

> For servers with `data_disk_size = 0`, the `data_disks` block is omitted.
> All servers in the batch share the same VPC/subnet/SG data sources.

---

## 3. Output JSON Format

After `terraform apply`, the script extracts VM IDs from Terraform output
and generates a JSON file matching the `huawei-cloud-sms-task-creation` input
format. Source server fields are left blank for the user to fill in.

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
            "target_vm_id": "actual-vm-id-from-terraform",
            "target_vm_name": "server-01-target"
        },
        {
            "hostname": "",
            "source_server_id": "",
            "os_type": "WINDOWS",
            "migration_type": "",
            "target_vm_id": "actual-vm-id-from-terraform",
            "target_vm_name": "server-02-target"
        }
    ]
}
```

### Fields Left Blank (user fills in)

| Field | Why blank |
|-------|-----------|
| region_name | User knows their region display name |
| project_id | User gets from My Credentials |
| project_name | User gets from My Credentials |
| hostname | Source server hostname (from agent registration) |
| source_server_id | SMS source server ID (from `hcloud SMS ListServers`) |
| migration_type | User decides: MIGRATE_FILE or MIGRATE_BLOCK |

### Fields Auto-filled

| Field | Source |
|-------|--------|
| region_id | From input JSON |
| os_type | From input JSON |
| target_vm_id | From Terraform output |
| target_vm_name | From input JSON (ecs_name) |

---

## 4. OBS Upload

After generating the output JSON, the script uploads it to OBS.

### Upload Command

```bash
hcloud OBS PutObject \
  --cli-region=<region> \
  --bucket=<bucket-name> \
  --key=<object-key> \
  --body=@output.json
```

Or using obsutil:

```bash
obsutil cp output.json obs://<bucket-name>/<object-key>
```

### Workflow

1. User runs this skill with input JSON
2. Skill creates ECS via Terraform
3. Skill generates output JSON with VM IDs
4. Skill asks user: "Enter the OBS path for the output file (e.g. obs://my-bucket/task-creation-input.json)"
5. Skill uploads the output JSON to the specified OBS path
6. User fills in blank fields (hostname, source_server_id, etc.)
7. User runs `huawei-cloud-sms-task-creation` with the same OBS path as input

---

## 5. Existing Resource Lookup

Terraform data sources resolve resource names to IDs at plan time:

| Data Source | Looks Up | By |
|-------------|----------|-----|
| `huaweicloud_vpc_vpc` | VPC ID | name |
| `huaweicloud_vpc_subnet` | Subnet ID | name + vpc_id |
| `huaweicloud_networking_secgroup` | Security Group ID | name |

> If a named resource doesn't exist, `terraform plan` will fail with a clear
> error. The user can then verify the resource name or create it manually.
