#!/usr/bin/env python3

import pathlib
import subprocess
import sys

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "roadatlas"
VALUES = CHART / "ci" / "microk8s-values.yaml"


def render() -> list[dict]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "roadatlas",
            str(CHART),
            "--namespace",
            "roadatlas",
            "--values",
            str(VALUES),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def resource(resources: list[dict], kind: str, name: str) -> dict:
    for candidate in resources:
        if candidate.get("kind") == kind and candidate.get("metadata", {}).get("name") == name:
            return candidate
    raise AssertionError(f"Missing {kind}/{name}")


def main() -> None:
    resources = render()
    deployment = resource(resources, "Deployment", "roadatlas")
    stateful_set = resource(resources, "StatefulSet", "roadatlas-postgresql")
    pvc = resource(resources, "PersistentVolumeClaim", "roadatlas-postgresql")
    ingress = resource(resources, "Ingress", "roadatlas")

    template = deployment["spec"]["template"]
    assert template["metadata"]["annotations"]["roadatlas.eu/place-index-release"] == "test-release"
    host_path = template["spec"]["volumes"][0]["hostPath"]
    assert host_path == {
        "path": "/srv/roadatlas-data/releases/test-release",
        "type": "Directory",
    }
    assert deployment["spec"]["strategy"]["type"] == "Recreate"
    assert template["spec"]["automountServiceAccountToken"] is False

    postgres_container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    mounts = {mount["mountPath"] for mount in postgres_container["volumeMounts"]}
    assert "/var/lib/postgresql" in mounts
    assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"

    assert ingress["spec"]["ingressClassName"] == "public"
    assert ingress["spec"]["rules"][0]["host"] == "app.roadatlas.eu"
    assert ingress["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "letsencrypt-prod"

    print(f"Validated {len(resources)} rendered RoadAtlas resources")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error

