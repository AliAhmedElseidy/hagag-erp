"""Host-side deployment of the reviewed repair branch; preserves live WhatsApp authentication."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

REPO = Path('/root/frappe_docker/hagag-erp-repo')
SERVICE = Path('/root/wa-baileys')
BACKUP = Path('/root/elsaidy-backups/wa-repair-20261101')
BACKEND = 'frappe_docker-backend-1'
WORKERS = ['frappe_docker-queue-short-1', 'frappe_docker-queue-long-1', 'e3e475191fe4_frappe_docker-scheduler-1']
BRANCH = 'fix/wa-production-repair-20261101'


def run(*args):
    completed = subprocess.run(args, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(f'Command failed ({args[0]}): {completed.stderr[-2000:]} {completed.stdout[-2000:]}')
    return completed.stdout


def bench(*args):
    return run('docker', 'exec', BACKEND, 'bench', '--site', 'erp.local', *args)


def auth_digest():
    creds = json.loads((SERVICE / 'session/creds.json').read_text())
    return hashlib.sha256(json.dumps({k: creds.get(k) for k in ['registrationId', 'signedIdentityKey', 'noiseKey']}, sort_keys=True).encode()).hexdigest()


assert REPO.resolve() == Path('/root/frappe_docker/hagag-erp-repo')
assert not run('git', '-C', str(REPO), 'status', '--porcelain').strip(), 'Server repository has unreviewed changes'
assert (BACKUP / 'code-config-before.tgz').is_file(), 'Code backup missing'
run('git', '-C', str(REPO), 'fetch', 'origin', BRANCH)
commit = run('git', '-C', str(REPO), 'rev-parse', 'origin/' + BRANCH).strip()
before_identity = auth_digest()
(BACKUP / 'auth-identity-before.sha256').write_text(before_identity + '\n')
site_config_path = Path('/var/lib/docker/volumes/frappe_docker_sites/_data/erp.local/site_config.json')
site_config = json.loads(site_config_path.read_text())
before_maintenance = site_config.get('maintenance_mode')
(BACKUP / 'maintenance-before.json').write_text(json.dumps({'present': 'maintenance_mode' in site_config, 'value': before_maintenance}))
bench('set-maintenance-mode', 'on')
print('Maintenance enabled; stopping messaging and workers', flush=True)
run('docker', 'stop', '-t', '60', *WORKERS)
run('docker', 'stop', '-t', '30', 'wa-baileys')
with tarfile.open(BACKUP / 'session-stopped-before.tgz', 'w:gz') as archive:
    archive.add(SERVICE / 'session', arcname='session')
os.chmod(BACKUP / 'session-stopped-before.tgz', 0o600)
# Reject a corrupt store rather than generating a replacement identity.
for auth_file in (SERVICE / 'session').glob('*.json'):
    json.loads(auth_file.read_text())
assert auth_digest() == before_identity
run('git', '-C', str(REPO), 'switch', '-c', BRANCH, '--track', 'origin/' + BRANCH)
(SERVICE / 'index.js').write_bytes((REPO / 'wa-baileys-index.js').read_bytes())
(SERVICE / 'wa-safety.mjs').write_bytes((REPO / 'wa-safety.mjs').read_bytes())
compose = SERVICE / 'docker-compose.yml'
text = compose.read_text()
if './wa-safety.mjs:/app/wa-safety.mjs:ro' not in text:
    assert '      - ./index.js:/app/index.js' in text
    text = text.replace('      - ./index.js:/app/index.js', '      - ./index.js:/app/index.js\n      - ./wa-safety.mjs:/app/wa-safety.mjs:ro')
compose.write_text(text)
dockerfile = SERVICE / 'Dockerfile'
text = dockerfile.read_text()
if 'COPY wa-safety.mjs' not in text:
    text = text.replace('COPY index.js ./', 'COPY index.js ./\nCOPY wa-safety.mjs ./')
dockerfile.write_text(text)
env_file = SERVICE / '.env'
env_lines = [line for line in env_file.read_text().splitlines() if not line.startswith('DEPLOYMENT_COMMIT=')]
env_file.write_text('\n'.join(env_lines + ['DEPLOYMENT_COMMIT=' + commit]) + '\n')
os.chmod(env_file, 0o600)
print('Source installed; updating only WhatsApp Log schema and scheduled jobs', flush=True)
bench('execute', 'frappe.reload_doc', '--args', '["hagag_erp", "doctype", "elsaidy_whatsapp_log"]')
bench('execute', 'frappe.core.doctype.scheduled_job_type.scheduled_job_type.sync_jobs')
bench('clear-cache')
run('docker', 'restart', '-t', '30', BACKEND)
run('docker', 'start', *WORKERS)
run('docker', 'compose', '-f', str(compose), 'up', '-d', '--no-build', '--force-recreate', 'wa-baileys')
assert auth_digest() == before_identity, 'WhatsApp authentication identity unexpectedly changed'
print(json.dumps({'deployed_commit': commit, 'auth_identity_preserved': True, 'maintenance_kept_on_until_health_verification': True}), flush=True)
