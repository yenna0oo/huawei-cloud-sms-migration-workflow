#!/usr/bin/env python3
"""
SMS Agent Pre-installation Check Script

Validates that a source host meets all requirements for SMS Agent installation.
Takes a JSON input file with host details and runs checks via SSH.

Requirements sourced from official Huawei Cloud documentation:
  https://support.huaweicloud.com/sms_faq/sms_faq_0007.html

Usage:
    python3 pre_installation_check.py --input host.json
    python3 pre_installation_check.py --input host.json --ssh-key /path/to/key.pem

Input JSON format:
{
    "hostname": "server-01",
    "ip": "172.16.0.10",
    "os": "linux",
    "username": "root",
    "ssh_key": "/path/to/key.pem",
    "ssh_port": 22,
    "region": "ap-southeast-3",
    "sms_domain": "sms.ap-southeast-3.myhuaweicloud.com"
}

Output: JSON report with check results and overall pass/fail status.
Exit code 0 if all checks pass, 1 if any fail.
"""

import argparse
import json
import subprocess
import sys

# Thresholds from official Huawei Cloud docs
CPU_USAGE_MAX = 80
MEMORY_MIN_MB = 256
LINUX_ROOT_DISK_MIN_MB = 200
WIN_DISK_LARGE_MIN_MB = 320
DISK_COUNT_MAX = 23
REQUIRED_ARCH = "x86_64"


def check_result(name, passed, detail="", severity="error"):
    return {
        "check": name,
        "passed": passed,
        "detail": detail,
        "severity": severity if not passed else "ok",
    }


def run_ssh(host_ip, username, ssh_key, port, command, timeout=30):
    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
        "-p", str(port),
    ]
    if ssh_key:
        ssh_cmd.extend(["-i", ssh_key])
    ssh_cmd.extend([f"{username}@{host_ip}", command])
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "SSH connection timed out", -1
    except Exception as e:
        return "", str(e), -1


def _ssh(host, cmd, timeout=30):
    return run_ssh(host["ip"], host["username"], host.get("ssh_key"),
                   host.get("ssh_port", 22), cmd, timeout)


# ── Linux checks ──

def check_linux_root(host):
    out, _, rc = _ssh(host, "whoami")
    passed = (rc == 0 and out == "root")
    return check_result("root_access", passed,
                        f"User: {out}" if passed else f"Not root (got: {out})")


def check_linux_cpu(host):
    out, _, _ = _ssh(host, "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'")
    try:
        usage = 100.0 - float(out)
        return check_result("cpu_usage", usage < CPU_USAGE_MAX,
                            f"CPU usage: {usage:.1f}% (max: {CPU_USAGE_MAX}%)")
    except (ValueError, TypeError):
        return check_result("cpu_usage", False, f"Parse failed: {out}")


def check_linux_memory(host):
    out, _, _ = _ssh(host, "free -m | awk '/Mem:/ {print $7}'")
    try:
        mb = int(out)
        return check_result("memory_available", mb > MEMORY_MIN_MB,
                            f"Available: {mb} MB (min: {MEMORY_MIN_MB} MB)")
    except (ValueError, TypeError):
        return check_result("memory_available", False, f"Parse failed: {out}")


def check_linux_disk(host):
    out, _, _ = _ssh(host, "df -m / | awk 'NR==2 {print $4}'")
    try:
        mb = int(out)
        return check_result("disk_space_root", mb > LINUX_ROOT_DISK_MIN_MB,
                            f"Root free: {mb} MB (min: {LINUX_ROOT_DISK_MIN_MB} MB)")
    except (ValueError, TypeError):
        return check_result("disk_space_root", False, f"Parse failed: {out}")


def check_linux_arch(host):
    out, _, _ = _ssh(host, "uname -m")
    return check_result("architecture", out == REQUIRED_ARCH,
                        f"Arch: {out}" if out == REQUIRED_ARCH else f"Arch: {out} (need: {REQUIRED_ARCH})")


def check_linux_components(host):
    results = []
    for comp, cmd in [("rsync", "which rsync"), ("ssh", "which ssh"),
                      ("grub", "which grub-install || which grub2-install")]:
        out, _, rc = _ssh(host, cmd)
        results.append(check_result(f"component_{comp}", rc == 0 and bool(out),
                                    f"{comp}: {out}" if out else f"{comp}: NOT FOUND"))
    return results


def check_linux_disk_count(host):
    out, _, _ = _ssh(host, "lsblk -d -n | wc -l")
    try:
        count = int(out)
        return check_result("disk_count", count <= DISK_COUNT_MAX,
                            f"Disks: {count} (max: {DISK_COUNT_MAX})")
    except (ValueError, TypeError):
        return check_result("disk_count", False, f"Parse failed: {out}")


def check_linux_existing_agent(host):
    out, _, _ = _ssh(host, "ps -ef | grep -E 'linuxmain|SMS-Agent' | grep -v grep")
    if out:
        return check_result("existing_agent", False, f"Agent running: {out}", "warning")
    out, _, _ = _ssh(host, "ls -d /root/SMS-Agent 2>/dev/null")
    if out:
        return check_result("existing_agent", False,
                            "Agent dir exists at /root/SMS-Agent", "warning")
    return check_result("existing_agent", True, "No existing agent")


# ── Windows checks ──

def check_windows_admin(host):
    out, _, rc = _ssh(host, 'whoami /groups | findstr "S-1-5-32-544"')
    return check_result("admin_access", rc == 0 and bool(out),
                        "Admin confirmed" if out else "Not Administrator")


