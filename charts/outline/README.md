# Outline chart

This chart uses the upstream Outline image and an optional upstream Redis instance.
PostgreSQL is external. Version 0.5.4 defaults to Outline 1.12.0.

Set `image.digest` to pin an immutable upstream image; when present, it takes
precedence over `image.tag`. The same image is used for the database migration
init container and the application. An upgrade may change the database schema:
take a current database backup and preserve the previous values and image digest
before upgrading. Reverting the image alone does not undo a schema migration.

`outline.aws.s3.maxSize` sets both `AWS_S3_UPLOAD_MAX_SIZE` and
`FILE_STORAGE_UPLOAD_MAX_SIZE` in both containers. Allow sufficient request size
at the ingress for the desired upload size plus multipart request overhead.

Validate before publishing:

```sh
helm lint --strict charts/outline
python3 scripts/check-outline-chart.py
```

Do not commit deployment values that contain credentials. Store private values
with restricted permissions or reference existing Secrets through `envFrom`.
