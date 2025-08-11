# Anki Sync Server – Developer Guide

A self-hosted implementation of Anki’s sync protocol that works with modern Anki clients (≥ 2.1.57 / sync v11), secured by AWS Cognito and fronted by nginx with automatic Let’s Encrypt certificates.

---

## 1. Quick Start

### Production (nginx + HTTPS)
```bash
# configure secrets
cp .env.example .env && nano .env     # fill in AWS + Cognito + domain

# launch
docker-compose -f docker-compose.latest.yml up -d

# verify
docker-compose -f docker-compose.latest.yml ps
curl -k https://<your-domain>/sync/hostKey   # should return JSON
```

### Local development
```bash
git clone https://github.com/jackymcgrady/ankicommunity-sync-server.git
cd ankicommunity-sync-server
cp .env.example .env   # fill in credentials
docker-compose -f docker-compose.latest.yml up -d
```

Connect every Anki client to `https://<your-domain>`.

---

## 2. Configuration (.env)

Required:

| Var | Purpose |
|-----|---------|
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY | IAM key permitted to call Cognito |
| ANKISYNCD_COGNITO_USER_POOL_ID | Cognito User Pool |
| ANKISYNCD_COGNITO_CLIENT_ID / ANKISYNCD_COGNITO_CLIENT_SECRET | Cognito App Client |
| DOMAIN_NAME | FQDN used for certificates |
| EMAIL | Address for Let’s Encrypt renewal mail |

Optional: `AWS_DEFAULT_REGION` (default `ap-southeast-1`), `SSL_MODE` (`letsencrypt` / `self-signed`), `DEV_MODE` (`true` to disable SSL enforcement).

---

## 3. Deployment & Maintenance

Essential commands:

```bash
# start / stop
docker-compose -f docker-compose.latest.yml up -d
docker-compose -f docker-compose.latest.yml down

# upgrade rebuild
docker-compose -f docker-compose.latest.yml pull
docker-compose -f docker-compose.latest.yml up -d --build

# logs
docker-compose -f docker-compose.latest.yml logs -f nginx
docker-compose -f docker-compose.latest.yml logs -f anki-sync-server
```

Handy scripts:

* `scripts/docker-deploy.sh` – push image & deploy
* `scripts/docker-dev.sh` – local build / run
* `scripts/setup-https-certs.sh` – create/renew certificates

Volumes that **must** persist:

```yaml
- ./efs:/data                        # collections & media (EFS mount)
- ./letsencrypt:/etc/letsencrypt     # certificates
- ./certbot-www:/var/www/certbot     # ACME challenge
- ./logs/nginx:/var/log/nginx        # nginx logs
```

---

## 4. Troubleshooting & Debugging

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Exception: expected auth` during discovery | Client expects HTTP 400 | already implemented – ensure you run latest image |
| `missing original_size` header | zstd responses must include it | server code handles this – pull latest image |
| `303 stream failure` in media sync | media USN mismatch | fixed by unified media manager |
| `JsonError invalid type` | field type mismatch | server converts `csum` & graves correctly in latest build |
| `SSL certificate error` | self-signed cert rejected | use Let's Encrypt or import cert into trust store |
| Media sync stuck at "checked: 250" | Client trapped requesting removed files | Reset user: `python3 scripts/reset_user_collection.py <username> --confirm --data-root ./efs` |

### Media Sync Issues

**Problem**: Media sync stuck at "checked: X" with repeated `downloadFiles` requests for non-existent files.

**Root Cause**: After relogin, client's local database may reference files that were removed from server, causing infinite retry loops.

**Solution**:
```bash
# Reset user's media sync state completely
python3 scripts/reset_user_collection.py <username> --confirm --data-root ./efs

# Restart container to ensure clean state
docker-compose -f docker-compose.latest.yml restart anki-sync-server
```

**Useful debugging commands**:

```bash
docker logs anki-sync-server-nginx --tail 20
docker exec anki-nginx-proxy tail -f /var/log/nginx/access.log
```

If things look wrong, rebuild:

```bash
docker-compose -f docker-compose.latest.yml down
docker-compose -f docker-compose.latest.yml up --build -d
```

---

## 5. References

* Client-side sync logic: `./Anki_Architect_reference/rslib/src/sync/`
* Schema docs: **anki2-schema-doc**

---

## License

GNU AGPL-v3+
