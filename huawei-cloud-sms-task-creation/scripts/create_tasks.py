#!/usr/bin/env python3
"""
SMS Task Creation Script

Reads a JSON input file with source-target server mapping,
fetches disk info via hcloud CLI ShowServer, and generates
hcloud CLI commands for CreateTask (one per source server).

Target ECS instances already exist (created by a separate Terraform skill).
This script does NOT create templates or auto-create ECS.

This script does NOT execute the commands — it only generates them for
user review and approval. The agent executes them after user confirms.

Usage:
    python3 create_tasks.py --input tasks.json
    python3 create_tasks.py --input tasks.json --region ap-southeast-3 --fetch-disks

Output: JSON report with task creation commands and summary for user review.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime


def get_mmdd():
    return datetime.now().strftime("%m%d")


def run_hcloud(args, timeout=30):
    try:
        result = subprocess.run(
            ["hcloud"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", -1
    except Exception as e:
        return "", str(e), -1


def fetch_source_disk_info(region, source_id):
    out, err, rc = run_hcloud([
        "SMS", "ShowServer",
        f"--cli-region={region}",
        f"--source_id={source_id}",
    ])
    if rc != 0:
        return None, f"ShowServer failed: {err}"
    try:
        data = json.loads(out)
        return data.get("disks", []), None
    except json.JSONDecodeError:
        return None, f"Could not parse ShowServer output: {out[:200]}"


def generate_task_command(server, data, mmdd, region):
    hostname = server["hostname"]
    task_name = f"{hostname}_{mmdd}"
    os_type = server.get("os_type", "LINUX")
    mig_type = server.get("migration_type", "MIGRATE_FILE")
    source_id = server["source_server_id"]
    target_vm_id = server["target_vm_id"]
    target_vm_name = server["target_vm_name"]

    cmd = [
        "hcloud", "SMS", "CreateTask",
        f"--cli-region={region}",
        f"--name={task_name}",
        f"--type={mig_type}",
        f"--os_type={os_type}",
        "--syncing=false",
        "--use_public_ip=false",
        "--start_target_server=true",
        f"--region_name={data['region_name']}",
        f"--region_id={data['region_id']}",
        f"--project_name={data['project_name']}",
        f"--project_id={data['project_id']}",
        f"--source_server.id={source_id}",
        f"--target_server.name={target_vm_name}",
        f"--target_server.vm_id={target_vm_id}",
    ]

    disks = server.get("_disk_info", [])
    for i, disk in enumerate(disks, 1):
        cmd.append(f"--target_server.disks.{i}.disk_id={disk.get('disk_id', '')}")
        cmd.append(f"--target_server.disks.{i}.name={disk.get('name', f'Disk {i-1}')}")
        cmd.append(f"--target_server.disks.{i}.size={disk.get('size', 0)}")
        cmd.append(f"--target_server.disks.{i}.device_use={disk.get('device_use', 'NORMAL')}")

    return {
        "task_name": task_name,
        "hostname": hostname,
        "source_server_id": source_id,
        "target_vm_id": target_vm_id,
        "target_vm_name": target_vm_name,
        "os_type": os_type,
        "command": " ".join(cmd),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate SMS task creation commands")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    parser.add_argument("--region", default=None, help="Override region for hcloud CLI")
    parser.add_argument("--fetch-disks", action="store_true",
                        help="Fetch disk info via ShowServer")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)

    servers = data["source_servers"]
    mmdd = get_mmdd()
    region = args.region or data["region_id"]

    required_top = ["region_id", "region_name", "project_id", "project_name"]
    missing = [f for f in required_top if f not in data]
    if missing:
        print(json.dumps({"error": f"Missing fields: {missing}"}, indent=2))
        sys.exit(1)

    if not servers:
        print(json.dumps({"error": "No source servers in input"}, indent=2))
        sys.exit(1)

    for s in servers:
        for field in ["hostname", "source_server_id", "os_type", "target_vm_id", "target_vm_name"]:
            if field not in s:
                print(json.dumps({"error": f"Server {s.get('hostname','?')} missing field: {field}"}, indent=2))
                sys.exit(1)

    disk_errors = []
    if args.fetch_disks:
        for server in servers:
            disks, err = fetch_source_disk_info(region, server["source_server_id"])
            if err:
                disk_errors.append({"hostname": server["hostname"], "error": err})
            else:
                server["_disk_info"] = disks

    task_cmds = [generate_task_command(s, data, mmdd, region) for s in servers]

    summary = {
        "date": mmdd,
        "task_count": len(task_cmds),
        "tasks": [],
        "disk_fetch_errors": disk_errors,
    }

    for tc in task_cmds:
        summary["tasks"].append({
            "task_name": tc["task_name"],
            "hostname": tc["hostname"],
            "source_server_id": tc["source_server_id"],
            "target_vm_id": tc["target_vm_id"],
            "target_vm_name": tc["target_vm_name"],
            "os_type": tc["os_type"],
            "command": tc["command"],
            "start_command": f"hcloud SMS UpdateTaskStatus --cli-region={region} --task_id=<TASK_ID> --operation=start",
        })

    print(json.dumps(summary, indent=2))
    sys.exit(0 if not disk_errors else 1)


if __name__ == "__main__":
    main()
