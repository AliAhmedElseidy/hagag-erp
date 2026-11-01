# Investigation of the existing failed WA-1101-A test

The owner reported sending `اختبار الصعيدي WA-1101-A` after approximately 16:49 Riyadh (13:49 UTC), 2026-11-01, with no reply. Handset delivery marks are unknown. Do not infer that WhatsApp delivered it to the bot.

## Evidence

- Searched the surviving production container logs starting before 13:49 UTC, plus the full current session message cache, durable webhook outbox and Frappe message records. Neither the phrase nor a received message ID from the authorized PN/LID was found. The test's database status is **absent**, not Failed or Ignored. No linked outgoing reply exists.
- API authorization settings: the Saudi contact remains active; `auto_reply_enabled=1`; no pre-existing phone/LID takeover. Both Frappe workers were idle, all short/default/long queues were empty, and their failed-job registries contained zero jobs.
- The live installed `onWhatsApp()` query confirmed the configured Saudi PN/LID; the bot's live blocklist did not contain that peer.
- Outgoing `3EB035B53DB2630FF0381A` is cached as an outbound text to the configured LID. The original send API returned `status=ok`, native status 1. Its separate database record is Pending, with no receipt in Redis, the durable outbox, the event buffer or surviving logs. There is no evidence of handset delivery; do not upgrade its state or automatically resend it.
- A read-only runtime probe found an initial CONNECTED socket with `buffering=false` and an empty event buffer, ruling out an always-held event buffer as a proven explanation for the original test.
- An inspector-cleanup expression in the diagnostic tool raised `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING` and caused one unintended service restart. The unchanged auth identity was retained. The tool was corrected; no session/key file was deleted or replaced. This is a diagnostic incident, not evidence of the original message failure.
- On the subsequent connection, the installed Baileys 6.7.24 buffer demonstrably held 104 upserts without an offline completion. Requesting the next existing-message batches released the backlog (104 → 48 → 0). None contained the acceptance phrase/peer. Subsequent raw metadata monitoring received live traffic but no target node, upsert or receipt. These operations sent no new test message.

## Narrow repair candidate — withdrawn after live regression

Baileys 6.7.24 sends only one `offline_batch count=100` on `offline_preview`. A bounded continuation was tested and deployed temporarily to request the next batch after idle. It completed the actual offline batch, but exposed a transport fault: CPU was approximately 118%, HTTP health requests exceeded five seconds, and connections closed with 428/408 and reconnected. It did not recover the acceptance message. The candidate was withdrawn and the prior production code restored, preserving the current auth store. The same CPU/HTTP fault persisted after rollback, so paging is not established as its cause. The proposed source/test diff is retained in `ops/offline-paging-candidate.patch` for review, not enabled in production (zero-context archival diff).

Regression tests cover incomplete batches, live/offline-zero traffic, socket replacement, request limits, transport failure, and release of 104 buffered upserts using the actual installed event-buffer implementation in an isolated production-image container.

