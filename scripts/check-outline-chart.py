#!/usr/bin/env python3
"""Check image selection and upload limits in both Outline processes."""
from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parents[1]
chart = root / "charts/outline"

def render(*args):
    result = subprocess.run(
        ["helm", "template", "outline", str(chart), "--kube-version", "1.35.0", *args],
        capture_output=True, text=True, check=True,
    )
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    spec = deployment["spec"]["template"]["spec"]
    return spec["initContainers"] + spec["containers"]

for container in render():
    assert container["image"] == "outlinewiki/outline:1.12.0"
    env = {entry["name"]: entry for entry in container["env"]}
    assert env["FILE_STORAGE_UPLOAD_MAX_SIZE"]["value"] == "26214400"

digest = "sha256:" + "a" * 64
for container in render("--set", "image.digest=" + digest,
                        "--set", "outline.aws.s3.maxSize=52428800"):
    assert container["image"] == "outlinewiki/outline@" + digest
    env = {entry["name"]: entry for entry in container["env"]}
    assert env["FILE_STORAGE_UPLOAD_MAX_SIZE"]["value"] == "52428800"
    assert env["AWS_S3_UPLOAD_MAX_SIZE"]["value"] == "52428800"
print("Outline image and application/init upload-limit checks passed")
