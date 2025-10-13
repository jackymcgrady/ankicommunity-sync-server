# EFS Permissions Setup for AnkiPi

## Overview
This document explains how EFS permissions are configured to allow write access across all AnkiPi services.

## Problem
Multiple services need to read/write files on the shared EFS mount:
- **Community Sync Server** (ankisyncd) - runs as `ankiworker:nogroup` in Docker
- **Web Application** (Next.js) - runs as `ec2-user`
- **Main AnkiPi Service** - runs as `ec2-user`
- **Waiter Scripts** - run as `ec2-user`
- **Purge Scripts** - run as `ec2-user`

## Solution

### 1. Shared Group: `nogroup` (GID 65533)
Both users are members of the `nogroup` group:
- `ec2-user` (UID 1000): `groups=1000(ec2-user),4(adm),10(wheel),...,65533(nogroup)`
- `ankiworker` (UID 1001): `groups=65533(nogroup)`

### 2. SetGID Bit on EFS Directories
The setgid bit ensures all new files/directories inherit the `nogroup` group:

```bash
sudo chmod g+s /home/ec2-user/ankicommunity-sync-server/efs
sudo chmod g+s /home/ec2-user/ankicommunity-sync-server/efs/collections
```

Result:
```
drwxrwsr-x  ankiworker nogroup  /efs
drwxrwsr-x  ankiworker nogroup  /efs/collections
         ^-- setgid bit
```

### 3. Umask Configuration
Each service sets `umask 0002` to create group-writable files (permissions `664` for files, `775` for directories).

#### Docker Container (ankisyncd)
File: `/home/ec2-user/ankicommunity-sync-server/docker-compose.latest.yml`
```yaml
services:
  anki-sync-server:
    command: >
      sh -c "
        umask 0002 &&
        mkdir -p /data/collections &&
        ...
        exec python -m ankisyncd
      "
```

#### Waiter Script
File: `/home/ec2-user/ankipi/src/run_waiter.py`
```python
def main():
    # Set umask to 0002 so new files are group-writable
    os.umask(0o002)
    ...
```

#### Purge Script
The purge script should be run with sudo when deleting files owned by other users:
```bash
sudo python3 purge_user.py --username maxwell4
# OR use the wrapper script:
/home/ec2-user/ankipi/set_umask_and_run.sh python3 purge_user.py --username maxwell4
```

### 4. Wrapper Script for Manual Operations
File: `/home/ec2-user/ankipi/set_umask_and_run.sh`
```bash
#!/bin/bash
umask 0002
exec "$@"
```

Usage:
```bash
./set_umask_and_run.sh python3 my_script.py
./set_umask_and_run.sh /home/ec2-user/ankipi/src/run_waiter.py
```

## Verification

### Check Directory Permissions
```bash
ls -ld /home/ec2-user/ankicommunity-sync-server/efs/collections
# Should show: drwxrwsr-x ankiworker nogroup
#                      ^-- setgid bit
```

### Check Group Membership
```bash
groups ec2-user  # Should include 'nogroup'
id ankiworker    # Should show gid=65533(nogroup)
```

### Test File Creation
```bash
# As ec2-user
cd /home/ec2-user/ankicommunity-sync-server/efs/collections
touch test.txt
ls -la test.txt
# Should show: -rw-rw-r-- ec2-user nogroup test.txt (if umask is set)
# Or:          -rw-r--r-- ec2-user nogroup test.txt (if umask not set)
```

### Check Docker Container
```bash
docker exec anki-sync-server-nginx id
# Should show: uid=1001 gid=65533(nogroup) groups=65533(nogroup)
```

## How It Works

1. **SetGID Bit**: When a file is created in `/efs/collections`, it automatically gets group=`nogroup`
2. **Umask 0002**: New files get permissions `664` (rw-rw-r--), new directories get `775` (rwxrwxr-x)
3. **Shared Group**: Both `ec2-user` and `ankiworker` can read/write files because they're in `nogroup`

## File Permission Flow

```
User creates file → SetGID → Group = nogroup → Umask 0002 → Permissions = 664
                                                                            ↓
                                                              Both users can read/write!
```

## Restart Services

After making changes, restart services to apply umask:

```bash
# Restart Docker containers
cd /home/ec2-user/ankicommunity-sync-server
docker-compose -f docker-compose.latest.yml restart anki-sync-server

# Restart systemd services (if needed)
sudo systemctl restart ankipiweb
```

## Troubleshooting

### Permission Denied on Existing Files
If you get "Permission denied" on existing files, they may have been created before the umask was set:
```bash
# Option 1: Fix specific directory (fast)
sudo chmod -R g+w /home/ec2-user/ankicommunity-sync-server/efs/collections/USER_UUID

# Option 2: Use sudo to delete (for purge operations)
sudo rm -rf /home/ec2-user/ankicommunity-sync-server/efs/collections/USER_UUID
```

### ACLs Not Supported
AWS EFS (NFS) does not support POSIX ACLs. Use the group permissions approach instead.

### Files Still Created with Wrong Permissions
Check that:
1. The service has `umask 0002` set before creating files
2. The service was restarted after configuration changes
3. The directory has the setgid bit (`chmod g+s`)

## Summary

✅ **SetGID** on directories → files inherit `nogroup` group
✅ **Umask 0002** in all services → files are group-writable
✅ **Both users in `nogroup`** → both can read/write
✅ **No recursive chmod needed** → works automatically for new files
