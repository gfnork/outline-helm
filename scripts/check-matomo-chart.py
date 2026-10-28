#!/usr/bin/env python3
"""Validate the chart's persistence, migration isolation and security contract."""
from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parents[1]
chart = root / 'charts/matomo'

def render(*args, success=True):
    r = subprocess.run(['helm', 'template', 'audit', str(chart), *args],
                       capture_output=True, text=True)
    if not success:
        assert r.returncode != 0, 'Invalid configuration unexpectedly rendered'
        return []
    assert r.returncode == 0, r.stderr
    return [d for d in yaml.safe_load_all(r.stdout) if d]

def pods(docs):
    for d in docs:
        if d['kind'] in ('Deployment', 'StatefulSet', 'Job'):
            yield d, d['spec']['template']['spec']
        elif d['kind'] == 'CronJob':
            yield d, d['spec']['jobTemplate']['spec']['template']['spec']

docs = render()
assert not any(d['kind'] in ('Secret', 'Role', 'ClusterRole', 'RoleBinding', 'ClusterRoleBinding') for d in docs)
assert all(d['spec']['type'] == 'ClusterIP' for d in docs if d['kind'] == 'Service')
assert not any(d['kind'] in ('StatefulSet', 'Job') for d in docs)
assert len([d for d in docs if d['kind'] == 'CronJob']) == 2
expected = 'docker.io/library/matomo@sha256:a54f3b69220b43cdcf2607f03fa2622d4f796cc3ce2820b31012b445c1fc43ed'
for d, spec in pods(docs):
    assert spec['automountServiceAccountToken'] is False
    assert all('hostPath' not in v for v in spec['volumes'])
    for c in spec.get('initContainers', []) + spec['containers']:
        assert c['image'] == expected
        assert c['securityContext']['allowPrivilegeEscalation'] is False
    c = spec['containers'][0]
    env = {e['name']: e for e in c['env']}
    assert 'valueFrom' in env['MATOMO_DATABASE_PASSWORD']
    assert c['securityContext']['readOnlyRootFilesystem'] is True
    mounts = {m['mountPath']: m for m in c['volumeMounts']}
    for path in ('config', 'plugins', 'tmp', 'js', 'misc/user'):
        assert mounts['/var/www/html/' + path]['name'] == 'data'
    script = spec['initContainers'][0]['args'][0]
    assert 'cp -a /usr/src/matomo/. /application/' in script
    if d['kind'] == 'CronJob':
        assert 'rm -rf' not in script, 'Recurring jobs must not overwrite live plugins'
        assert c['securityContext']['runAsNonRoot'] is True
        assert d['spec']['concurrencyPolicy'] == 'Forbid'

docs = render('--set', 'web.enabled=false', '--set', 'migration.enabled=true',
              '--set', 'mariadb.enabled=true', '--set', 'cron.archive.suspend=true',
              '--set', 'cron.scheduledTasks.suspend=true',
              '--set', 'persistence.existingClaim=restored-files',
              '--set', 'mariadb.persistence.existingClaim=restored-database',
              '--set', 'config.existingSecret=restored-config')
assert not any(d['kind'] in ('Deployment', 'PersistentVolumeClaim') for d in docs)
job = next(d for d in docs if d['kind'] == 'Job')
assert job['spec']['backoffLimit'] == 0
assert job['spec']['template']['metadata']['labels']['app.kubernetes.io/instance'] == 'audit'
assert job['spec']['template']['metadata']['labels']['app.kubernetes.io/component'] == 'migration'
migrate = job['spec']['template']['spec']['containers'][0]
assert migrate['command'] == ['/bin/sh', '-ec']
assert migrate['args'][0].count('php /var/www/html/console core:update --yes') == 2
db = next(d for d in docs if d['kind'] == 'StatefulSet')
assert 'volumeClaimTemplates' not in db['spec']
assert db['spec']['persistentVolumeClaimRetentionPolicy']['whenDeleted'] == 'Retain'
assert db['spec']['template']['spec']['containers'][0]['image'] == 'docker.io/library/mariadb@sha256:d46e102fa8b9b72bfcdeb56f9dd538742092119dc8b11f31fe662605cd234cd9'
for _, spec in pods(docs):
    assert spec['automountServiceAccountToken'] is False

render('--set', 'migration.enabled=true', success=False)
render('--set', 'web.enabled=false', '--set', 'migration.enabled=true',
       '--set', 'cron.archive.suspend=false', success=False)
render('--set', 'database.existingSecret=', success=False)
render('--set', 'extraEnv[0].name=MATOMO_DATABASE_PASSWORD',
       '--set', 'extraEnv[0].value=unsafe', success=False)
print('Matomo storage, migration, cron, secret and service-account checks passed')
