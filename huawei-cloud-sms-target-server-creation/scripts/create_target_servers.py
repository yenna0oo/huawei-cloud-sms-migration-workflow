#!/usr/bin/env python3
"""
Target Server Creation Script

Reads a JSON input with per-server ECS specs, generates Terraform configs
that reference existing VPC/subnet/SG by name (via data sources), runs
terraform init/plan, and after user approval runs terraform apply.

After apply, extracts VM IDs from terraform output, generates an output
JSON matching huawei-cloud-sms-task-creation input format (with source
server fields blank), and uploads to OBS.

Usage:
    python3 create_target_servers.py --input servers.json --workdir /tmp/tf-targets
    python3 create_target_servers.py --input servers.json --workdir /tmp/tf-targets --apply

Stages:
    1. Generate Terraform files (always)
    2. terraform init + plan (always)
    3. terraform apply (only with --apply flag, after user approval)
    4. Extract VM IDs + generate output JSON (after apply)
    5. Upload to OBS (after apply, user provides OBS path)
"""

import argparse
import json
import os
import re
import subprocess
import sys


def run_cmd(cmd, cwd=None, timeout=120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", -1
    except Exception as e:
        return "", str(e), -1


def sanitize_name(name):
    """Convert ECS name to valid Terraform resource name."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def generate_providers_tf():
    return '''terraform {
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
'''


def generate_variables_tf():
    return '''variable "region" {
  description = "Huawei Cloud region"
  type        = string
}

variable "access_key" {
  description = "IAM access key"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "IAM secret key"
  type        = string
  sensitive   = true
}

variable "vpc_name" {
  description = "Existing VPC name"
  type        = string
}

variable "subnet_name" {
  description = "Existing subnet name"
  type        = string
}

variable "security_group_name" {
  description = "Existing security group name"
  type        = string
}
'''


def generate_main_tf(servers):
    """Generate main.tf with data sources and one compute_instance per server."""
    lines = []
    lines.append('# Data sources: look up existing VPC, subnet, security group by name')
    lines.append('data "huaweicloud_vpc_vpc" "vpc" {')
    lines.append('  name = var.vpc_name')
    lines.append('}')
    lines.append('')
    lines.append('data "huaweicloud_vpc_subnet" "subnet" {')
    lines.append('  name   = var.subnet_name')
    lines.append('  vpc_id = data.huaweicloud_vpc_vpc.vpc.id')
    lines.append('}')
    lines.append('')
    lines.append('data "huaweicloud_networking_secgroup" "sg" {')
    lines.append('  name = var.security_group_name')
    lines.append('}')
    lines.append('')

    output_entries = []

    for srv in servers:
        ecs_name = srv["ecs_name"]
        res_name = sanitize_name(ecs_name)
        lines.append(f'# ECS instance: {ecs_name}')
        lines.append(f'resource "huaweicloud_compute_instance" "{res_name}" {{')
        lines.append(f'  name              = "{ecs_name}"')
        lines.append(f'  availability_zone = "{srv["availability_zone"]}"')
        lines.append(f'  flavor_id         = "{srv["flavor_id"]}"')
        lines.append(f'  image_id          = "{srv["image_id"]}"')
        lines.append(f'  admin_pass        = "{srv["admin_password"]}"')
        lines.append('  security_group_ids = [')
        lines.append('    data.huaweicloud_networking_secgroup.sg.id')
        lines.append('  ]')
        lines.append('')
        lines.append('  network {')
        lines.append('    uuid = data.huaweicloud_vpc_subnet.subnet.id')
        lines.append('  }')
        lines.append('')
        lines.append(f'  system_disk_type = "{srv["system_disk_type"]}"')
        lines.append(f'  system_disk_size = {srv["system_disk_size"]}')

        if srv.get("data_disk_size", 0) > 0:
            lines.append('')
            lines.append('  data_disks {')
            lines.append(f'    type = "{srv.get("data_disk_type", "SAS")}"')
            lines.append(f'    size = {srv["data_disk_size"]}')
            lines.append('  }')

        lines.append('}')
        lines.append('')
        output_entries.append(f'    "{ecs_name}" = huaweicloud_compute_instance.{res_name}.id')

    # Outputs
    lines.append('output "vm_ids" {')
    lines.append('  value = {')
    lines.extend(output_entries)
    lines.append('  }')
    lines.append('}')
    lines.append('')

    return '\n'.join(lines)


def generate_tfvars(region, vpc_name, subnet_name, sg_name):
    return f'''region = "{region}"
vpc_name = "{vpc_name}"
subnet_name = "{subnet_name}"
security_group_name = "{sg_name}"
'''


def terraform_init(workdir):
    return run_cmd(["terraform", "init"], cwd=workdir, timeout=120)


def terraform_plan(workdir):
    return run_cmd(["terraform", "plan", "-input=false"], cwd=workdir, timeout=300)


def terraform_apply(workdir):
    return run_cmd(["terraform", "apply", "-auto-approve", "-input=false"],
                   cwd=workdir, timeout=600)


def terraform_output(workdir):
    out, err, rc = run_cmd(["terraform", "output", "-json"], cwd=workdir)
    if rc != 0:
        return None, f"terraform output failed: {err}"
    try:
        return json.loads(out), None
    except json.JSONDecodeError:
        return None, f"Parse error: {out[:200]}"


def generate_output_json(input_data, vm_ids):
    """Generate output JSON matching task-creation input format."""
    servers = input_data["servers"]
    output = {
        "region_id": input_data["region"],
        "region_name": "",
        "project_id": "",
        "project_name": "",
        "source_servers": []
    }

    vm_ids_value = vm_ids.get("vm_ids", {}).get("value", {})

    for srv in servers:
        ecs_name = srv["ecs_name"]
        vm_id = vm_ids_value.get(ecs_name, "")
        output["source_servers"].append({
            "hostname": "",
            "source_server_id": "",
            "os_type": srv.get("os_type", "LINUX"),
            "migration_type": "",
            "target_vm_id": vm_id,
            "target_vm_name": ecs_name,
        })

    return output


def upload_to_obs(region, obs_path, file_path):
    """Upload file to OBS using hcloud CLI."""
    # Parse obs://bucket/key format
    obs_path = obs_path.replace("obs://", "")
    parts = obs_path.split("/", 1)
    if len(parts) != 2:
        return False, f"Invalid OBS path: {obs_path}. Expected obs://bucket/key"
    bucket, key = parts

    out, err, rc = run_cmd([
        "hcloud", "OBS", "PutObject",
        f"--cli-region={region}",
        f"--bucket={bucket}",
        f"--key={key}",
        f"--body=@{file_path}",
    ])
    if rc != 0:
        return False, f"OBS upload failed: {err}"
    return True, None


def main():
    parser = argparse.ArgumentParser(description="Create target ECS via Terraform")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    parser.add_argument("--workdir", required=True, help="Working directory for Terraform")
    parser.add_argument("--apply", action="store_true",
                        help="Run terraform apply (requires prior plan approval)")
    parser.add_argument("--obs-path", default=None,
                        help="OBS path for output JSON (e.g. obs://bucket/key)")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)

    servers = data["servers"]
    region = data["region"]

    if not servers:
        print(json.dumps({"error": "No servers in input"}, indent=2))
        sys.exit(1)

    # All servers should share the same VPC/subnet/SG (batch)
    vpc_name = servers[0]["vpc_name"]
    subnet_name = servers[0]["subnet_name"]
    sg_name = servers[0]["security_group_name"]

    # Validate all servers use the same VPC/subnet/SG
    for s in servers:
        if s["vpc_name"] != vpc_name or s["subnet_name"] != subnet_name or s["security_group_name"] != sg_name:
            print("ERROR: All servers in a batch must use the same VPC/subnet/security group.")
            sys.exit(1)

    # Generate Terraform files
    os.makedirs(args.workdir, exist_ok=True)

    with open(os.path.join(args.workdir, "providers.tf"), "w") as f:
        f.write(generate_providers_tf())

    with open(os.path.join(args.workdir, "variables.tf"), "w") as f:
        f.write(generate_variables_tf())

    with open(os.path.join(args.workdir, "main.tf"), "w") as f:
        f.write(generate_main_tf(servers))

    with open(os.path.join(args.workdir, "terraform.tfvars"), "w") as f:
        f.write(generate_tfvars(region, vpc_name, subnet_name, sg_name))

    print(f"Terraform files generated in {args.workdir}")
    print(f"  Servers: {len(servers)}")
    for s in servers:
        print(f"    {s['ecs_name']} ({s['flavor_id']}, {s['system_disk_size']}GB system"
              f"{' + ' + str(s.get('data_disk_size', 0)) + 'GB data' if s.get('data_disk_size', 0) > 0 else ''})")
    print()

    # terraform init
    print("Running terraform init...")
    out, err, rc = terraform_init(args.workdir)
    if rc != 0:
        print(f"terraform init FAILED:\n{err}")
        sys.exit(1)
    print("terraform init OK\n")

    # terraform plan
    print("Running terraform plan...")
    out, err, rc = terraform_plan(args.workdir)
    if rc != 0:
        print(f"terraform plan FAILED:\n{out}\n{err}")
        print("\nReport this error to the user. Ask for approval before any action.")
        sys.exit(1)
    print("terraform plan output:")
    print(out)
    print("\nReview the plan above. Run with --apply to proceed after user approval.")

    if not args.apply:
        print("\nTo apply: re-run with --apply flag after user confirms 'ok'")
        sys.exit(0)

    # terraform apply
    print("\nRunning terraform apply...")
    out, err, rc = terraform_apply(args.workdir)
    if rc != 0:
        print(f"terraform apply FAILED:\n{out}\n{err}")
        print("\nReport this error to the user. Ask for approval before any action.")
        sys.exit(1)
    print("terraform apply OK\n")

    # Extract VM IDs
    vm_ids, err = terraform_output(args.workdir)
    if err:
        print(f"Failed to get terraform output: {err}")
        sys.exit(1)

    # Generate output JSON
    output_json = generate_output_json(data, vm_ids)
    output_path = os.path.join(args.workdir, "task_creation_input.json")
    with open(output_path, "w") as f:
        json.dump(output_json, f, indent=2)

    print("=== Resource Creation Summary ===")
    print(f"  ECS instances created: {len(servers)}")
    for srv in output_json["source_servers"]:
        print(f"    {srv['target_vm_name']} -> VM ID: {srv['target_vm_id']} ({srv['os_type']})")
    print(f"\n  Output JSON: {output_path}")
    print(f"  (Source server fields left blank for user to fill in)")
    print()

    # Upload to OBS
    obs_path = args.obs_path
    if not obs_path:
        obs_path = input("Enter OBS path for output file (e.g. obs://my-bucket/task-creation-input.json): ").strip()

    if obs_path:
        ok, err = upload_to_obs(region, obs_path, output_path)
        if ok:
            print(f"\nOutput JSON uploaded to: {obs_path}")
        else:
            print(f"\nOBS upload failed: {err}")
            print(f"Output JSON is available locally at: {output_path}")
    else:
        print(f"\nOutput JSON saved locally at: {output_path}")

    print("\nNext step: Fill in blank fields (hostname, source_server_id, etc.)")
    print("Then run huawei-cloud-sms-task-creation with this file as input.")


if __name__ == "__main__":
    main()