Upstream context: [Baileys issue 2810](https://github.com/WhiskeySockets/Baileys/issues/2810). Runtime measurements above, rather than the issue alone, justify the narrow repair.

## Verified Signal queue starvation

After rollback, live V8 CPU stack snapshots repeatedly stopped in `libsignal/src/session_cipher.js:fillMessageKeys` / `crypto.calculateMAC`. A scalar-only pause captured a requested counter of 1114 against a stored counter of 10. No key material was inspected or printed. The `libsignal@6.0.0` queue resolves and starts successive jobs through microtasks without giving network I/O a turn. A regression test against the original installed queue reproduced starvation of a network heartbeat during a burst of crypto jobs, while preserving task order.

The pinned fairness patch yields through `setImmediate` only after each complete Signal job, keeping per-device FIFO, return values, rejection behavior and completed persistence unchanged. It changes no cryptographic operation, retry counter limit, key, ratchet or auth format. The same regression passes with the patched actual dependency; 18 targeted engine/dependency/queue tests pass in an isolated production-image container. The patch generator refuses any original queue SHA256 other than the audited `d581518bab0da98ddc71cd6616bab769e0de413ec007454b7d42804ee3f244f3`.

## Verified non-atomic auth persistence failure

The live `session/creds.json` was observed at zero bytes, first during active writes and later persistently after an automatic process restart at 14:37 UTC. The unmodified auth store treats unreadable credentials as absent and generated QR codes, despite the linked device still having an existing identity. No QR was scanned and no unlink/reset was requested. The stopped-session snapshot from before the paging candidate contains a valid 1878-byte credential record whose registration/identity/noise digest exactly matches the original device-13 digest.

The repair restores only that same credential record into the zero-byte file, not the session directory or any Signal ratchet/session key files. A valid current credential file is never overwritten. Persistence is patched at the audited Baileys auth-store writer to write a private temporary file, fsync/close it, then atomically rename under the existing per-file mutex. The application also fails closed on empty/malformed existing credentials instead of creating a replacement socket/identity.

The original installed writer's regression produced 148 empty/partial snapshots during 24 credential writes in an isolated test. The patched writer produced zero, and the empty-file startup guard refused to create a socket. All 20 focused engine, installed-dependency, queue and auth-persistence tests pass with the exact production-image dependencies and both pinned patches. The auth module's required original SHA256 is `39de093873dc675fa453a63636189daa65ec8cf4a5b02eac46001b454f86f8ac`.

Deployment uses read-only binds for the generated `libsignal-queue-job.js` and `wa-auth-state.js` with the existing image, backing up Compose and both original modules. Code rollback removes these binds/restores `compose-before-signal-fairness.yml` and recreates only Baileys, keeping the current valid credentials and Signal files; never restore the zero-byte file. Remove/review these version-specific overrides before any dependency upgrade. Live responsiveness and original-message recovery must be checked independently; regression tests alone are not proof of handset delivery or the origin of this particular message's absence.

## Safety and conclusion

During existing-backlog inspection a temporary, uniquely marked takeover was applied only to the sole authorized test contact, preventing automated replies and accounting execution. It must be removed after recovery, without changing a takeover set independently by the owner.

The original acceptance message has not been recovered. Its last observable failed stage is before the application's inbound handler/admission. The underlying reason that WhatsApp did not expose this particular message remains unproven. The offline-drain defect is verified but its repair candidate was withdrawn; it must not be reported as the proven cause or as successful acceptance of WA-1101-A. Do not request another handset test or send repeated outbound test messages during this investigation.


## Verified retry cache mismatch & companion session invalidation (2026-11-01 continuation)

### 1. Verified Defect: Outbound Retry Cache Key Asymmetry
- **Evidence:** Runtime logs during live sending of messages `3EB0EF497B8719C8778004` and `3EB0387F3733604B5BBBFD` to `88949594783992@lid` recorded immediate peer retry requests that failed with:
  `[GetMessage] Message <id> requested for retry but not found in cache`
  despite both messages existing on disk in `/app/session/message_cache/`.
- **Root Cause:** Outbound messages are stored with `key.fromMe = true` and `key.participant = undefined`. When a peer handset receives ciphertext it cannot immediately decrypt, it transmits a retry receipt. In Baileys `messages-recv.js:handleReceipt`, because `attrs.recipient` is set in multi-device direct messages and `attrs.from` is the peer, Baileys sets `key.fromMe = false` and `key.participant = peerJid`. Passing this `key` into `messageCacheKey()` yielded a completely different SHA256 digest, so `fetchStoredMessage(key)` looked for a non-existent cache file.
- **Consequences:**
  1. `getMessage` returned `undefined`.
  2. Baileys `sendMessagesAgain` invoked `assertSessions([participant], true)`, force-closing the established Signal ratchet session (`Closing session: SessionEntry`) without retransmitting the message.
  3. The recipient handset remained stuck on *"Waiting for this message. This may take a while"*.
  4. The outbound message remained stuck in `Pending` status in MariaDB / ERPNext.
- **Repair Applied:**
  `fetchRetryMessage(key, socket)` now evaluates:
  1. Exact requested key.
  2. Inverse direction (`fromMe: !key.fromMe`, participant stripped) to match outbound storage.
  3. Alternate JID (LID <-> PN) in both directions.
  4. Fallback lookup by message ID (`id_${key.id}.json` and memory index).
- **Verification:** Unit test added in `tests/wa-engine.test.mjs` confirming peer retry receipts with `fromMe=false` and participant properly resolve stored outbound messages across LID, PN, and ID fallback. All 16 engine tests, 21 node tests, and 18 python tests pass.

### 2. Live Runtime Status: Companion Device Revocation (`401 location="rva"`)
- At 2026-11-01T15:18:33.618Z (18:18 Riyadh), after the repeated unhandled retry requests, WhatsApp server terminated the stream: `[ERROR] stream errored out`.
- On reconnection attempts, WhatsApp's authentication server returned:
  `{"message":"Connection Failure", "data":{"reason":"401", "location":"rva"}}`.
- Physical credentials in `/root/wa-baileys/session/creds.json` remain intact (1,878 bytes, identity digest `8430f806c972...` matches `auth-identity-before.sha256`), but WhatsApp's server (RVA = Registration/Validation/Auth) has revoked device 13.
- In accordance with safety rules, no session files were wiped or destroyed.
- Real physical message reception requires re-linking the Egyptian WhatsApp account (`+201028632620`) to obtain a fresh companion registration from WhatsApp.

### 3. Cross-Conversation Disclosure Remediation & Fresh QR Pairing (2026-11-01 Final Stage)
- **Security Defect Removed:**
  The un-scoped fallback `id_${key.id}.json` and `messageStore.get('id:' + key.id)` introduced in commit `cb925c0` could allow a peer requesting a known message ID to retrieve message contents belonging to an unrelated conversation.
- **Strict Scoping Applied:**
  1. `storeMessage`: All writes to `id:${msgId}` and `id_${msgId}.json` were completely removed. Messages are cached exclusively under keyed conversation hashes.
  2. `fetchRetryMessage`: Evaluates candidate JIDs strictly belonging to the verified conversation (`reqJid` and trusted bidirectional LID/PN aliases).
  3. Every candidate is strictly validated using `sameConversation(reqJid, candidate.key.remoteJid, lidPnMap)` and ID equality before returning.
  4. Negative & positive regression tests added to `tests/wa-engine.test.mjs`, proving cross-conversation disclosure is strictly blocked across PN, LID, and unknown third parties.
  5. Purged any legacy un-scoped `id_*.json` cache files.
- **Session Archive & Fresh QR Generation:**
  - Owner confirmed that the old device companion registration was intentionally unlinked from the Egyptian handset.
  - The old session directory was safely archived to `/root/elsaidy-backups/session-unlinked-archive-20261101_2318/` (sha256 `ee94f4ac9818...`).
  - Old Signal ratchets were strictly excluded from the new session.
  - A clean session directory was initialized with permissions `0700`.
  - Baileys initialized cleanly with WA Version `2.3000.1043857760` and generated a fresh QR code for the Egyptian WhatsApp bot handset (`+201028632620`).
  - Verified live QR availability via Baileys internal API `/qr` and ERPNext backend `hagag_erp.whatsapp_bridge.get_qr_code_internal`.

