## Docker Configuration
- Always keep only one docker compose yml, as I'm only developing one service version for now. Name it docker-compose.latest.yml

## Project Overview
- This is a project that serves as a sync server for a customized Anki
- Uses nginx for HTTPS proxy (as a container, part of the docker compose)
- Configured to authenticate users using AWS Cognito
- Recommendation: Understand the README.md first before diving into the project details

## Development Philosophy
- Never ask me to downgrade the client to meet traditional server, as I'm taking this server online to meet modern anki users.

## Compatibility
- When client version is higher than what is compatible with the server, remember to always try to update the server (refer to @Anki_Client_Code/ for latest client expectations)

## User Management
- huyuping is user 1, when I tell you to reset huyuping, you run:
  ```bash
  echo "yes" | python3 scripts/reset_user_collection.py huyuping --confirm --data-root /home/ec2-user/ankicommunity-sync-server/data
  ```
  This sets huyuping's collection and media data to completely empty, ready for a fresh first sync.