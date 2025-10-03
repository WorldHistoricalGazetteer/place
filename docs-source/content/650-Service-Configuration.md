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

| Subdomain                    | Purpose                      | Kubernetes Service | Port  | Access Scope  |
|------------------------------|------------------------------|--------------------|-------|---------------|
| `whgazetteer.org`            | Public-facing frontend       | `frontend`         | 443   | Public        |
| `docs.whgazetteer.org`       | Public documentation         | `docs`             | 443   | Public        |
| `blog.whgazetteer.org`       | WordPress blog               | `blog`             | 443   | Public        |
| `tileserver.whgazetteer.org` | Map tile server              | `tile-server`      | 443   | Public        |
| `admin.whgazetteer.org`      | Management API               | `management-api`   | 8000  | Pitt VPN only |
| `test.whgazetteer.org`       | Django test instance         | `django-test`      | 8443  | Pitt VPN only |
| `errors.whgazetteer.org`     | Error tracking               | `glitchtip`        | 3000  | Pitt VPN only |
| `analytics.whgazetteer.org`  | Usage analytics              | `plausible`        | 8000  | Pitt VPN only |

Each of these Services will be exposed in the cluster according to the CRC team's preferred mechanism (e.g. `NodePort`,
`LoadBalancer`, or `ClusterIP` behind an internal ingress proxy). We will adjust our service exposure strategy
accordingly once this is confirmed.

> ### ⚠️ Bot Management
> To reduce the impact of unwanted bot traffic (e.g. crawlers, scrapers, vulnerability scanners) on public-facing endpoints, we request that basic bot filtering be applied at the ingress layer.
> 
> At minimum, this should include:
> - Blocking requests from known malicious or non-browser user agents
> - Applying reasonable rate limits per IP address to mitigate brute-force or scanning behaviour (`tileserver.whgazetteer.org` would need a relatively generous allowance)
> - Preventing unauthenticated access to subdomains not intended for public use
