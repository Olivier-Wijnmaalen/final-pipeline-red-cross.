# Application architecture

```text
upload -> Stage 0 -> Stage 1 -> validated evidence bank -> Stage 2
       -> dashboard adapter -> dashboard-data.json -> visualizer
```

The Python pipeline remains authoritative. `dashboard_adapter/` is the only
translation layer. `web/` starts jobs and displays the contract; it does not
score indicators. Runs use generated IDs and live under ignored `runs/` paths.

The web job boundary has two implementations:

- local: a detached Python worker and filesystem-backed status/artifacts;
- production: `DEMA_REMOTE_WORKER_URL`, an authenticated HTTPS worker that
  implements `POST /jobs` and writes status/artifacts to durable shared storage.

The sample route creates a run from committed fictional artifacts without
model calls. The initial interface is deliberately empty.
