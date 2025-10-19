# SSL Certificate Auto-Renewal Setup

## Overview
Automatic SSL certificate renewal has been configured for your AnkiPi sync server to prevent certificate expiration issues.

## What Was Set Up

### 1. Renewal Script
**Location**: `/home/ec2-user/ankicommunity-sync-server/scripts/renew-certs.sh`

This script:
- Runs certbot to renew Let's Encrypt certificates
- Reloads nginx to apply new certificates
- Logs all activity to `/home/ec2-user/ankicommunity-sync-server/logs/certbot/renewal.log`

### 2. Systemd Service
**Service**: `certbot-renewal.service`
- Executes the renewal script
- Runs as ec2-user
- Logs output to renewal.log and renewal-error.log

### 3. Systemd Timer
**Timer**: `certbot-renewal.timer`
- Runs daily at 3:00 AM (with random delay of 0-60 minutes)
- Automatically enabled and started
- Persistent (runs on boot if missed)

## Current Status

All certificates are valid until: **January 17, 2026**

Next automatic renewal check: **Daily at ~3:00 AM**

## Useful Commands

### Check timer status
```bash
sudo systemctl status certbot-renewal.timer
```

### View next scheduled run
```bash
sudo systemctl list-timers --all | grep certbot
```

### Manually trigger renewal (for testing)
```bash
sudo systemctl start certbot-renewal.service
```

### View renewal logs
```bash
tail -f /home/ec2-user/ankicommunity-sync-server/logs/certbot/renewal.log
```

### View error logs
```bash
tail -f /home/ec2-user/ankicommunity-sync-server/logs/certbot/renewal-error.log
```

### Stop/disable automatic renewal
```bash
sudo systemctl stop certbot-renewal.timer
sudo systemctl disable certbot-renewal.timer
```

### Re-enable automatic renewal
```bash
sudo systemctl enable certbot-renewal.timer
sudo systemctl start certbot-renewal.timer
```

## How It Works

1. **Daily Check**: The timer runs certbot daily to check if certificates need renewal
2. **Auto-Renewal**: Let's Encrypt certificates are automatically renewed 30 days before expiration
3. **Nginx Reload**: After successful renewal, nginx is reloaded to apply new certificates
4. **Logging**: All activity is logged for troubleshooting

## Troubleshooting

### If renewal fails:
1. Check error logs: `tail /home/ec2-user/ankicommunity-sync-server/logs/certbot/renewal-error.log`
2. Check certbot logs: `tail /home/ec2-user/ankicommunity-sync-server/logs/certbot/letsencrypt.log`
3. Verify nginx is running: `docker ps | grep nginx`
4. Test renewal manually: `sudo systemctl start certbot-renewal.service`

### Manual renewal (if needed):
```bash
cd /home/ec2-user/ankicommunity-sync-server
./scripts/renew-certs.sh
```

## Certificate Locations

- **Certificates**: `/home/ec2-user/ankicommunity-sync-server/letsencrypt/live/`
- **Archive**: `/home/ec2-user/ankicommunity-sync-server/letsencrypt/archive/`
- **Renewal configs**: `/home/ec2-user/ankicommunity-sync-server/letsencrypt/renewal/`

## Important Notes

- Certbot uses webroot authentication (requires nginx to be running)
- Certificates are renewed automatically 30 days before expiration
- No manual intervention required under normal circumstances
- The system will continue to work even if you reboot the server
