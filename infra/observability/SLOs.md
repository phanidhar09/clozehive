# Clozehive — Service Level Objectives

These SLOs drive the alert rules in [`alerts.yml`](./alerts.yml) and the
dashboard in [`grafana-dashboard.json`](./grafana-dashboard.json).

## Service Level Indicators (SLIs)

| SLI | Definition | Source metric |
|-----|------------|---------------|
| Availability | % of HTTP requests not returning 5xx | `http_requests_total{status}` |
| Latency | p95 request duration | `http_request_duration_seconds_bucket` |
| AI responsiveness | p95 AI/LLM call duration | `clozehive_ai_request_duration_seconds_bucket` |
| Cache effectiveness | hit / (hit+miss) | `clozehive_cache_operations_total` |

## Objectives (28-day rolling window)

| SLO | Target | Error budget |
|-----|--------|--------------|
| **Availability** | 99.5% of requests succeed | 0.5% (~3.6h/month) |
| **Latency** | 95% of requests < 1.5s | 5% may exceed |
| **AI responsiveness** | 95% of AI calls < 20s | 5% may exceed |

## Burn-rate alerting

`alerts.yml` implements multi-window multi-burn-rate alerts on the availability
SLO (Google SRE workbook pattern):

| Alert | Burn rate | Windows | Action |
|-------|-----------|---------|--------|
| `ErrorBudgetBurnFast` | 14.4× | 5m & 1h | **Page** — budget gone in ~2 days |
| `ErrorBudgetBurnSlow` | 6× | 30m & 6h | **Ticket** — investigate same day |

A 14.4× burn over the 5m+1h windows means the full 28-day budget would be spent
in ~2 days — worth waking someone. The slow alert catches sustained low-grade
degradation that wouldn't trip the fast one.

## Dashboards

`grafana-dashboard.json` (folder *Clozehive*) shows the four golden signals
(rate, errors, latency, saturation) plus business panels: AI latency/tokens,
cache hit ratio, embedding-job transport mix, and vision pipeline stage timings.

## Runbook pointers

- **HighErrorRate / ServiceDown** → check the service's logs (filter by
  `trace_id` to jump to the failing trace in Tempo), recent deploys, DB/Redis health.
- **DBPoolNearExhaustion** → check `clozehive_db_pool_connections_in_use`; consider
  the read replica (`DATABASE_READ_URL`) or raising `DB_POOL_SIZE`.
- **AILatencyHigh** → check the AI provider status + `ai-agent` traces.
- **CacheHitRatioLow** → check Redis health, TTLs, and eviction (cache vs state split).
