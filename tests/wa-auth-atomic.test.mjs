import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
const require = createRequire('/app/package.json');
const { useMultiFileAuthState } = await import(require.resolve('@whiskeysockets/baileys'));

test('concurrent auth readers always see complete JSON during repeated credential writes', async () => {
  const directory = await fsp.mkdtemp(path.join(os.tmpdir(), 'wa-atomic-auth-'));
  let reading = true, invalid = 0, reads = 0;
  try {
    const { state, saveCreds } = await useMultiFileAuthState(directory);
    await saveCreds();
    const file = path.join(directory, 'creds.json');
    const reader = (async () => {
      while (reading) {
        try { JSON.parse(fs.readFileSync(file, 'utf8')); } catch { invalid++; }
        reads++; await new Promise(resolve => setImmediate(resolve));
      }
    })();
    state.creds.regressionPayload = 'x'.repeat(512 * 1024);
    for (let n = 0; n < 24; n++) { state.creds.regressionCounter = n; await saveCreds(); }
    reading = false; await reader;
    assert.ok(reads > 10);
    assert.equal(invalid, 0, `read ${invalid} empty or partial credential snapshots`);
    assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).regressionCounter, 23);
  } finally { reading = false; await fsp.rm(directory, { recursive: true, force: true }); }
});
