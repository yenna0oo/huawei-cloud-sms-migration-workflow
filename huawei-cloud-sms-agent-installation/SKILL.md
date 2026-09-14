---
name: huawei-cloud-sms-agent-installation
description: Install, start, and verify the Huawei Cloud SMS (Server Migration Service) Agent on source hosts (Linux and Windows) for server migration. Covers the full agent lifecycle: pre-installation checks, download from OBS, installation, startup, connectivity verification, restart, and uninstall. Use when the user asks to: (1) install SMS Agent on a source server, (2) set up migration agent on a host, (3) check if SMS Agent is already installed, (4) restart or uninstall SMS Agent, (5) verify SMS Agent connectivity to Huawei Cloud, (6) prepare a source host for migration. Triggers on phrases like "install SMS agent", "安装迁移Agent", "setup migration agent", "部署SMS Agent", "check agent status", "restart SMS agent", "uninstall SMS agent".
---

# huawei-cloud-sms-agent-installation

## Overview

Install the Huawei Cloud SMS Agent on source hosts to enable server migration.
The agent collects source server information and sends it to the SMS service,
which then orchestrates the migration to a destination ECS.

Supports both Linux and Windows source hosts. All procedures are sourced from
official Huawei Cloud documentation (see references/AGENT_INSTALL_REFERENCE.md).

## Safety Rules

1. **Source VM is read-only** — DO NOT modify, delete, or add anything on the
   source VM without explicit user approval, EXCEPT for the SMS Agent itself
   (download, extract, install, start).
2. **No repeated installs** — Always check if the SMS Agent already exists before
   installing. Repeated installs waste disk space and may cause conflicts.
3. **Safe credential handling** — AK/SK must never appear in process arguments
   (visible via `ps aux`). Use temp file redirection or environment variables.
   See references/AGENT_INSTALL_REFERENCE.md section 7.
4. **Report, don't fix** — If anything goes wrong, report to the user with
   possible causes and resolutions. Do NOT auto-fix. Use the companion skill
   `huawei-cloud-sms-troubleshooting` to check for known issues first.

## Input Format

JSON file with host details:

```json
{
    "hostname": "server-01",
    "ip": "172.16.0.10",
    "os": "linux",
    "username": "root",
    "ssh_key": "/path/to/key.pem",
    "ssh_port": 22,
    "region": "ap-southeast-3",
    "sms_domain": "sms.ap-southeast-3.myhuaweicloud.com",
    "obs_path": "obs://my-bucket/SMS-Agent.tar.gz",
    "disk_info": {"disk_count": 2}
}
```

For Windows hosts, set `"os": "windows"`, `"username": "Administrator"`.

## Workflow

### Step 1: Read JSON Input

Parse the JSON file to extract host details. Validate required fields:
`hostname`, `ip`, `os`, `username`.

### Step 2: Pre-installation Checks

Run the pre-installation check script:

```bash
python3 scripts/pre_installation_check.py --input host.json
```

This validates:
- Root (Linux) / Administrator (Windows) access
- CPU usage < 80%
- Available memory > 256 MB
- Disk space (Linux root > 200 MB / Windows C: > 320 MB)
- Architecture is x86_64 / 64-bit
- Required components (Linux: rsync, ssh, grub; Windows: WMI, VSS)
- No existing SMS Agent already installed
- Network connectivity to SMS endpoint

If any check fails with severity "error", report to user and stop.
If checks fail with severity "warning" (e.g. existing agent), inform user
and ask how to proceed.

### Step 3: Check if Agent Already Exists

Before downloading or installing, check for existing agent:

- **Linux**: Check for `/root/SMS-Agent` directory and `linuxmain` process
- **Windows**: Check for `C:\SMS-Agent-Py3` or `C:\SMS-Agent-Py2` directories

If agent exists and is running, skip installation. If agent exists but is not
running, use restart procedure (section 4 of reference doc) instead of fresh
install.

### Step 4: Download Agent Package

Download the agent package from the OBS path provided by the user.

