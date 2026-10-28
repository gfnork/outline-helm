# RoadAtlas chart

This chart deploys RoadAtlas, an isolated PostgreSQL 18 database, ingress, and
read-only locally generated place data on a single-node MicroK8s host.

The place index is not stored in the chart or application image. Upload an
immutable release to `/srv/roadatlas-data/releases/<release>` with the
RoadAtlas repository's `npm run deploy:place-index` command, then select it
through `placeIndex.release`.

Create `roadatlas-runtime` before installing the chart. It must contain
`DATABASE_URL`, `POSTGRES_PASSWORD`, `BETTER_AUTH_SECRET`, `CHIBIGEO_SECRET`,
and the `SMTP_*` variables. Create `roadatlas-registry` as a Docker registry
Secret when the application image is private. Do not commit credentials.

PostgreSQL 18 stores its versioned `PGDATA` below `/var/lib/postgresql`; the
PVC deliberately mounts at that parent path. The PVC has Helm's `keep`
resource policy. No scheduled database backup is included, so take a current
`pg_dump` before deploying schema-changing application releases.

Validate with:

```sh
helm lint --strict charts/roadatlas -f charts/roadatlas/ci/microk8s-values.yaml
python3 scripts/check-roadatlas-chart.py
```

