#!/usr/bin/env python3
"""Smoke-test the rendered chart's official images and mounts, without production data."""
from pathlib import Path
import base64
import json
import os
import secrets
import subprocess
import tempfile
import time
import uuid
import yaml

root = Path(__file__).resolve().parents[1]
render = subprocess.run(['helm', 'template', 'smoke', str(root / 'charts/matomo')],
                        capture_output=True, text=True, check=True)
docs = [x for x in yaml.safe_load_all(render.stdout) if x]
web = next(x for x in docs if x['kind'] == 'Deployment')['spec']['template']['spec']
db_render = subprocess.run(['helm', 'template', 'smoke', str(root / 'charts/matomo'), '--set', 'mariadb.enabled=true'], capture_output=True, text=True, check=True)
db_docs = [x for x in yaml.safe_load_all(db_render.stdout) if x]
db_spec = next(x for x in db_docs if x['kind'] == 'StatefulSet')['spec']['template']['spec']
db_image = db_spec['containers'][0]['image']
image = web['containers'][0]['image']
prefix = 'matomo-chart-check-' + uuid.uuid4().hex[:8]
volumes = {key: prefix + '-' + key for key in ('application', 'data', 'runtime', 'db')}
network = prefix + '-net'
containers = []

def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)

def mount(source, target, subpath=None):
    value = f'type=volume,src={source},dst={target}'
    if subpath:
        value += ',volume-subpath=' + subpath
    return ['--mount', value]

try:
    docker('network', 'create', '--internal', network)
    for name in volumes.values():
        docker('volume', 'create', name)
    with tempfile.TemporaryDirectory(prefix='matomo-chart-check-') as directory:
        directory = Path(directory)
        password = secrets.token_hex(24)
        env = directory / 'database.env'
        env.write_text(f'MARIADB_DATABASE=matomo\nMARIADB_USER=matomo\nMARIADB_PASSWORD={password}\nMARIADB_ROOT_PASSWORD={secrets.token_hex(24)}\n')
        env.chmod(0o600)
        db = prefix + '-db'
        db_args = ['run', '-d', '--name', db, '--network', network, '--network-alias', 'database', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges']
        for cap in db_spec['containers'][0]['securityContext']['capabilities']['add']:
            db_args += ['--cap-add', cap]
        docker(*db_args, '--env-file', str(env), *mount(volumes['db'], '/var/lib/mysql'), db_image)
        containers.append(db)
        deadline = time.monotonic() + 120
        while docker('exec', db, 'healthcheck.sh', '--connect', '--innodb_initialized', check=False).returncode:
            if time.monotonic() > deadline:
                raise RuntimeError('Isolated database failed to initialize')
            time.sleep(2)

        init = web['initContainers'][0]
        args = ['run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL']
        for cap in init['securityContext']['capabilities']['add']:
            args += ['--cap-add', cap]
        for item in init['volumeMounts']:
            args += mount(volumes[item['name']], item['mountPath'])
        docker(*args, '--entrypoint', '/bin/sh', image, '-ec', init['args'][0])

        # This endpoint exists only in the disposable, unexposed test volume.
        endpoint = '''<?php
        $pdo = new PDO('mysql:host=database;dbname=matomo', 'matomo', getenv('MATOMO_DATABASE_PASSWORD'));
        echo PHP_VERSION . '|' . posix_geteuid() . '|' . $pdo->query('SELECT 1')->fetchColumn();
        '''
        docker('run', '--rm', '--network', 'none', *mount(volumes['application'], '/application'),
               '--entrypoint', 'php', image, '-r',
               'file_put_contents("/application/chart-runtime-check.php",base64_decode("' + base64.b64encode(endpoint.encode()).decode() + '"));')

        env = directory / 'application.env'
        env.write_text(f'MATOMO_DATABASE_HOST=database:3306\nMATOMO_DATABASE_USERNAME=matomo\nMATOMO_DATABASE_DBNAME=matomo\nMATOMO_DATABASE_PASSWORD={password}\n')
        env.chmod(0o600)
        settings = directory / 'php.ini'
        configmap = next(x for x in docs if x['kind'] == 'ConfigMap')
        settings.write_text(configmap['data']['php.ini'])
        app = prefix + '-web'
        args = ['run', '-d', '--name', app, '--network', network, '--read-only',
                '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL', '--env-file', str(env)]
        for cap in web['containers'][0]['securityContext']['capabilities']['add']:
            args += ['--cap-add', cap]
        for item in web['containers'][0]['volumeMounts']:
            if item['name'] == 'settings':
                args += ['--mount', f'type=bind,src={settings},dst={item["mountPath"]},readonly']
            else:
                args += mount(volumes[item['name']], item['mountPath'], item.get('subPath'))
        docker(*args, image)
        containers.append(app)
        deadline = time.monotonic() + 60
        while True:
            result = docker('exec', app, 'php', '-r',
                            '$v=@file_get_contents("http://127.0.0.1/chart-runtime-check.php"); if ($v===false) exit(1); echo $v;', check=False)
            if result.returncode == 0:
                assert result.stdout == '8.4.27|33|1', result.stdout
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Apache/PHP/database smoke test did not become ready')
            time.sleep(2)
        result = docker('exec', '--user', '33:33', app, 'php', '-r',
                        'if (!is_writable("/tmp") || !is_writable("/var/www/html/tmp")) exit(1); if (ini_get("session.upload_progress.enabled")) exit(2); echo "cli-ok";')
        assert result.stdout == 'cli-ok'
        print('Official Matomo PHP 8.4.27, Apache UID 33, database connection, read-only root and CLI write paths passed')
finally:
    for name in reversed(containers):
        docker('rm', '-f', name, check=False)
    for name in volumes.values():
        docker('volume', 'rm', name, check=False)
    docker('network', 'rm', network, check=False)
