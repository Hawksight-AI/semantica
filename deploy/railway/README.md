# Railway

Deploys the Knowledge Explorer from the root `Dockerfile` and checks `/api/health`.

```bash
railway login
railway init
railway add --database redis
railway variable --set "FALKORDB_HOST=${{Redis.REDISHOST}}"
railway variable --set "FALKORDB_PORT=${{Redis.REDISPORT}}"
railway variable --set "ALLOWED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}"
railway variable --set "SEMANTICA_API_KEY=$(openssl rand -hex 32)"
railway up
```

The Redis plugin variables are wired to the requested FalkorDB env names for deployment compatibility. The Explorer currently reads these settings but does not persist graph state to FalkorDB.

Railway exposes this service on a public domain, so `SEMANTICA_API_KEY` is required — without it the Explorer refuses every protected route (503) rather than serving anonymously. Pass the same value as the `X-API-Key` header from any client that talks to the deployed API.
