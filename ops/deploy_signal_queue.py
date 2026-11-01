"""VPS host: deploy the pinned queue fairness patch without replacing authentication."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
from patch_signal_queue import patch_queue
from patch_auth_state import patch_auth

SERVICE = Path('/root/wa-baileys')
BACKUP = Path('/root/elsaidy-backups/wa-acceptance-20261101')
REPO = Path('/root/frappe_docker/hagag-erp-repo')


def run(*args):
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr.decode(errors="replace")[-1000:]}')
    return result.stdout


def identity(data):
    value = {key: data.get(key) for key in ['registrationId', 'signedIdentityKey', 'noiseKey']}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


assert not run('git', '-C', str(REPO), 'status', '--porcelain').strip()
BACKUP.mkdir(mode=0o700, parents=True, exist_ok=True)
original = run('docker', 'exec', 'wa-baileys', 'cat', '/app/node_modules/libsignal/src/queue_job.js')
patched = patch_queue(original)  # Reject unreviewed or already patched input.
original_auth_module = run('docker', 'exec', 'wa-baileys', 'cat', '/app/node_modules/@whiskeysockets/baileys/lib/Utils/use-multi-file-auth-state.js')
patched_auth_module = patch_auth(original_auth_module)
compose = SERVICE / 'docker-compose.yml'
mount = '      - ./libsignal-queue-job.js:/app/node_modules/libsignal/src/queue_job.js:ro'
auth_mount = '      - ./wa-auth-state.js:/app/node_modules/@whiskeysockets/baileys/lib/Utils/use-multi-file-auth-state.js:ro'
config = compose.read_text()
assert mount not in config
assert auth_mount not in config
assert '      - ./index.js:/app/index.js' in config
(BACKUP / 'compose-before-signal-fairness.yml').write_bytes(compose.read_bytes())
(BACKUP / 'libsignal-queue-original.cjs').write_bytes(original)
(BACKUP / 'wa-auth-state-original.js').write_bytes(original_auth_module)
(BACKUP / 'index-before-auth-guard.js').write_bytes((SERVICE / 'index.js').read_bytes())
os.chmod(BACKUP / 'compose-before-signal-fairness.yml', 0o600)
# Recover only a proven zero-byte credential file, never overwrite a different
# valid identity or restore any Signal session/ratchet file from an old snapshot.
expected_identity = Path('/root/elsaidy-backups/wa-repair-20261101/auth-identity-before.sha256').read_text().strip()
with tarfile.open(BACKUP / 'session-before-paging-fix.tgz') as archive:
    backup_credentials = archive.extractfile('session/creds.json').read()
assert identity(json.loads(backup_credentials)) == expected_identity
run('docker', 'stop', '-t', '30', 'wa-baileys')
credentials_path = SERVICE / 'session/creds.json'
current_credentials = credentials_path.read_bytes()
recovered = not current_credentials
if recovered:
    (BACKUP / 'creds-zero-before-recovery.json').write_bytes(current_credentials)
    temporary = credentials_path.with_name('creds.recovery.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'wb') as target:
        target.write(backup_credentials); target.flush(); os.fsync(target.fileno())
    os.replace(temporary, credentials_path)
assert identity(json.loads(credentials_path.read_bytes())) == expected_identity
(SERVICE / 'libsignal-queue-job.js').write_bytes(patched)
(SERVICE / 'wa-auth-state.js').write_bytes(patched_auth_module)
(SERVICE / 'index.js').write_bytes((REPO / 'wa-baileys-index.js').read_bytes())
compose.write_text(config.replace('      - ./index.js:/app/index.js', '      - ./index.js:/app/index.js\n' + mount + '\n' + auth_mount))
commit = run('git', '-C', str(REPO), 'rev-parse', 'HEAD').decode().strip()
env_file = SERVICE / '.env'
lines = [line for line in env_file.read_text().splitlines() if not line.startswith('DEPLOYMENT_COMMIT=')]
env_file.write_text('\n'.join(lines + ['DEPLOYMENT_COMMIT=' + commit]) + '\n')
run('docker', 'compose', '-f', str(compose), 'up', '-d', '--no-deps', '--no-build', '--force-recreate', 'wa-baileys')
assert identity(json.loads(credentials_path.read_bytes())) == expected_identity
print(json.dumps({'commit': commit, 'auth_identity_preserved': True, 'zero_byte_creds_recovered': recovered,
                  'signal_session_files_restored_or_deleted': False, 'signal_queue_sha256': hashlib.sha256(patched).hexdigest()}))
