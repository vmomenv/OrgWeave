# Monitoring (planned)

Phase 0 does **not** run Prometheus or Grafana. Health is exposed through the
API readiness endpoint and Docker healthchecks.

When monitoring is added:

- Scrape `/api/v1/health/ready` with a blackbox exporter or add a `/metrics`
  endpoint backed by `prometheus_client`.
- Export worker heartbeat age as a gauge (Redis key TTL / `updated_at`).
- Alert on readiness degradation, stale worker heartbeats and HTTP error rates.
- Do not expose tenant identifiers or credentials in metrics labels.
