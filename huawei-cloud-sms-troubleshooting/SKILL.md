---
name: huawei-cloud-sms-troubleshooting
description: Troubleshoot and resolve issues encountered during Huawei Cloud SMS (Server Migration Service) agent installation and migration. Maintains a knowledge base of known issues and their proven resolutions. Use when encountering errors during SMS agent installation, startup, connectivity verification, or migration tasks. Triggers on phrases like "SMS agent error", "迁移Agent报错", "SMS installation failed", "agent connectivity issue", "SMS error code", "troubleshoot SMS", "SMS问题排查".
---

# huawei-cloud-sms-troubleshooting

## Overview

Issue tracking and resolution for Huawei Cloud SMS agent installation and
migration problems. This skill maintains a knowledge base of known issues
and their proven resolutions, accumulating new solutions as they are discovered.

## Workflow

### Step 1: Check Known Issues

Read `references/KNOWN_ISSUES.md` to search for the encountered issue.

Match by:
- Error code (e.g. SMS.6517, SMS.0202, SMS.0515)
- Symptom description
- OS type (Linux/Windows)
- Step where the error occurred (pre-check, install, start, verify)

### Step 2: Report to User

If a known issue is found:
- Report the issue and its proven resolution to the user
- Wait for user approval before executing the resolution
- Do NOT auto-fix — the user must explicitly confirm

If no known issue is found:
- Report the unknown issue to the user with possible causes
- Suggest potential resolutions based on available information
- Wait for user to decide how to proceed

### Step 3: Execute Resolution (with approval)

Only after the user explicitly approves:
- Execute the resolution steps
- Verify the issue is resolved
- If resolved, proceed to Step 4 to record the issue
- If not resolved, report back to user and try alternative approaches

### Step 4: Record New Issues

If a new issue was encountered and successfully resolved:
- Add the issue to `references/KNOWN_ISSUES.md` with:
  - Error code or symptom
  - OS type
  - Step where it occurred
  - Root cause
  - Resolution steps
  - Date resolved

## Known Error Codes (from official docs)

| Error Code | Description | Quick Fix |
|------------|-------------|-----------|
| SMS.6517 | rsync not installed on source | Install rsync: `yum install rsync` or `apt install rsync` |
| SMS.0202 | AK/SK authentication failed | Verify AK/SK correctness and permissions |
| SMS.1902 | IO monitor startup failed | Check disk IO permissions, antivirus software |
| SMS.0515 | Disk info incomplete | Re-collect disk info via ShowServer API |
| SMS.0007 | Template missing required fields | Rebuild template with all required params |

> Full error catalog will accumulate in references/KNOWN_ISSUES.md as issues
> are encountered and resolved in practice.

## File Structure

```
huawei-cloud-sms-troubleshooting/
├── SKILL.md
└── references/
    └── KNOWN_ISSUES.md    ← Accumulated known issues and resolutions
```

## Relationship to Other Skills

- **huawei-cloud-sms-agent-installation**: This skill is invoked when the
  agent installation skill encounters an error. The installation skill reports
  the issue, this skill checks for known resolutions.
- **sms-migration-assistant**: This skill can also be used for migration task
  errors beyond just agent installation.
