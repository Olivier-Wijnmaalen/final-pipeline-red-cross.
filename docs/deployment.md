# Web deployment

## Local

Install the Python requirements (including `requirements-stage0.txt`) and then:

```powershell
cd web
npm ci
npm run dev
```

Live runs use the repository Python environment. Set `PYTHON_BIN` if `python`
is not the correct executable. Configure provider secrets only in the root
`.env`. For baseline mode, set `DEMA_BASELINE_BANK` to an approved local bank.

## Red Cross-managed Vercel

Import this private GitHub repository, set Root Directory to `web`, Framework
Preset to Next.js, Install Command to `npm ci`, and Build Command to
`npm run build`. The sample works without secrets. Live processing requires an
external worker and durable object/blob storage because Vercel functions have
ephemeral filesystems and execution limits. Configure `DEMA_REMOTE_WORKER_URL`
and `DEMA_REMOTE_WORKER_TOKEN` as encrypted project variables after that worker
is approved.

The worker contract is authenticated HTTPS: `POST /jobs` accepts multipart
`run_id`, `country`, `mode`, and `document`; `GET /jobs/<run-id>` returns the
same status shape as the local worker and includes `dashboard` when complete;
`GET /jobs/<run-id>/artifacts/<name>` returns one of `evidence`, `score`,
`manifest`, or `dashboard`. The worker owns durable storage and retention.

Protect preview and production deployments with Red Cross organizational SSO
or Vercel deployment protection. Do not expose the application publicly. Add
the approved internal demo URL to the main README after deployment.
