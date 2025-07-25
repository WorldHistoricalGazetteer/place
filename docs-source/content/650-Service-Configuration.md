# Service Configuration

This document outlines the proposed mapping between public-facing subdomains and internal Kubernetes Services for the
World Historical Gazetteer (WHG) deployment on the Pitt University CRC-managed VM.

We assume that Ingress is managed centrally by CRC (e.g. via an institutional NGINX or HAProxy setup). As such, we do
*not* plan to deploy our own Ingress controller within the cluster. We also assume that TLS termination will be handled
upstream.

> ### ⚠️ QUESTION:
> During initial testing and development, would it be practical to use `pitt.whgazetteer.org` as the base domain for the
> public frontend, with all related subdomains nested under it (e.g., `admin.pitt.whgazetteer.org`,
> `test.pitt.whgazetteer.org`), rather than deploying directly under `whgazetteer.org`? This would allow us to maintain
> our existing site without unnecessary complications until we are ready to fully transition to the new setup.

## Proposed Subdomain Mapping

| Subdomain                    | Purpose                      | Kubernetes Service | Port | Access Scope    |
|------------------------------|------------------------------|--------------------|------|-----------------|
| `whgazetteer.org`            | Public-facing frontend       | `frontend`         | 80   | Public          |
| `docs.whgazetteer.org`       | Public documentation         | `docs`             | 80   | Public          |
| `blog.whgazetteer.org`       | WordPress blog               | `blog`             | 80   | Public          |
| `tileserver.whgazetteer.org` | Map tile server              | `tile-server`      | 80   | Public          |
| `api.whgazetteer.org`        | Public API                   | `public-api`       | 80   | Public          |
| `admin.whgazetteer.org`      | Management API               | `management-api`   | 8000 | CI/CD, Pitt VPN |
| `test.whgazetteer.org`       | Django test instance         | `django-test`      | 80   | Pitt VPN only   |
| `errors.whgazetteer.org`     | Error tracking               | `glitchtip`        | 3000 | Pitt VPN only   |
| `analytics.whgazetteer.org`  | Usage analytics              | `plausible`        | 8000 | Pitt VPN only   |
| `monitor.whgazetteer.org`    | Prometheus + Grafana metrics | `grafana`          | 3000 | Pitt VPN only   |

Each of these Services will be exposed in the cluster according to the CRC team's preferred mechanism (e.g. `NodePort`,
`LoadBalancer`, or `ClusterIP` behind an internal ingress proxy). We will adjust our service exposure strategy
accordingly once this is confirmed.

The CI/CD pipeline is a simple secured GitHub Action which polls the management API, causing a pull of the relevant directories
and re-application of the associated Helm charts (see `.github/workflows/notify-pitt.yml` and `deployment/app/api.py`).