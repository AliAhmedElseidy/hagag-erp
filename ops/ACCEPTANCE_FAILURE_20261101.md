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

Deployment uses a read-only bind for the generated `libsignal-queue-job.js` and the existing image, with the Compose file and original queue backed up. Rollback removes that bind/restores `compose-before-signal-fairness.yml` and recreates only Baileys, keeping the current session. Remove/review this version-specific override before any dependency upgrade. Live responsiveness and original-message recovery must be checked independently; the queue regression alone is not proof of handset delivery or the origin of this particular message's absence.

## Safety and conclusion

During existing-backlog inspection a temporary, uniquely marked takeover was applied only to the sole authorized test contact, preventing automated replies and accounting execution. It must be removed after recovery, without changing a takeover set independently by the owner.

The original acceptance message has not been recovered. Its last observable failed stage is before the application's inbound handler/admission. The underlying reason that WhatsApp did not expose this particular message remains unproven. The offline-drain defect is verified but its repair candidate was withdrawn; it must not be reported as the proven cause or as successful acceptance of WA-1101-A. Do not request another handset test or send repeated outbound test messages during this investigation.
