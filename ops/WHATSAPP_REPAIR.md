# WhatsApp repair and rollout — 2026-11-01

## Status

Real handset acceptance is pending. Do not label this release Production Ready.
No WhatsApp unlink, pairing reset, Signal key deletion, credential rotation, or financial test transaction is authorized by this release.

## Verified baseline

- Local/server repository baseline: `206a139`.
- PR #1 was reviewed, not merged. Its pairing/logout/healing guards, missing-secret failure, receipt-field fix, and accepted-send check were incorporated and extended.
- SSH host identity matched the previously saved ED25519 fingerprint `SHA256:n0cSc/K9xfK1sy0/5Ab6M52mRIIHisTRYJyl4C1dSXk` before password authentication.
- Production: Node 20.20.2, Baileys 6.7.24, Frappe 16.54.0, ERPNext 16.53.0.
- Running Baileys source and server Git HEAD source matched SHA256 `6dab781bb823f684c7492901ff3a64b7f74a52db83ce1275a5a69b050351227e`.
- Running Frappe bridge matched HEAD SHA256 `17d969e4b1e66aaeace423fa733c7a3298f5b63eaf86cae4e822a2aa21385a45`.
- Existing Baileys image: `sha256:5128b9039f9a77d540e142a598c324045a8fc1c959d1354516389eea1adcb261`. Checked source hashes in the running container against a fresh container: dependency files matched.
- API token is configured in the encrypted Hub Password field and Node environment; existing authenticated status request returned HTTP 200. Values were not printed.
- MariaDB query, both Redis PINGs, HTTPS redirect, two workers, and scheduler checks passed.
- Baileys binds to host loopback port 3001, shares `frappe_docker_default`, persists `/app/session`, and has `unless-stopped` policy. No configured Docker healthcheck existed.
- Resource snapshot: 68 GB available on root disk; approximately 5.7 GB available RAM; 2 GB configured swap was not assumed — actual swap was 8 GB with about 1.5 GB used.

## Findings and changes

1. Pairing and logged-out handlers deleted authentication; manual healing deleted live Signal files while a shared cache retained old state. All session destruction routes now reject; pairing rejects registered disconnected accounts. Each recreated socket gets a fresh Signal cache. Credential/key writes are tracked before reconnect/shutdown.
2. The retry cache used message ID alone and ordinary JSON. It now uses hashed chat/message/direction/participant keys and Baileys BufferJSON, writes atomically, and uses exact learned PN/LID aliases for retries. No fabricated quoted message is sent.
3. Inbound dedup ran before successful webhook delivery, HTTP errors were dropped, and receipt dispatch was unobserved. Events now persist in a disk outbox and remain until Frappe acknowledges admission. Both HTTP and application status are checked.
4. Frappe acknowledged/replied without checking a real outbound message ID. Replies now create distinct Outgoing records linked to the Incoming ID. Admission saves an Incoming record before enqueueing; workers serialize by ID. Received records can be re-enqueued; Processing/Failed records are never blindly replayed after an uncertain external send.
5. Receipt `status_code` was ignored; unknown statuses defaulted to Sent. Status 0 is Failed, 1 Pending, 2 Sent (server acknowledgement only), 3 Delivered, 4/5 Read. Updates are monotonic and apply only to the outbound ID. Early receipts are retained in Redis.
6. Partial phone/LID matching could authorize unrelated senders. Exact normalized equality is required. Group reply and mention rules are enforced; discovering a group no longer enables it. Accounting requires an explicitly authorized contact.
7. Multiple GUI read/control endpoints omitted Hub permission checks. Administrative pairing/QR/restart require System Manager; invoice export also checks invoice read access.
8. The legacy invoice sender retained another embedded token. All active WhatsApp paths now use the encrypted Hub token; missing configuration fails closed. Query-string authentication is removed. Provider keys are not put in Gemini URLs. Library console objects are reduced to diagnostic metadata to avoid dumping Signal secrets.
9. Inbox now sees bot replies as Outgoing rows, fetches the latest page in chronological order, supports group/LID identities and takeover, polls while visible, and renders delivery states separately. Untrusted contact names no longer enter inline JavaScript. Added filters and responsive RTL layout.
10. Logs/dashboard now surface transport, webhook and decrypt counters; diagnostic versions/storage state come from the running service. Unknown backup/restart information is shown as unverified, not invented.

## Runtime evidence and limits

A bounded 3,000-line pre-rollout log sample contained 311 structured decrypt errors with `fromMe=true` and 48 with `fromMe=false`; the last external error examples were status broadcasts. This supports separating companion synchronization/broadcast noise from direct-message failure. It does not prove direct messaging works. Ignored broadcast/newsletter JIDs are now excluded using the installed `shouldIgnoreJid` API before decryption.