def check_windows_cpu(host):
    out, _, _ = _ssh(host, "wmic cpu get loadpercentage /value")
    try:
        for line in out.splitlines():
            if "LoadPercentage" in line:
                usage = int(line.split("=")[1].strip())
                return check_result("cpu_usage", usage < CPU_USAGE_MAX,
                                    f"CPU: {usage}% (max: {CPU_USAGE_MAX}%)")
    except (ValueError, IndexError):
        pass
    return check_result("cpu_usage", False, f"Parse failed: {out}")


def check_windows_memory(host):
    out, _, _ = _ssh(host, "wmic OS get FreePhysicalMemory /value")
    try:
        for line in out.splitlines():
            if "FreePhysicalMemory" in line:
                mb = int(line.split("=")[1].strip()) // 1024
                return check_result("memory_available", mb > MEMORY_MIN_MB,
                                    f"Available: {mb} MB (min: {MEMORY_MIN_MB} MB)")
    except (ValueError, IndexError):
        pass
    return check_result("memory_available", False, f"Parse failed: {out}")


def check_windows_disk(host):
    out, _, _ = _ssh(host, 'wmic logicaldisk where "DeviceID=\'C:\'" get FreeSpace /value')
    try:
        for line in out.splitlines():
            if "FreeSpace" in line:
                mb = int(line.split("=")[1].strip()) // (1024 * 1024)
                return check_result("disk_space_c", mb > WIN_DISK_LARGE_MIN_MB,
                                    f"C: free: {mb} MB (min: {WIN_DISK_LARGE_MIN_MB} MB)")
    except (ValueError, IndexError):
        pass
    return check_result("disk_space_c", False, f"Parse failed: {out}")


def check_windows_arch(host):
    out, _, _ = _ssh(host, "wmic os get osarchitecture /value")
    return check_result("architecture", "64" in out,
                        f"Arch: {out.strip()}" if "64" in out else f"Arch: {out.strip()} (need: 64-bit)")


def check_windows_components(host):
    results = []
    for comp, cmd in [("WMI", 'sc query winmgmt | findstr RUNNING'),
                      ("VSS", 'sc query vss | findstr RUNNING')]:
        out, _, rc = _ssh(host, cmd)
        results.append(check_result(f"component_{comp}", rc == 0 and bool(out),
                                    f"{comp}: running" if out else f"{comp}: NOT running"))
    return results


def check_windows_existing_agent(host):
    for path in ["C:\\SMS-Agent-Py3", "C:\\SMS-Agent-Py2"]:
        out, _, _ = _ssh(host, f'if exist "{path}" echo EXISTS')
        if "EXISTS" in out:
            return check_result("existing_agent", False, f"Agent at {path}", "warning")
    return check_result("existing_agent", True, "No existing agent")


# ── Network connectivity check (both OS) ──

def check_network(host):
    sms_domain = host.get("sms_domain", "")
    if not sms_domain:
        return check_result("network", True, "SMS domain not provided, skipping")
    if host["os"] == "linux":
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 10 https://{sms_domain}"
    else:
        cmd = f"powershell -Command \"(Invoke-WebRequest -Uri 'https://{sms_domain}' -UseBasicParsing -TimeoutSec 10).StatusCode\""
    out, err, _ = _ssh(host, cmd, timeout=20)
    passed = out in ("200", "403", "404", "401")
    return check_result("network_connectivity", passed,
                        f"SMS endpoint: {out}" if passed else f"Cannot reach SMS: {out or err}")


# ── Orchestration ──

def run_linux_checks(host):
    results = [
        check_linux_root(host), check_linux_cpu(host), check_linux_memory(host),
        check_linux_disk(host), check_linux_arch(host),
    ]
    results.extend(check_linux_components(host))
    results.extend([
        check_linux_disk_count(host), check_linux_existing_agent(host), check_network(host)
    ])
    return results


def run_windows_checks(host):
    results = [
        check_windows_admin(host), check_windows_cpu(host), check_windows_memory(host),
        check_windows_disk(host), check_windows_arch(host),
    ]
    results.extend(check_windows_components(host))
    results.extend([check_windows_existing_agent(host), check_network(host)])
    return results


def main():
    parser = argparse.ArgumentParser(description="SMS Agent pre-installation check")
    parser.add_argument("--input", required=True, help="Path to JSON file with host details")
    parser.add_argument("--ssh-key", default=None, help="SSH private key path")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        host = json.load(f)
    if args.ssh_key:
        host["ssh_key"] = args.ssh_key

    required = ["hostname", "ip", "os", "username"]
    for field in required:
        if field not in host:
            print(json.dumps({"hostname": "unknown", "overall": "error",
                              "error": f"Missing field: {field}", "checks": []}, indent=2))
            sys.exit(1)

    os_type = host["os"].lower()
    if os_type == "linux":
        checks = run_linux_checks(host)
    elif os_type == "windows":
        checks = run_windows_checks(host)
    else:
        print(json.dumps({"hostname": host["hostname"], "overall": "error",
                           "error": f"Unsupported OS: {host['os']}", "checks": []}, indent=2))
        sys.exit(1)

    errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    warnings = [c for c in checks if not c["passed"] and c["severity"] == "warning"]
    overall = "pass" if not errors else "fail"

    report = {
        "hostname": host["hostname"],
        "ip": host["ip"],
        "os": host["os"],
        "overall": overall,
        "warnings": len(warnings),
        "checks": checks,
    }
    print(json.dumps(report, indent=2))
    sys.exit(0 if overall == "pass" else 1)


if __name__ == "__main__":
    main()
