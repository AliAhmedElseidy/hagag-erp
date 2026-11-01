"""VPS host: deploy the pinned queue fairness patch without replacing authentication."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from patch_signal_queue import patch_queue

SERVICE = Path('/root/wa-baileys')
BACKUP = Path('/root/elsaidy-backups/wa-acceptance-20261101')
REPO = Path('/root/frappe_docker/hagag-erp-repo')


def run(*args):
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr.decode(errors="replace")[-1000:]}')
    return result.stdout


def identity():
    for attempt in range(30):
        try:
            data = json.loads((SERVICE / 'session/creds.json').read_text())
            value = {key: data.get(key) for key in ['registrationId', 'signedIdentityKey', 'noiseKey']}
            return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        except json.JSONDecodeError:
            time.sleep(0.1)  # The installed multi-file store uses non-atomic writes.
    raise RuntimeError('Auth store unreadable; no reset or restore attempted')


assert not run('git', '-C', str(REPO), 'status', '--porcelain').strip()
BACKUP.mkdir(mode=0o700, parents=True, exist_ok=True)
original = run('docker', 'exec', 'wa-baileys', 'cat', '/app/node_modules/libsignal/src/queue_job.js')
patched = patch_queue(original)  # Reject unreviewed or already patched input.
compose = SERVICE / 'docker-compose.yml'
mount = '      - ./libsignal-queue-job.js:/app/node_modules/libsignal/src/queue_job.js:ro'
config = compose.read_text()
assert mount not in config
assert '      - ./index.js:/app/index.js' in config
(BACKUP / 'compose-before-signal-fairness.yml').write_bytes(compose.read_bytes())
(BACKUP / 'libsignal-queue-original.cjs').write_bytes(original)
os.chmod(BACKUP / 'compose-before-signal-fairness.yml', 0o600)
before = identity()
run('docker', 'stop', '-t', '30', 'wa-baileys')
(SERVICE / 'libsignal-queue-job.js').write_bytes(patched)
compose.write_text(config.replace('      - ./index.js:/app/index.js', '      - ./index.js:/app/index.js\n' + mount))
commit = run('git', '-C', str(REPO), 'rev-parse', 'HEAD').decode().strip()
env_file = SERVICE / '.env'
lines = [line for line in env_file.read_text().splitlines() if not line.startswith('DEPLOYMENT_COMMIT=')]
env_file.write_text('\n'.join(lines + ['DEPLOYMENT_COMMIT=' + commit]) + '\n')
run('docker', 'compose', '-f', str(compose), 'up', '-d', '--no-deps', '--no-build', '--force-recreate', 'wa-baileys')
assert identity() == before
print(json.dumps({'commit': commit, 'auth_identity_preserved': True, 'signal_queue_sha256': hashlib.sha256(patched).hexdigest()}))
