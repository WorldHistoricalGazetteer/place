# GlitchTip Helm Chart

Based on https://gitlab.com/burke-software/django-helm-chart/

This helm chart will deploy GlitchTip web, worker, migration job, postgres (if enabled), and valkey (if enabled).

# Usage

1. Add our Helm chart repo `helm repo add glitchtip https://gitlab.com/api/v4/projects/16325141/packages/helm/stable`
2. Review our values.yaml and values.sample.yaml. At a minimum, decide if using helm postgresql and set env.secret.SECRET_KEY
3. Install the chart `helm install glitchtip glitchtip/glitchtip -f your-values.yaml`. You'll need to specify your own values.yml file or make use of `--set`

For postgresql, we recommend an externally managed database and providing only the DATABASE_URL environment variable. If using helm managed postgresql, then make sure to consider:

- If you uninstall the chart, it will not delete the pvc. If you reinstall the chart, it won't have the correct password because of this.
- postgresql helm chart does not support major upgrades (such as 14.0 to 15.0). It will fail to start. You could export to a sql file and import if downtime is acceptable. Minor updates are supported.

## Important Tips

- Use [helm diff](https://github.com/databus23/helm-diff) to preview changes
- Set image.pullPolicy to `IfNotPresent` after specifying the image.tag
- Set valkey.auth.password to avoid valkey being entirely remade on each release
- If updating the chart, carefully review values for any new defaults

## Updating

See changes in this chart on [GitLab](https://gitlab.com/glitchtip/glitchtip-helm-chart/-/releases)

- `helm repo update`
- Set the image.tag to the [latest version](https://gitlab.com/glitchtip/glitchtip-frontend/-/releases)
- `helm diff upgrade glitchtip glitchtip/glitchtip`
- Carefully review diff
- `helm upgrade glitchtip glitchtip/glitchtip -f your-values.yaml`


# Contributing

Please open issues only with potential solutions and be prepared to do some work or else fund it. Contributors are welcome. However, we kindly ask that feature requests and support requests not be opened in this repo.
