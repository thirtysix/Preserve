# Deploying the Preserve API gateway

The gateway (`preserve.api`) is an OpenAI-compatible proxy that scrubs PII before
forwarding to an upstream LLM and restores it in the response. This guide covers a
production deployment: Docker Compose, TLS, shared rate limiting, and a non-Docker
systemd option.

> **Security model.** In gateway mode, user prompts (with PII) reach *your* server but
> never the third-party LLM. Keep these true: the upstream key lives only on the server
> (`PRESERVE_UPSTREAM_API_KEY`), clients authenticate with their own gateway keys, traffic
> is HTTPS-only, and per-key quotas are set. Audit logs (`logs/api_audit.jsonl`) record
> counts, never PII values.

## 1. Configuration

All config is environment-driven (see [`preserve/api/settings.py`](../preserve/api/settings.py)).
Create a `.env`:

```bash
PRESERVE_UPSTREAM_API_KEY=sk-your-org-upstream-key      # never exposed to clients
PRESERVE_UPSTREAM_BASE_URL=https://api.deepinfra.com/v1/openai
PRESERVE_DEFAULT_MODEL=meta-llama/Llama-3.3-70B-Instruct
PRESERVE_SENSITIVITY=standard
# Gateway keys: who may call the proxy, and their limits
PRESERVE_API_KEYS={"sk-team-alpha":{"name":"alpha","rpm":60,"daily_token_quota":2000000}}
```

Generate gateway keys with anything unguessable, e.g. `python -c "import secrets;print('sk-'+secrets.token_urlsafe(32))"`.

## 2. Docker Compose (recommended)

```bash
docker compose up --build -d        # starts api (127.0.0.1:8800) + redis
curl http://127.0.0.1:8800/health
```

Compose binds the API to `127.0.0.1` on purpose: a reverse proxy terminates TLS and is
the only thing exposed publicly. Redis provides rate-limit state shared across workers
(the app auto-detects `REDIS_URL`; without it, it falls back to in-memory limiting).

Scale workers: `uvicorn ... --workers 4` (Redis keeps quotas consistent across them).

## 3. TLS reverse proxy

### Caddy (automatic HTTPS)

```caddy
# /etc/caddy/Caddyfile
preserve.example.org {
    reverse_proxy 127.0.0.1:8800
}
```

`caddy reload`; Caddy obtains and renews a Let's Encrypt cert automatically.

### nginx + certbot

```nginx
server {
    server_name preserve.example.org;
    location / {
        proxy_pass http://127.0.0.1:8800;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;   # LLM calls can be slow
    }
}
```

```bash
sudo certbot --nginx -d preserve.example.org
```

## 4. Non-Docker (systemd)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[api,redis]"
```

```ini
# /etc/systemd/system/preserve-api.service
[Unit]
Description=Preserve API gateway
After=network.target

[Service]
WorkingDirectory=/opt/preserve
EnvironmentFile=/opt/preserve/.env
ExecStart=/opt/preserve/.venv/bin/uvicorn preserve.api.app:app --host 127.0.0.1 --port 8800 --workers 4
Restart=always
User=preserve

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now preserve-api
```

## 5. Deploying alongside other sites (e.g. a shared Hetzner VM)

If the box already runs other sites behind one nginx + certbot:

1. **DNS**: point `preserve.example.org` at the VM (A/AAAA at your registrar).
2. **Backend**: run the gateway on `127.0.0.1:8800` (Compose or systemd above).
3. **vhost**: add the nginx server block from §3, then `sudo nginx -t && sudo systemctl reload nginx`.
4. **Cert**: `sudo certbot --nginx -d preserve.example.org`.
5. **Verify**: `curl https://preserve.example.org/health`, then a real `/v1/chat/completions` call.

This adds a site without touching the existing ones. Roll back by removing the vhost and reloading nginx.

## 6. Pre-launch checklist

- [ ] HTTPS only; API bound to localhost behind the proxy.
- [ ] `PRESERVE_UPSTREAM_API_KEY` set server-side; never returned to clients.
- [ ] Per-key `rpm` and `daily_token_quota` set for every gateway key.
- [ ] `REDIS_URL` set if running more than one worker/host.
- [ ] `log_scrubbed_content` stays off (default) so audit logs hold no PII.
- [ ] `PRESERVE_ALLOW_NO_AUTH` is **not** set in production.