- **Linux**: `SMS-Agent.tar.gz` — download via `wget` or `curl` from OBS URL
- **Windows**: `SMS-Agent-Py3.exe` or `SMS-Agent-Py2.exe` — download or upload
  to the source server

> The user provides the OBS path. Do NOT guess or fabricate download URLs.

### Step 5: Install Agent

Follow OS-specific installation procedure from
references/AGENT_INSTALL_REFERENCE.md:

- **Linux** (section 2): Extract tarball, optionally configure proxy, run `./startup.sh`
- **Windows** (section 3): Run the .exe installer, enter AK/SK/SMS domain

### Step 6: Start Agent with Safe Credentials

Use the safe credential passing method (reference section 7):

```bash
# Create temp file with restrictive permissions
CRED_FILE=$(mktemp /tmp/.sms_cred.XXXXXX)
chmod 600 "$CRED_FILE"
# Write interactive input sequence
cat > "$CRED_FILE" << 'EOF'
y
y
<AK>
<SK>
sms.<region>.myhuaweicloud.com
0
EOF
# Feed via stdin redirection (not visible in ps aux)
./startup.sh < "$CRED_FILE"
# Securely delete
shred -u "$CRED_FILE" 2>/dev/null || rm -f "$CRED_FILE"
```

For restart (agent config already exists), step 5 input is `y` instead of
the sms_domain string. See reference section 2.3 for details.

### Step 7: Verify Agent Connectivity

Verify the agent has started and connected to the SMS service:

1. **Process check** (reference section 6.1/6.2):
   - Linux: `ps -ef | grep linuxmain | grep -v grep`
   - Windows: `tasklist | findstr "SMS-Agent"`

2. **SMS console check** (reference section 6.3):
   ```bash
   hcloud SMS ListServers --cli-region=<region>
   # Verify: source server appears, state=waiting, connected=true
   ```

3. **Network check** (reference section 6.4):
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://sms.<region>.myhuaweicloud.com
   ```

If verification fails, report to user. Do NOT auto-fix. Use the
`huawei-cloud-sms-troubleshooting` skill to check for known issues.

## Error Handling

When any step fails:

1. **Do NOT operate anything** on the source VM.
2. **Report to user**: describe the issue, possible causes, and potential resolutions.
3. **Check known issues**: invoke the `huawei-cloud-sms-troubleshooting` skill
   to see if this issue has been encountered and resolved before.
4. **Wait for approval**: the user decides whether to proceed with the resolution.
5. **Record new issues**: after a new issue is resolved, record it in the
   troubleshooting skill's `references/KNOWN_ISSUES.md` for future reference.

## OS-Specific Quick Reference

### Linux

| Step | Command |
|------|---------|
| Extract | `cd /root && tar -zxvf SMS-Agent.tar.gz` |
| Start | `cd SMS-Agent && ./startup.sh` |
| Verify | `ps -ef \| grep linuxmain \| grep -v grep` |
| Restart | `cd /root/SMS-Agent && ./restart.sh` |
| Stop | `./shutdown.sh` |
| Uninstall | `./shutdown.sh && cd /root && rm -rf SMS-Agent` |

### Windows

| Step | Action |
|------|--------|
| Install | Double-click `SMS-Agent-Py3.exe` (or Py2 for older Windows) |
| Start | Click "启动" in agent GUI, or `agent-start.exe` for Py2 |
| Verify | `tasklist \| findstr "SMS-Agent"` |
| Restart | Py3: tray icon → Quit → relaunch; Py2: `restart.bat` |
| Uninstall | Control Panel → Programs → Uninstall, or `Uninstall.exe` |

## File Structure

```
huawei-cloud-sms-agent-installation/
├── SKILL.md                              ← This file
├── references/
│   └── AGENT_INSTALL_REFERENCE.md        ← Detailed procedures, requirements, OS lists
└── scripts/
    └── pre_installation_check.py         ← Pre-installation validation script
```

## Companion Skill

- **huawei-cloud-sms-troubleshooting**: Issue tracking and resolution for SMS
  agent installation and migration problems. Use this skill when encountering
  any error during installation.
