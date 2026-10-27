# Discourse community Helm chart

This chart deploys Discourse with the upstream `discourse/discourse` web-only image.
It is maintained by this repository, **not by Discourse**, and the upstream image
is still described as experimental. Discourse's supported installation method is
the `discourse_docker` launcher. Test a restore before using this chart for a live forum.

- [Upstream image and support status](https://hub.docker.com/r/discourse/discourse/)
- [Supported deployment](https://github.com/discourse/discourse_docker)
- [Discourse backup and restore guidance](https://meta.discourse.org/t/15721)

## Architecture and requirements

- Kubernetes 1.32+, Helm 3.8+ or Helm 4, and a working PVC provisioner.
- One application replica with `Recreate` updates. Nginx, the web processes, and
  embedded Sidekiq run under the image's upstream supervisor in the same container.
  `web.workers` and `web.sidekiqWorkers` set their process counts. This first release
  does not support independently scaling the web and worker processes.
- External PostgreSQL only. Provision the database, role, and extensions required
  by the selected Discourse version before migration. The chart does not create
  database roles, grant privileges, install extensions, or alter PostgreSQL volumes.
- Optional authenticated upstream Redis StatefulSet with AOF persistence, or an
  external authenticated Redis. Redis passwords are SHA-256 hashed into a temporary
  ACL file rather than placed in process arguments. The Secret file must contain
  exactly the password bytes (no trailing newline).
- Persistent `/shared` for uploads, backups, logs, and restore scratch files.
  Application PVCs are kept on uninstall; Redis PVCs are retained by the StatefulSet.
  You remain responsible for off-machine backups and checking the image's bundled
  log rotation and the retention of backups under `/shared`.
- The upstream image must initialize as root; its supervisor drops privileges for
  application processes. This chart does not satisfy the Kubernetes Restricted
  Pod Security profile. Service-account token mounting is disabled.

TLS terminates at the ingress controller; in-container Let's Encrypt is disabled.
Use ingress annotations for cert-manager, upload size limits, and proxy timeouts as
appropriate for your controller. A startup probe allows 15 minutes for asset
precompilation. Readiness checks Rails at `/srv/status`; liveness checks the Nginx
socket and deliberately does not restart the whole application during a DB outage.
That liveness check does not independently prove Sidekiq is healthy; monitor queues.

The application defaults to release `2026.7.4`, pinned by a multi-architecture image
digest. To select a different tag, set **both** `image.tag` and `image.digest=""`, or
set the new verified digest. The same precedence applies to `redis.image`.
Plugins must be included in a derived image; there is
no runtime git clone or package installation. Use the same derived image for the
web pod and migration Job.

## Credentials and configuration

Create the namespace and existing Secrets first. Use a secret manager or files
outside this repository. These commands do not embed passwords in shell history:

```sh
kubectl create namespace forum
kubectl -n forum create secret generic discourse-database \
  --from-file=password=/secure/path/database-password
kubectl -n forum create secret generic discourse-redis \
  --from-file=password=/secure/path/redis-password
```

Set the hostname, database connection, and ingress in a private values file:

```yaml
fullnameOverride: forum
hostname: forum.example.com
database:
  host: postgresql.database.svc.cluster.local
  name: discourse
  username: discourse
  existingSecret: discourse-database
redis:
  auth:
    existingSecret: discourse-redis
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  tls:
    - secretName: forum-tls
      hosts: [forum.example.com]
extraEnv:
  - name: DISCOURSE_SMTP_ADDRESS
    value: smtp.example.com
  - name: DISCOURSE_SMTP_PORT
    value: "587"
extraEnvFrom:
  - secretRef:
      name: discourse-smtp
```

Create `discourse-smtp` separately with the upstream environment variable keys
`DISCOURSE_SMTP_USER_NAME` and `DISCOURSE_SMTP_PASSWORD`. Other supported upstream
settings can be supplied through `extraEnv` and `extraEnvFrom`. Do not put credentials
in values files: Helm stores release values in the cluster. Explicit chart environment
variables take precedence over `envFrom`; do not duplicate chart-managed variables
in `extraEnv`. Changing an existing Secret does not restart pods: schedule a rollout
to pick up new environment values and reload Redis's ACL password.

For external Redis set `redis.enabled=false`, `redis.external.host`, and optionally
`redis.external.port`. Keep `redis.auth.existingSecret` configured. This release
supports password authentication without Redis TLS or a custom ACL username.

## Install and schema migrations

Use a pinned chart version for published installs. The commands below use a local
checkout. Keep using the same `forum-values.yaml` on every step; do not use
`--reuse-values` to carry obsolete Bitnami settings into this chart.

1. Provision and verify the database, required extensions, and Secrets.
2. Install storage and Redis without starting the application:

   ```sh
   helm upgrade --install forum ./charts/discourse -n forum \
     -f /secure/path/forum-values.yaml --set web.enabled=false \
     --set migration.enabled=false --wait --timeout 15m
   ```

3. Run the explicit migration Job (a failed Job is not automatically retried):

   ```sh
   helm upgrade forum ./charts/discourse -n forum \
     -f /secure/path/forum-values.yaml --set web.enabled=false \
     --set migration.enabled=true --wait --wait-for-jobs --timeout 35m
   kubectl -n forum logs job/forum-migration
   ```

4. Only after migration succeeds, start web and Sidekiq:

   ```sh
   helm upgrade forum ./charts/discourse -n forum \
     -f /secure/path/forum-values.yaml --set web.enabled=true \
     --set migration.enabled=false --wait --timeout 20m
   ```

The example uses `fullnameOverride: forum`; without it resource names are
`<release>-discourse`. The migration Job runs `bundle exec rake db:migrate` as the
image's `discourse` user. It is not a Helm lifecycle hook. Pod restarts never run
schema migrations or create the database automatically. The web startup performs
the asset precompilation required by the upstream image.

For upgrades, first take a database-and-uploads backup and confirm the restore path.
Apply step 2 to remove the old application Deployment, then wait for the old pod to
terminate before step 3:

```sh
kubectl -n forum wait --for=delete pod \
  -l app.kubernetes.io/instance=forum,app.kubernetes.io/component=web --timeout=5m
```

The template rejects `web.enabled=true` together with `migration.enabled=true`,
but cannot check whether an older pod is still running. Follow the separate stop,
wait, migrate, and start steps. A failed migration requires investigation; keep
the application stopped. Remove a failed migration Job only after inspecting it
and determining that another attempt is safe. Helm rollback does **not** undo
database migrations: restore the matching database and uploads backup if required.

## Migrating from Bitnami

This is a separate restore-and-cutover operation, not an in-place chart upgrade.
Bitnami paths (`/bitnami/discourse`, including a `discourse` PVC subdirectory) do not
match the upstream `/shared` layout. Never attach the existing Bitnami application
PVC directly to the new container or change the database container image in place.

1. Inventory the actual running Discourse version (the old chart's `appVersion`
   can be stale), plugins, themes, authentication, SMTP, and externally stored uploads.
   Select a compatible target version and plugin set; do not restore a newer backup
   onto older Discourse. Avoid combining unrelated database upgrades with migration.
2. Produce a Discourse backup including uploads, save the release configuration
   and plugin inventory securely, and copy backups off-machine. Check the archive
   is readable and contains the expected database and uploads.
3. Provision an isolated database, dedicated Redis, and new PVC in a staging
   namespace. Use `ci/microk8s-values.yaml` as a non-secret starting point. Do not
   reference the production database, production Redis, or production PVCs.
4. Rehearse the upstream restore procedure against that isolated installation.
   Disable outbound mail and external integrations before starting restored jobs;
   `DISCOURSE_DISABLE_EMAILS=yes` is included in the sample, and an SMTP sink or
   network restriction provides an additional safeguard. Do not expose staging
   publicly until its restored content and authentication have been reviewed.
5. Verify posts/users, attachments, uploads, login/SSO, themes/plugins, background
   jobs, HTTPS, and email behavior. A green Kubernetes readiness probe is insufficient.
6. For cutover, stop writes and drain/pause the old workers; take and restore a final
   backup. Database backups do not preserve queued Redis jobs. Move the production
   ingress to the replacement only after final verification. Enable integrations
   and mail deliberately. Keep the old database, PVCs, and images for rollback.
7. After an agreed retention period and a tested off-machine backup, retire the old
   release explicitly. Inspect its resources first: uninstalling the Bitnami chart
   can delete release-managed storage. Do not uninstall it as part of a trial.

If external PostgreSQL also uses a Bitnami image, replacing this chart does not
migrate that server or its other databases. Plan and verify that operation separately.

## Validation and publishing

```sh
helm lint --strict charts/discourse
python3 scripts/check-discourse-chart.py  # requires PyYAML
helm package charts/discourse --destination /tmp/chart-packages
```

`.github/workflows/discourse-ci.yml` validates this chart independently of Outline.
The existing chart-releaser workflow discovers `charts/discourse` alongside
`charts/outline` and publishes versioned packages and the GitHub Pages index when
changes reach `main`. A chart version bump is required for each release. Repository
Pages/Actions settings and the first published artifact must be checked before
advertising a repository URL. No generated repository index needs manual editing.

Static rendering checks are not a production restore test. Before publishing a
production recommendation, validate the pinned image and restore path on a staging
cluster with your storage class and PostgreSQL configuration.
