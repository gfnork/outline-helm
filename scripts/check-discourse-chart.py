#!/usr/bin/env python3
"""Exercise deployment modes and migration safety without accessing a cluster."""
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/discourse"


def render(*args, fails=False):
    result = subprocess.run(
        ["helm", "template", "forum", str(CHART), "--kube-version", "1.35.0", *args],
        text=True, capture_output=True,
    )
    if fails:
        assert result.returncode, "Expected invalid configuration to be rejected"
        return result.stderr
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def one(docs, kind):
    matches = [doc for doc in docs if doc["kind"] == kind]
    assert len(matches) == 1, (kind, len(matches))
    return matches[0]


def env(container):
    return {item["name"]: item for item in container["env"]}


docs = render()
web = one(docs, "Deployment")
assert web["spec"]["strategy"]["type"] == "Recreate"
assert web["spec"]["replicas"] == 1
pod = web["spec"]["template"]["spec"]
assert pod["automountServiceAccountToken"] is False
container = pod["containers"][0]
assert "@sha256:" in container["image"]
settings = env(container)
assert settings["MIGRATE_ON_BOOT"]["value"] == "0"
assert settings["CREATE_DB_ON_BOOT"]["value"] == "0"
assert settings["DISCOURSE_DB_PASSWORD"]["valueFrom"]["secretKeyRef"]["name"]
assert not any(doc["kind"] in ("Secret", "Job", "Ingress") for doc in docs)
assert one(docs, "PersistentVolumeClaim")["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
redis = one(docs, "StatefulSet")
redis_container = redis["spec"]["template"]["spec"]["containers"][0]
assert '"$(redis-cli --raw ping)" = PONG' in redis_container["readinessProbe"]["exec"]["command"][-1]
assert redis["spec"]["persistentVolumeClaimRetentionPolicy"]["whenDeleted"] == "Retain"
assert "--requirepass" not in redis_container["args"][0]

error = render("--set", "migration.enabled=true", fails=True)
assert "Stop the web/Sidekiq" in error
migration = render("--set", "web.enabled=false,migration.enabled=true")
assert not any(doc["kind"] == "Deployment" for doc in migration)
job = one(migration, "Job")
assert "helm.sh/hook" not in job["metadata"].get("annotations", {})
assert "db:migrate" in job["spec"]["template"]["spec"]["containers"][0]["args"][0]
assert job["spec"]["backoffLimit"] == 0

external = render(
    "--set", "redis.enabled=false,redis.external.host=redis.example.internal",
    "--set", "persistence.existingClaim=restored-uploads",
    "--set", "ingress.enabled=true,ingress.className=public",
    "--set", "ingress.tls[0].secretName=forum-tls,ingress.tls[0].hosts[0]=discourse.example.com",
)
assert not any(doc["kind"] in ("StatefulSet", "PersistentVolumeClaim") for doc in external)
external_pod = one(external, "Deployment")["spec"]["template"]["spec"]
assert external_pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == "restored-uploads"
assert env(external_pod["containers"][0])["DISCOURSE_REDIS_HOST"]["value"] == "redis.example.internal"
assert one(external, "Ingress")["spec"]["tls"][0]["secretName"] == "forum-tls"
assert "redis.external.host" in render("--set", "redis.enabled=false", fails=True)
assert "database" in render("--set", "database.existingSecret=", fails=True)
assert "web" in render("--set", "web.workers=0", fails=True)
paused = render("--set", "web.sidekiqWorkers=0")
assert env(one(paused, "Deployment")["spec"]["template"]["spec"]["containers"][0])["UNICORN_SIDEKIQS"]["value"] == "0"
assert "chart-managed" in render(
    "--set", "extraEnv[0].name=MIGRATE_ON_BOOT", "--set-string", "extraEnv[0].value=1", fails=True
)

ephemeral = render("--set", "persistence.enabled=false,redis.persistence.enabled=false")
assert not any(doc["kind"] == "PersistentVolumeClaim" for doc in ephemeral)
assert "volumeClaimTemplates" not in one(ephemeral, "StatefulSet")["spec"]
assert "emptyDir" in one(ephemeral, "Deployment")["spec"]["template"]["spec"]["volumes"][0]
tagged = render("--set", "image.digest=,image.tag=test-version,persistence.storageClass=-")
assert one(tagged, "Deployment")["spec"]["template"]["spec"]["containers"][0]["image"].endswith(":test-version")
assert one(tagged, "PersistentVolumeClaim")["spec"]["storageClassName"] == ""
render("-f", str(CHART / "ci/microk8s-values.yaml"))
print("Discourse chart configuration and migration safety checks passed")