Installed sources inspected: `Utils/use-multi-file-auth-state.js`, `Utils/auth-utils.js`, `Utils/decode-wa-message.js`, `Utils/event-buffer.js`, `Socket/messages-recv.js`, `Socket/messages-send.js`, `Signal/libsignal.js`. Baileys 6.7.24 has no v7 repository LID mapping API. Configured/observed exact mappings are used; optional newer APIs are feature-detected. The test phone/LID is never embedded in startup code.

The underlying multi-file store uses file locks but non-atomic `writeFile`; this change preserves it and tracks writes, rather than replacing a live authentication format. Native WhatsApp retry requests cannot recover every missing payload. Existing media metadata/captions are admitted, but full media download/preview is not implemented here.

## Tests

```powershell
node --test tests/wa-engine.test.mjs
python -m unittest discover -s tests -p 'test_*.py' -v
node --check wa-baileys-index.js
node --check hagag_erp/hagag_erp/doctype/elsaidy_whatsapp_hub/elsaidy_whatsapp_hub.js
python -m py_compile hagag_erp/whatsapp_bridge.py hagag_erp/api/whatsapp.py
git diff --check
```

Offline tests use controlled Frappe/HTTP/socket doubles; they do not substitute for the site integration or device checks. `tests/wa-installed.test.mjs` additionally runs against the unchanged production image with networking disabled and a temporary authentication directory; it verifies actual credential/key reloads and binary retry payload serialization. The image startup smoke test checks unauthenticated HTTP 401 and authenticated diagnostics HTTP 200 with Baileys 6.7.24. Missing-token startup rejection was also observed as expected.

## Mapping and rollout

| Repository source | Production target |
| --- | --- |
| `wa-baileys-index.js` | `/root/wa-baileys/index.js` → bind `/app/index.js` |
| `wa-safety.mjs` | `/root/wa-baileys/wa-safety.mjs` → new bind `/app/wa-safety.mjs:ro` |
| `hagag_erp/**` | `/root/frappe_docker/hagag-erp-repo/hagag_erp/**` → Frappe app bind |

Before rollout, code/config archive and verified gzip database backup were created:

- `/root/elsaidy-backups/wa-repair-20261101/code-config-before.tgz`, root-only permissions.
- Site database/config backup prefix: `20261101_160018-erp_local` in `sites/erp.local/private/backups`.

Rollout procedure: save current maintenance setting; enable maintenance; stop Baileys and workers/scheduler; archive the stopped session under the root-only backup directory; record authentication identity digest without exposing keys; check out the reviewed repair commit in the clean server repository; copy Node source/helper; add helper mount without rebuilding/upgrading dependencies; reload only the WhatsApp Log DocType and scheduler jobs; clear site cache; restart existing ERP services; recreate Baileys using the existing image without build; verify CONNECTED and identity digest; restore maintenance setting. Do not run accounting tests from the old project test scripts.

## Rollback

Stop message ingress and let current jobs finish before reverting Python methods referenced by queued jobs. Restore the code/config archive and previous Compose file, restore the old server Git branch, and recreate Baileys from the recorded existing image. Restart backend/workers/scheduler and clear cache. Added SQL columns can remain during code rollback; restoring the whole database is a disaster-recovery action, not routine code rollback, because it would discard subsequent records.

Never restore an old session backup merely to roll code back: Signal ratchets advance while running. Keep the current live session. Session snapshot restoration requires a separate reviewed recovery decision. New durable Processing/Failed rows require investigation rather than automatic resend. Existing historical reply rows have no recoverable outbound IDs and are not falsified or rewritten.

## Coordinated credential rotation (not executed)

Secrets shared in chat and the historical API-token fallback need a separate authorized rotation. Save encrypted backups and test the current deployment rollback first. During a short controlled ingress pause, set a newly generated value in Node's protected environment and the Frappe encrypted Password field, restart only the messaging service, verify both authenticated directions and rejection of the old value, then resume ingress. Keep recovery values in a secure credential store, never Git or this document. Rotate SSH/GitHub credentials separately with a tested replacement login before revoking the old access. No history rewrite is part of this repair.

## Physical-device acceptance

1. From the authorized Saudi handset, send a unique plain text phrase to the linked Egyptian bot; avoid expense/accounting language.
2. Match the real inbound message ID to one Incoming row and its conversation identity.
3. Confirm exactly one linked Outgoing ID, correct target, one reply bubble, and no extra reply after the outbox retries.
4. Require Delivered/Read receipt separately from Sent; the owner must confirm the reply on the physical Saudi handset.
5. Enable takeover, send another plain message, verify one Incoming row and no bot reply; test one manual reply, then disable takeover.
6. Perform one controlled reconnect without relinking, confirm same account identity, and repeat the plain-text exchange.
7. Check Inbox timestamps/filter/search and logs/diagnostic controls in an authenticated ERP browser. Inspect fresh decrypt errors by message ID; do not infer recovery from CONNECTED alone.
