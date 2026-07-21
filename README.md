> ## ⚠️ NOT IN PRODUCTION USE
>
> This repository holds **Kubernetes configuration** created when WHG planned to migrate
> hosting from DigitalOcean to Pitt CRC on a K8s cluster. That migration proved unworkable
> and was abandoned, so none of these manifests were ever adopted in production.
>
> **What runs instead:** WHG production is hosted on DigitalOcean using plain Docker Compose.
> The Django application is deployed from the [`website`](https://github.com/WorldHistoricalGazetteer/website)
> repo; authority-file indexing lives in [`indexing`](https://github.com/WorldHistoricalGazetteer/indexing).
> Supporting services (Zulip, Plausible, GlitchTip, WordPress) run from their own upstream
> Compose projects on the server.
>
> The Vespa search work explored here is also superseded: Elasticsearch covers current needs
> and is expected to remain part of the planned **v4** (graph data model —
> see https://docs.whgazetteer.org/content/v4/data-model.html).
>
> Kept read-only for historical reference. Do not deploy from this repo.

---

![WHG Logo](https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/refs/heads/main/whg_logo.png)

# World Historical Gazetteer: PLACE

### This is the repository for the **WHG PLACE** (Placement+Path+Period Linkage, Alignment, and Concordance Engine).

It contains the Kubernetes server configuration files for deploying and managing the World Historical Gazetteer (WHG)
application. This repository is separate from the main Django application
code ([here](https://github.com/WorldHistoricalGazetteer/whg3)), and provides a dedicated space for
configuring and orchestrating the server environment.

**Full documentation can be found at [docs.whgazetteer.org](https://docs.whgazetteer.org/content/500-System.html).**
