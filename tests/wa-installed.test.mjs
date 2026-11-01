// Run inside an isolated container built from the existing production image, network disabled.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
const require = createRequire('/app/package.json');
const baileys = await import(require.resolve('@whiskeysockets/baileys'));
const { default: NodeCache } = await import(require.resolve('node-cache'));
const logger = { trace() {}, debug() {}, info() {}, warn() {}, error() {} };

test('installed dependency exports required APIs and preserves credentials and keys across reloads', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'wa-auth-test-'));
  try {
    assert.equal(typeof baileys.makeWASocket, 'function');
    const first = await baileys.useMultiFileAuthState(directory);
    const identity = Buffer.from(first.state.creds.signedIdentityKey.public);
    await first.saveCreds();
    const store = baileys.makeCacheableSignalKeyStore(first.state.keys, logger, new NodeCache({ useClones: false }));
    await store.set({ session: { 'test-only.0': Buffer.from([1, 2, 3]) } });
    const second = await baileys.useMultiFileAuthState(directory);
    assert.deepEqual(Buffer.from(second.state.creds.signedIdentityKey.public), identity);
    assert.deepEqual(Buffer.from((await second.state.keys.get('session', ['test-only.0']))['test-only.0']), Buffer.from([1, 2, 3]));
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});

test('installed BufferJSON round-trips retry media keys', () => {
  const message = { imageMessage: { mediaKey: new Uint8Array([1, 3, 5]), fileSha256: Buffer.from([2, 4]) } };
  const decoded = JSON.parse(JSON.stringify(message, baileys.BufferJSON.replacer), baileys.BufferJSON.reviver);
  assert.deepEqual(Buffer.from(decoded.imageMessage.mediaKey), Buffer.from([1, 3, 5]));
  assert.deepEqual(Buffer.from(decoded.imageMessage.fileSha256), Buffer.from([2, 4]));
});
