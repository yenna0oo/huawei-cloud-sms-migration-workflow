# SMS Agent Installation — Detailed Reference

> All content sourced from official Huawei Cloud SMS documentation.
> - Linux install: https://support.huaweicloud.com/qs-sms/sms3_02_0006.html
> - Windows install: https://support.huaweicloud.com/qs-sms/sms3_02_0005.html
> - System requirements: https://support.huaweicloud.com/sms_faq/sms_faq_0007.html
> - Restart: https://support.huaweicloud.com/intl/en-us/sms_faq/topic_0000001124046925.html
> - Uninstall: https://support.huaweicloud.com/intl/en-us/sms_faq/sms_faq_0035.html

---

## Table of Contents

1. [Pre-installation Requirements](#1-pre-installation-requirements)
2. [Linux Agent Installation](#2-linux-agent-installation)
3. [Windows Agent Installation](#3-windows-agent-installation)
4. [Agent Restart](#4-agent-restart)
5. [Agent Uninstall](#5-agent-uninstall)
6. [Agent Verification](#6-agent-verification)
7. [Safe Credential Passing](#7-safe-credential-passing)
8. [Detecting Existing Agent](#8-detecting-existing-agent)
9. [Supported OS List](#9-supported-os-list)

---

## 1. Pre-installation Requirements

### 1.1 Server Specifications

| Requirement | Threshold | Source |
|-------------|-----------|--------|
| CPU usage | < 80% | Official FAQ sms_faq_0007 |
| Available memory | > 256 MB | Official FAQ sms_faq_0007 |
| Architecture | x86_64 only | Official FAQ sms_faq_0007 |
| Disk count | <= 23 disks | Official FAQ sms_faq_0007 (ECS max 24 + 1 agent disk) |
| Linux disk size | <= 16 TB per disk | Official FAQ sms_faq_0007 |

### 1.2 Disk Space Requirements

| OS | Condition | Minimum Free Space |
|----|-----------|-------------------|
| Linux | Root partition | > 200 MB available |
| Windows | Partition >= 600 MB | > 320 MB available |
| Windows | Partition < 600 MB | > 40 MB available |

### 1.3 Required Components

| OS | Required Components |
|----|---------------------|
| Linux | SSH (e.g. OpenSSH), rsync, grub |
| Windows | WMI, VSS |

### 1.4 Other Constraints

- **No antivirus software** on Windows source (may cause Agent startup failure)
- **Character set**: Linux must use UTF-8; Windows supports cp437 and cp936
- **SSH key algorithms** (Linux): ssh-rsa, rsa-sha2-256, rsa-sha2-512
- **No BitLocker encryption** on Windows
- **No RAID**, no LVM nested systems, no LVM thin volumes
- **Login user**: Linux requires root; Windows requires Administrator

### 1.5 Pre-check Commands

#### Linux

```bash
# Root access
whoami  # must be root

# CPU usage
top -bn1 | grep "Cpu(s)" | awk '{print $2}'  # idle %; usage = 100 - idle; must be < 80

# Available memory
free -m | awk '/Mem:/ {print $7}'  # available MB; must be > 256

# Root partition free space
df -m / | awk 'NR==2 {print $4}'  # available MB; must be > 200

# Architecture
uname -m  # must be x86_64

# Required components
which rsync && rsync --version | head -1
which ssh
which grub-install || which grub2-install  # either one

# Disk count
lsblk -d | wc -l  # subtract 1 for header; must be <= 23

# No existing SMS agent
ps -ef | grep -E "linuxmain|SMS-Agent" | grep -v grep  # should be empty
ls -d /root/SMS-Agent 2>/dev/null  # should not exist
```

#### Windows (run via SSH or WinRM)

```powershell
# Administrator access
whoami /groups | findstr "S-1-5-32-544"  # must find Administrators group

# CPU usage
wmic cpu get loadpercentage /value  # must be < 80

# Available memory
wmic OS get FreePhysicalMemory /value  # in KB; must be > 256*1024

# Disk free space (system drive)
wmic logicaldisk where "DeviceID='C:'" get FreeSpace /value  # in bytes

# Architecture
wmic os get osarchitecture /value  # must be "64-bit"

# Required components - WMI
sc query winmgmt | findstr RUNNING
# Required components - VSS
sc query vss | findstr RUNNING

# No existing SMS agent
sc query | findstr "SMS-Agent"  # should be empty
dir "C:\SMS-Agent-Py2" 2>nul  # should not exist
dir "C:\SMS-Agent-Py3" 2>nul  # should not exist
```

---

## 2. Linux Agent Installation

### 2.1 Prerequisites

- Root user login on the source Linux server
- OS type must be in the Linux compatibility list (see section 9)
- AK/SK for the destination Huawei Cloud account
- SMS domain name (obtainable from SMS console -> "迁移Agent" page)
- Agent package downloaded (from OBS path or SMS console)

### 2.2 Installation Steps

```bash
# 1. Extract the agent package
cd /root && tar -zxvf SMS-Agent.tar.gz

# 2. Enter the agent directory
cd SMS-Agent

# 3. (Optional) Configure proxy -- ONLY for VPN/direct connect scenarios
#    If NOT using proxy, DO NOT modify auth.cfg
cd agent/config
vi auth.cfg
# Set:
#   [proxy-config]
#   enable = true
#   proxy_addr = https://your-proxy-addr.com
#   proxy_port = 3128
#   proxy_user = root
#   use_password = true
cd ../..

# 4. Start the agent
./startup.sh
```

### 2.3 Interactive Input Sequence

**First-time installation** (config directory empty):

```
y              <- acknowledge fstab pre-check warning
y              <- agree to data collection declaration
<AK>           <- Huawei Cloud Access Key ID
<SK>           <- Huawei Cloud Secret Access Key
<sms_domain>   <- e.g. sms.ap-southeast-3.myhuaweicloud.com
0              <- enterprise project (0 = default)
```

**Restart** (config directory already has configuration):

```
y              <- acknowledge fstab pre-check warning
y              <- agree to data collection declaration
<AK>           <- Huawei Cloud Access Key ID
<SK>           <- Huawei Cloud Secret Access Key
y              <- reuse previous sms_domain (Y/N confirmation, NOT re-enter)
0              <- enterprise project
```

> WARNING: First-time install step 5 requires the sms_domain string.
> Restart step 5 requires `y` to confirm reuse.
> Passing the wrong type causes an infinite input loop.

### 2.4 Success Indicator

When the agent starts successfully, the terminal displays a success message
indicating the agent has started and is uploading source server information
to the SMS service. Check the SMS console to confirm the source server appears.

### 2.5 Known Installation Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| SMS.6517 | rsync not installed on source | Install rsync, retry |
| SMS.0202 | AK/SK authentication failed | Verify AK/SK correctness |
| Agent not visible in console | Registration failed | Check network to SMS endpoint |

---

## 3. Windows Agent Installation

### 3.1 Agent Version Selection

| Windows Version | Agent Version | Interface |
|----------------|---------------|-----------|
| Server 2012/2016/2019/2022/2025, Win 8.1/10/11 | SMS-Agent-Py3.exe | GUI (Python 3) |
| Server 2008, Win 7 | SMS-Agent-Py2.exe | CLI (Python 2) |

> Python 2 agent can also run on later Windows versions.

### 3.2 Prerequisites

- Administrator user login on the source Windows server
- OS type must be in the Windows compatibility list (see section 9)
- AK/SK for the destination Huawei Cloud account
- SMS domain name (obtainable from SMS console)
- No antivirus software installed
- Agent installer (.exe) uploaded to the source server

### 3.3 Installation -- Windows Agent Python 3 (GUI)

1. Upload `SMS-Agent-Py3.exe` to the source server
2. Login as Administrator, double-click `SMS-Agent-Py3.exe`
3. Click "安装" (Install), wait for completion
4. Click "完成" (Finish) -- agent GUI appears
5. Enter AK, SK, and SMS domain
6. Select connection method:
   - "直连" (Direct) -- no proxy
   - "使用代理" (Use proxy) -- enter proxy IP, port, username, password
7. If enterprise project is enabled, select the target project
8. Click "启动" (Start)
9. Read the warning popup, click "是" (Yes)
10. Success: "启动成功！等待服务端命令..." appears

### 3.4 Installation -- Windows Agent Python 2 (CLI)

1. Upload `SMS-Agent-Py2.exe` to the source server
2. Login as Administrator, double-click `SMS-Agent-Py2.exe`
3. Click "安装" (Install), wait for completion
4. Click "完成" (Finish) -- command-line interface appears
5. (Optional) Configure proxy in `C:\SMS-Agent-Py2\config\auth.cfg`
6. Follow prompts to enter AK, SK, and SMS domain
7. If enterprise project is enabled, select the target project
8. Authentication passes -> agent starts and uploads server info
9. For subsequent starts: go to `C:\SMS-Agent-Py2`, double-click `agent-start.exe`

### 3.5 Proxy Configuration (auth.cfg)

Only for VPN/direct connect scenarios. **Do NOT modify auth.cfg if not using proxy.**

```ini
[proxy-config]
enable = true
proxy_addr = https://your-proxy-addr.com
proxy_port = 3128
proxy_user = root
use_password = true
```

| Parameter | Description |
|-----------|-------------|
| enable | Set to true when using proxy |
| proxy_addr | Proxy server address (NOT destination server) |
| proxy_port | Proxy server port |
| proxy_user | Proxy username (leave empty if none) |
| use_password | true if proxy has password, false otherwise |

> Proxy is only used for agent registration, not for data migration.

---

## 4. Agent Restart

### 4.1 Linux

```bash
cd /root/SMS-Agent
./restart.sh
# Enter AK/SK and SMS domain when prompted
```

### 4.2 Windows Agent Python 3

1. Right-click SMS-Agent icon in system tray -> Quit
2. Open `C:\SMS-Agent-Py3` folder
3. Double-click `SMS-Agent.exe`
4. Enter required information, click Start

### 4.3 Windows Agent Python 2

1. Open `C:\SMS-Agent-Py2` folder
2. Double-click `restart.bat`
3. Enter AK/SK and SMS domain in the CMD window

---

## 5. Agent Uninstall

> Only uninstall after migration is complete and with user approval.

### 5.1 Linux

```bash
cd /root/SMS-Agent
./shutdown.sh
cd /root
rm -rf SMS-Agent
```

### 5.2 Windows -- Method 1: Control Panel

1. Login to the server
2. Start menu -> Control Panel -> Programs -> Uninstall a program
3. Find `SMS-Agent-Py2` or `SMS-Agent-Py3`
4. Double-click to uninstall, click Yes to confirm

### 5.3 Windows -- Method 2: Installation Directory

1. Login to the server
2. Navigate to `C:\SMS-Agent-Py2` or `C:\SMS-Agent-Py3`
3. Double-click `Uninstall.exe`
4. Click Yes to confirm

---

## 6. Agent Verification

### 6.1 Linux -- Process Check

```bash
ps -ef | grep linuxmain | grep -v grep
# A running process indicates the agent is active
```

### 6.2 Windows -- Process Check

```powershell
# Python 3 agent
tasklist | findstr "SMS-Agent"
# Python 2 agent
tasklist | findstr "agent-start"
```

### 6.3 SMS Console -- Connectivity Check

Use hcloud CLI to verify the agent has registered and connected:

```bash
hcloud SMS ListServers --cli-region=<region>
# Look for the source server in the list
# Verify: state=waiting, connected=true
```

### 6.4 Network Connectivity Test

```bash
# Linux
curl -s -o /dev/null -w "%{http_code}" https://sms.<region>.myhuaweicloud.com
# Expected: 200 or 403 (reachable, auth required)

# Windows
Invoke-WebRequest -Uri "https://sms.<region>.myhuaweicloud.com" -UseBasicParsing
```

---

## 7. Safe Credential Passing

### 7.1 Problem with printf Pipes

The non-interactive method `printf 'y\ny\nAK\nSK\n...' | ./startup.sh` exposes
AK/SK in the process argument list, visible via `ps aux`. This is a security risk.

### 7.2 Safe Method -- Temp File with File Redirection

Use a temporary file with restrictive permissions, fed via stdin redirection
(never appears in process args), then securely deleted:

```bash
# 1. Create a temp file with credentials (restrictive permissions)
CRED_FILE=$(mktemp /tmp/.sms_cred.XXXXXX)
chmod 600 "$CRED_FILE"
cat > "$CRED_FILE" << 'CRED_EOF'
y
y
AK_VALUE
SK_VALUE
sms.ap-southeast-3.myhuaweicloud.com
0
CRED_EOF

# 2. Feed to startup.sh via stdin redirection, then delete immediately
./startup.sh < "$CRED_FILE"
EXIT_CODE=$?
shred -u "$CRED_FILE" 2>/dev/null || rm -f "$CRED_FILE"

# 3. Check exit code
if [ $EXIT_CODE -ne 0 ]; then
    echo "Agent startup may have failed (exit code: $EXIT_CODE)"
fi
```

### 7.3 Safe Method -- Environment Variables via SSH

For SSH-based remote installation, pass credentials via environment variables
that are forwarded through SSH, not as CLI arguments:

```bash
# On the control machine:
export SMS_AK="your-ak"
export SMS_SK="your-sk"
export SMS_DOMAIN="sms.ap-southeast-3.myhuaweicloud.com"

# SSH into source VM -- credentials passed via env, not process args
ssh -i key.pem root@<source_ip> \
  "SMS_AK='$SMS_AK' SMS_SK='$SMS_SK' SMS_DOMAIN='$SMS_DOMAIN' bash -s" << 'REMOTE'
  cd /root/SMS-Agent
  CRED_FILE=$(mktemp /tmp/.sms_cred.XXXXXX)
  chmod 600 "$CRED_FILE"
  printf 'y\ny\n%s\n%s\n%s\n0\n' "$SMS_AK" "$SMS_SK" "$SMS_DOMAIN" > "$CRED_FILE"
  ./startup.sh < "$CRED_FILE"
  shred -u "$CRED_FILE" 2>/dev/null || rm -f "$CRED_FILE"
REMOTE
```

> **Key principle**: Credentials must never appear in `ps aux` output.
> Use file redirection (`< file`), environment variables, or expect scripts.
> Always clean up temp files with `shred -u` after use.

---

## 8. Detecting Existing Agent

Before installing, always check if an agent is already present to avoid
repeated installations that waste disk space.

### 8.1 Linux

```bash
# Check for running agent process
AGENT_PROC=$(ps -ef | grep -E "linuxmain|SMS-Agent" | grep -v grep)
if [ -n "$AGENT_PROC" ]; then
    echo "SMS Agent is already running -- skip installation"
fi

# Check for agent directory
if [ -d "/root/SMS-Agent" ]; then
    echo "SMS Agent directory exists at /root/SMS-Agent"
    # May need restart instead of fresh install
fi

# Check for agent config (indicates prior installation)
if [ -d "/root/SMS-Agent/agent/config" ] && [ -f "/root/SMS-Agent/agent/config/agent.xml" ]; then
    echo "Agent has existing configuration -- use restart.sh, not startup.sh"
fi
```

### 8.2 Windows

```powershell
# Check for running agent process
$agentProc = Get-Process -Name "SMS-Agent","agent-start" -ErrorAction SilentlyContinue
if ($agentProc) { Write-Output "SMS Agent is already running" }

# Check for installation directories
if (Test-Path "C:\SMS-Agent-Py3") { Write-Output "Python3 agent installed" }
if (Test-Path "C:\SMS-Agent-Py2") { Write-Output "Python2 agent installed" }

# Check via service list
$svc = Get-Service -Name "*SMS*" -ErrorAction SilentlyContinue
if ($svc) { Write-Output "SMS service found: $($svc.Name)" }
```

---

## 9. Supported OS List

### 9.1 Windows Compatibility

| OS Version | Bits | UEFI | Agent Version |
|------------|------|------|---------------|
| Windows Server 2008 / 2008 R2 | 64 | No | Python 2 (CLI) |
| Windows 7 | 64 | No | Python 2 (CLI) |
| Windows 8.1 | 64 | No | Python 3 (GUI) |
| Windows 10 | 64 | Yes | Python 3 (GUI) |
| Windows 11 | 64 | Yes (UEFI only) | Python 3 (GUI) |
| Windows Server 2012 / 2012 R2 | 64 | Yes | Python 3 (GUI) |
| Windows Server 2016 | 64 | Yes | Python 3 (GUI) |
| Windows Server 2019 | 64 | Yes | Python 3 (GUI) |
| Windows Server 2022 | 64 | Yes | Python 3 (GUI) |
| Windows Server 2025 | 64 | Yes | Python 3 (GUI) |

### 9.2 Linux Compatibility (File-level Migration)

| OS Family | Supported Versions |
|-----------|-------------------|
| Red Hat | RHEL 6.0-6.10, 7.0-7.9, 8.0-8.10, 9.0-9.7 |
| CentOS | CentOS 6.0-6.10, 7.0-7.9, 8.0-8.5, Stream 8, Stream 9 |
| Oracle Linux | 6.0-6.10, 7.0-7.9, 8.0-8.10, 9.0-9.3 |
| SUSE | SLES 11 SP3/SP4, 12 SP0-SP5, 15 SP0-SP6 |
| Ubuntu | 12.04-24.04 |
| Debian | 6.0-12.13 |
| Fedora | 23-39 |
| EulerOS | 2.0.0, 2.2.0, 2.3.0, 2.5.0 |
| Amazon Linux | 2.0, 2018.3, 2023 AMI |
| Alibaba Cloud Linux | 2.1903, 3.2104 |
| AlmaLinux | 8.3-8.10, 9.0-9.4 |
| OpenEuler | 20.03, 21.09, 22.03 |
| Rocky Linux | 8.3-8.10, 9.0-9.6 |

> Full detailed version list with UEFI support flags available at:
> https://support.huaweicloud.com/sms_faq/sms_faq_0007.html
