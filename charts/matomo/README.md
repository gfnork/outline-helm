# Matomo

This chart runs the official `matomo` Apache image, with optional official
MariaDB or an existing database. It does not depend on Bitnami charts or images.
Both default images are pinned to immutable manifest digests.

## Installation

Create a Secret containing a `password` key for the database connection. If
`mariadb.enabled=true`, also provide a `root-password` key. Supply secrets through
your secret manager or private files; never commit passwords in Helm values.

```yaml
database:
  existingSecret: matomo-database
  host: existing-database.example.internal
  port: 3306
  name: matomo
  username: matomo
persistence:
  storageClass: longhorn
cron:
  archive:
    url: https://analytics.example.org
```

For a bundled database, set `mariadb.enabled=true`; `database.host` is then ignored.
The chart creates a single MariaDB StatefulSet and retains its PVC on removal.
When updating images, replace their pinned digests with the verified new manifests.

```sh
helm repo add gfnork https://gfnork.github.io/outline-helm/
helm repo update
helm upgrade --install analytics gfnork/matomo -f private-values.yaml
```

For an existing installation, provide the complete `config.ini.php` through a
Secret using `config.existingSecret`, or migrate it into the PVC before enabling
the web deployment. The Secret is copied only when the PVC has no config file.
Changing that Secret does not silently overwrite an established installation.
For a fresh installation, complete Matomo's installer before enabling archival.
Both cron jobs are suspended by default; set their `suspend` values to `false`
only once configuration and migration checks are complete.

## Persistence and upgrades

Application code is copied from the pinned image into an `emptyDir` at pod startup.
Only `config`, `plugins`, `tmp`, `js`, and `misc` are persistent. New official bundled
plugins and `global.ini.php` replace their old versions during a web or explicit
migration startup. Additional custom/premium plugin directories are preserved;
check their compatibility before an upgrade. Cron jobs copy application code into
their own ephemeral directory and never overwrite plugins while the web serves.

PHP runs as Apache's `www-data` user (UID 33). Apache's parent starts as root to bind
its port and drop privileges, with a read-only root filesystem and a limited
capability set. CLI jobs run as UID 33. No workload mounts a service-account token.
The init process needs root only to populate application files and set ownership
on the persistent directories. The Service is always ClusterIP.

`persistence.existingClaim` adopts no resources; it only mounts a supplied PVC.
The default access mode is ReadWriteOnce, and the web deployment uses Recreate.
For multi-node scheduling, use an appropriate RWX claim or ensure web and CLI jobs
can mount the RWO claim on the same node. This chart does not implement HA.

## Migrating from Bitnami

Test the procedure on restored data before redirecting production traffic.

1. Record the old Helm revision, image digests, ingress routes, database settings,
   active plugin list and table prefix. Back up **all** Matomo database tables and
   the full persisted file tree. Validate the dumps and retain the original PVCs.
2. Install this chart under a separate release name with `web.enabled=false`,
   both cron jobs suspended, and `migration.enabled=false`. Use fresh app and
   database PVCs for the test migration, or a separate restored database.
3. Restore the SQL dump into the destination database. Preserve all tables,
   including historical archives, logs, users, sites, settings and plugin tables.
4. Copy the old `config` directory into `config`, old `plugins` into `plugins`,
   old `tmp` into `tmp`, old `js` into `js`, and the complete old `misc` directory into `misc` on the new application
   PVC. Preserve configuration secrets, salts, SMTP settings, trusted hosts,
   custom plugins and GeoIP/user files, including databases directly under `misc`. Do not copy old application core code.
   Inspect any additional site-specific persisted files and absolute paths.
5. Privately update only the database connection fields in `config/config.ini.php`
   for the destination database. Preserve the existing table prefix and remaining
   configuration. Review any Bitnami-specific filesystem paths.
6. Enable `migration.enabled=true` while the web is disabled and crons remain
   suspended. Wait for the `*-migrate-<revision>` Job to succeed. This is an explicit
   CLI `core:update --yes` in two idempotent passes: plugin activation in the first
   pass can introduce dimensions requiring the second pass. There are no automatic
   Helm migration hooks.
7. Disable the migration Job, enable the web deployment, and test login, site/user
   counts, historical reports, custom plugins, tracking endpoints and both CLI
   tasks against the restored data. Confirm the running PHP version is patched.
8. For final cutover, stop old web writes and suspend old cron jobs. Make a **fresh**
   consistent database/file backup, refresh the destination data, repeat the schema
   migration and validation, then redirect ingress to the new ClusterIP Service.
   Enable the new cron jobs only after cutover. Avoid two archivers or two web
   installations writing to the same database during migration.

Retain the old release, database and PVCs until the new installation is accepted.
Rollback routes traffic to the old installation with its original database and
files. Do not run older Matomo code against a database already upgraded in place.
Any events accepted after cutover must be reconciled before reverting databases.

## Validation

```sh
helm lint --strict charts/matomo
python scripts/check-matomo-chart.py
python scripts/check-matomo-runtime.py  # requires Docker
helm package charts/matomo --destination /tmp/chart-packages
```

The render checks validate security and persistence contracts. The runtime check
uses temporary Docker volumes and an internal-only network to verify Apache, PHP,
CLI permissions and a fresh database connection. It cleans up its own resources.
These checks do not replace a restored-production-data migration test.
