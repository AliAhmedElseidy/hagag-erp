import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

export function serviceDiagnostics(directory) {
  let packageVersion = null;
  try {
    const require = createRequire(import.meta.url);
    let candidate = path.dirname(require.resolve('@whiskeysockets/baileys'));
    for (let depth = 0; depth < 5; depth++) {
      const manifest = path.join(candidate, 'package.json');
      if (fs.existsSync(manifest)) {
        const pkg = JSON.parse(fs.readFileSync(manifest, 'utf8'));
        if (pkg.name === '@whiskeysockets/baileys') { packageVersion = pkg.version; break; }
      }
      candidate = path.dirname(candidate);
    }
  } catch (_) { /* Report unknown rather than inventing an installed version. */ }
  let readable = false, writable = false, credentialsPresent = false;
  try { fs.accessSync(directory, fs.constants.R_OK); readable = true; } catch (_) {}
  try { fs.accessSync(directory, fs.constants.W_OK); writable = true; } catch (_) {}
  credentialsPresent = fs.existsSync(path.join(directory, 'creds.json'));
  return { node_version: process.version, baileys_version: packageVersion,
    deployment_commit: process.env.DEPLOYMENT_COMMIT || null,
    session: { readable, writable, credentials_present: credentialsPresent },
    container_status: 'running', restart_count: null, backup_status: 'unverified' };
}

export function canonicalJid(value = '') {
  return String(value).trim().replace(/:\d+(?=@)/, '');
}

export function sameConversation(a, b, lidToPn = new Map()) {
  const identity = value => {
    const jid = canonicalJid(value);
    return jid.endsWith('@lid')
      ? `${lidToPn.get(jid) || lidToPn.get(jid.split('@')[0]) || jid}@identity`
      : jid.endsWith('@s.whatsapp.net') ? `${jid.split('@')[0]}@identity` : jid;
  };
  return Boolean(a && b) && identity(a) === identity(b);
}

export function validRecipient(jid) {
  return /^\d+@(?:s\.whatsapp\.net|lid)$/.test(jid) || /^\d+(?:-\d+)?@g\.us$/.test(jid);
}

export function tokenMatches(expected, supplied) {
  if (!expected || typeof supplied !== 'string') return false;
  const a = Buffer.from(expected), b = Buffer.from(supplied);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export function messageCacheKey(key) {
  if (!key?.id || !key.remoteJid) return null;
  return crypto.createHash('sha256').update(JSON.stringify([
    canonicalJid(key.remoteJid), key.id, Boolean(key.fromMe), key.fromMe ? '' : canonicalJid(key.participant)
  ])).digest('hex');
}

export function webhookAccepted(httpOK, body) {
  const result = body?.message || body;
  return httpOK && ['ok', 'queued', 'already_processed', 'ignored', 'rejected'].includes(result?.status);
}

export function retryKind(parameters = []) {
  const text = parameters.join(' ').toLowerCase();
  if (text.includes('absent from node')) return 'absent';
  if (text.includes('bad mac')) return 'bad_mac';
  if (text.includes('no session')) return 'missing_session';
  return 'undecrypted';
}

// Baileys 6.7.24 requests only one offline batch. A missing terminator can
// leave decoded messages/receipts buffered indefinitely on an open socket.
export function drainOfflineBatches(socket, {
  isCurrent = () => true, idleMs = 5000, maxRequests = 50,
  setTimer = setTimeout, clearTimer = clearTimeout, log = () => {}
} = {}) {
  let timer = null, active = false, disposed = false, requests = 0;
  const cancel = () => { if (timer !== null) clearTimer(timer); timer = null; };
  const arm = () => {
    cancel();
    if (!active || disposed || !isCurrent()) return;
    timer = setTimer(async () => {
      timer = null;
      if (!active || disposed || !isCurrent()) return;
      if (requests >= maxRequests) {
        active = false;
        log('error', `[OfflineDrain] Stopped at ${maxRequests} extra batches without completion`);
        return;
      }
      requests++;
      try {
        await socket.sendNode({ tag: 'ib', attrs: {}, content: [{ tag: 'offline_batch', attrs: { count: '100' } }] });
        log('info', `[OfflineDrain] Requested next existing-message batch ${requests}`);
        arm();
      } catch (err) {
        active = false;
        log('error', `[OfflineDrain] Batch request failed: ${err.message}`);
      }
    }, idleMs);
    timer?.unref?.();
  };
  const preview = () => { if (!disposed) { active = true; arm(); } };
  const complete = () => { active = false; cancel(); log('info', `[OfflineDrain] Server completed offline delivery after ${requests} extra batches`); };
  const activity = node => {
    if (active && ['1', 1, true].includes(node?.attrs?.offline)) arm();
  };
  socket.ws.on('CB:ib,,offline_preview', preview);
  socket.ws.on('CB:ib,,offline', complete);
  for (const event of ['CB:message', 'CB:receipt', 'CB:notification', 'CB:call']) socket.ws.on(event, activity);
  return () => {
    disposed = true; active = false; cancel();
    socket.ws.off?.('CB:ib,,offline_preview', preview);
    socket.ws.off?.('CB:ib,,offline', complete);
    for (const event of ['CB:message', 'CB:receipt', 'CB:notification', 'CB:call']) socket.ws.off?.(event, activity);
  };
}
