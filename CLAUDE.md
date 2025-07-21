## Docker Configuration
- Always keep only one docker compose yml, as I'm only developing one service version for now. Name it docker-compose.latest.yml

## Project Overview
- This is a project that serves as a sync server for a customized Anki
- Uses nginx for HTTPS proxy (as a container, part of the docker compose)
- Configured to authenticate users using AWS Cognito
- Recommendation: Understand the README.md first before diving into the project details