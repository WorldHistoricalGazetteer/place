# Service Configuration

This document outlines the proposed mapping between public-facing subdomains and internal Kubernetes Services for the
World Historical Gazetteer (WHG) deployment on the Pitt University CRC-managed VM.

We assume that Ingress is managed centrally by CRC (e.g. via an institutional NGINX or HAProxy setup). As such, we do 
*not* plan to deploy our own Ingress controller within the cluster. We also assume that TLS termination will be handled
upstream.

## Proposed Subdomain Mapping

| Subdomain                    | Purpose                | Kubernetes Service | Port | Access Scope    |
|------------------------------|------------------------|--------------------|------|-----------------|
| `whgazetteer.org`            | Public-facing frontend | `frontend`         | 80   | Public          |
| `docs.whgazetteer.org`       | Public documentation   | `docs`             | 80   | Public          |
| `blog.whgazetteer.org`       | WordPress blog         | `blog`             | 80   | Public          |
| `tileserver.whgazetteer.org` | Map tile server        | `tile-server`      | 80   | Public          |
| `api.whgazetteer.org`        | Public API             | `public-api`       | 80   | Public          |
| `admin.whgazetteer.org`      | Management API         | `management-api`   | 8000 | CI/CD, Pitt VPN |
| `test.whgazetteer.org`       | Django test instance   | `django-test`      | 80   | Pitt VPN only   |

Each of these Services will be exposed in the cluster according to the CRC team's preferred mechanism (e.g. `NodePort`,
`LoadBalancer`, or `ClusterIP` behind an internal ingress proxy). We will adjust our service exposure strategy
accordingly once this is confirmed.