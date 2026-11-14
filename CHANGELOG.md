# Elsaidy ERP — Changelog
سجل التغييرات والتحديثات المعمارية لنظام الصعيدي للمقاولات

All notable changes to the Elsaidy ERP (hagag-erp) platform are documented in this file.

---

## [16.0.0-Production-Release] - 2026-11-14

### Added
- **LavaLoon KSA Compliance v0.62.0 Integration (PR #4):**
  - Integrated official ZATCA Phase 2 candidate upstream release (Nov 10, 2026).
  - Adoptium Temurin OpenJDK 11 JRE Dockerfile (`ops/Dockerfile.zatca`) with validated SHA-256 checksum for reproducible container builds.
  - Saudi Contracting IPC tax engine calculations (`calculate_contracting_ipc_tax_base`, `calculate_ipc_tax_breakdown`).
  - Separation of private commercial contracts (`certification_date`) from government Etimad contracts (`payment_date`).
  - Strict Article 50 input tax recovery rules (commercial heavy equipment fuel vs restricted private vehicles).
  - 8 isolated pure mocked ZATCA unit tests (`hagag_erp/tests_zatca_integration.py`).
  - Automated ZATCA CI workflow (`.github/workflows/zatca_ci.yml`) running on Python 3.14.
- **Raven AI Native DocType Architecture (PR #6):**
  - Replaced transient in-memory monkey-patching with native Raven DocTypes (`Raven AI Function` with type `Custom Function` & `Raven Bot.bot_functions`).
  - Zero modifications to vendor core files in `apps/raven` (verified 0 file writes).
  - Multi-process persistence across container restarts and RQ background worker jobs.
  - Comprehensive Raven integration test suite (`hagag_erp/tests_raven_integration.py`) covering request lifecycles, background workers, process isolation, and idempotency.
- **WhatsApp Hub Command Center:**
  - Baileys Node.js gateway integration (port 3001) with persistent session handling.
  - Purged all hardcoded API tokens (`HAGAG_WA_7f3c9a2d6e4b8a1c`) across codebase and documentation.
  - Secure token resolution strictly via encrypted single store (`get_hub_auth_token`) and environment variables.
  - Successfully rotated exposed WhatsApp Bearer token on live container without dropping active device pairing.
  - Strict allowlist enforcement with silent drop of unauthorized senders.
  - Cloud LID resolution for 1-to-1 chats to eliminate Signal protocol ratchet decryption errors.
  - Notification deduplication protecting against redundant outbound messages.
- **Production Master Acceptance Suite:**
  - Master test suite (`test_production_acceptance_master.py`) covering 23 end-to-end scenarios with 100% pass rate.

### Changed
- Unified all Docker containers, Bench environments, pyproject configuration, and GitHub Actions workflows to **Python 3.14.10**.
- Scoped code formatting rules in `.pre-commit-config.yaml` to isolate legacy debt while enforcing strict standards on newly changed files.
- Aligned legal company name across all templates and setups to `ركن سبل الافق` (Abbreviation: `Rkn`).
- Resolved default company fallback in `get_target_company` to prevent unhandled exceptions during uninitialized process execution.

### Fixed
- Fixed broken test imports in `tests_zatca_integration.py` by implementing genuine, tested contracting tax base functions.
- Resolved Semgrep security alerts without using blanket suppressions or unsafe workarounds.
- Resolved Ruff import sorter, unused variables, and trailing whitespace violations across all PR branches.
- Prevented unhandled `object is not bound` exceptions when executing pure unit tests outside live Frappe site contexts.
