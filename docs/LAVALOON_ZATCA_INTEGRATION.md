# LavaLoon KSA Compliance & ZATCA Phase 2 Integration Guide
## Elsaidy ERP (hagag_erp) & Elsaidy Contracting

### 1. Executive Summary & Upstream Release Pinning
- **Selected Upstream Package**: [LavaLoon KSA Compliance](https://github.com/lavaloon-eg/ksa_compliance)
- **Evaluated Release**: `0.62.0` (November 10, 2026)
- **Pinned Git Commit**: `39a3817e098e98066af2c1539d6ad6ed18ad0225`
- **Frappe / ERPNext Compatibility**: Native compatibility with Frappe v16 Desk (`frappe 16.54.0` / `erpnext 16.53.0`).
- **Core Policy**: Zero modifications to ERPNext, Frappe, Raven, or LavaLoon vendor core files.
- **Pull Request**: [#4](https://github.com/AliAhmedElseidy/hagag-erp/pull/4) (`feature/lavaloon-zatca-integration` → `main`).

---

### 2. Upstream Migration & Fresh Install Root Cause Analysis
During initial evaluations, a migration failure occurred where Frappe attempted to execute historical patch `_2024_08_19_update_old_fatoora_url_in_business_settings.py` on a modern schema without `fatoora_server_url`.

**Root Cause Determined:**
1. Under normal Frappe architecture, `bench install-app` syncs DocTypes from JSON and then calls `set_all_patches_as_completed(app)`, marking all historical patches as completed so they never execute on fresh installs.
2. In earlier builds of `hagag_erp`, `Elsaidy WhatsApp Hub` had a hardcoded `"default": "..."` on the Link field `default_company`. During `install-app`, Frappe's `init_singles()` executed `_validate_links()` before companies were created, throwing a `LinkValidationError`.
3. This interrupted `install_app` midway before `set_all_patches_as_completed` could execute. Subsequent `bench migrate` runs then tried to execute historical 2024 patches on a 2026 schema.
4. **Permanent Engineering Resolution:**
   - Removed hardcoded default on `default_company` in `elsaidy_whatsapp_hub.json`.
   - No `ALTER TABLE` or artificial `tabPatch Log` spoofing is used.
   - Verified via fresh installation from zero on `zatca-fresh.local`: `install-app ksa_compliance` and subsequent `bench migrate` execute 100% cleanly without errors.

---

### 3. Architectural Division of Responsibilities
1. **LavaLoon KSA Compliance (`ksa_compliance`) Owns**:
   - Official ZATCA UBL 2.1 XML generation (Standard Invoice, Simplified Invoice, Credit Note, Debit Note).
   - Digital cryptographic ECDSA signing via ZATCA CLI 2.10.0.
   - Simplified tax invoice (B2C) QR code encoding (TLV format with ECDSA signature).
   - Direct API clearance (B2B) and compliance reporting (B2C) to ZATCA Fatoora Portal.
   - Official ZATCA Phase 2 Print Formats (`ZATCA Phase 1 Print Format` & `ZATCA Phase 2 Print Format`).
   - Cryptographic key pair, CSR generation, and CSID certificate storage.

2. **Hagag ERP (`hagag_erp`) Owns**:
   - Contracting IPC calculation engine: Gross Work Done, Retention deduction (e.g. 10%), Advance Recovery deduction.
   - Saudi Contracting IPC Print Format (`شهادة مستخلص أعمال مقاولات معتمد - IPC`).
   - Article 50 Input Tax audit and expense review on Purchase Invoices and Journal Entries.
   - Automated WhatsApp dispatch for approved customer documents.

---

### 4. Real ZATCA Storage Architecture & Security Permissions
According to LavaLoon's upstream implementation in `ksa_compliance/zatca_files.py`:
- `get_zatca_file_path()` resolves to: `frappe.get_site_path('zatca-files')` (`sites/<site>/zatca-files`).
- `get_zatca_tool_path()` resolves to: `frappe.get_site_path('zatca-tools')` (`sites/<site>/zatca-tools`).

#### Directory & Key Permission Standards:
| Path | Recommended Permission | Owner:Group | Purpose |
| :--- | :---: | :---: | :--- |
| `sites/<site>/zatca-files` | `0700` (`drwx------`) | `frappe:frappe` | Root directory for certificates, keys, and CSRs |
| `sites/<site>/zatca-files/*.privkey` | `0600` (`-rw-------`) | `frappe:frappe` | Private ECDSA keys (strictly non-world-readable) |
| `sites/<site>/zatca-files/*.cert` | `0644` (`-rw-r--r--`) | `frappe:frappe` | CSID Public Certificates |
| `sites/<site>/zatca-tools` | `0750` (`drwxr-x---`) | `frappe:frappe` | ZATCA CLI binaries and configuration scripts |

#### Persistence Verification Across Container Recreation:
Tested and verified on clean container stacks using independent Docker volumes:
1. Container 1 initializes `zatca-files` (0700) and writes `private_key.pem` (0600).
2. Container 1 is destroyed (`--rm`).
3. Container 2 starts from the image with the same volume attached.
4. Permissions and key payloads persist with 100% integrity without data loss or permission alteration.

---

### 5. Docker Reproducibility & Java 11 Verification
To eliminate local machine dependencies and prevent environmental drift:

1. **Pinned Upstream Base Image by Digest**:
   `frappe/erpnext:v16.53.0@sha256:b961d69ed3265f44f712f40be58a3e6a22c8662f61a7e1a8097765534e3e9be2`
   (Guarantees zero reliance on local `custom:47` artifacts).

2. **Strict Java 11 JRE Requirement**:
   - Debian 12 (Bookworm) and Debian 13 (Trixie) default packages map `default-jre-headless` to **OpenJDK 17**.
   - ZATCA CLI 2.10.0 strictly requires **Java 11**; running on Java 17 produces cryptographic signature and XML canonicalization discrepancies.
   - **Solution**: Explicitly installs Adoptium Eclipse Temurin OpenJDK 11.0.25+9 JRE in `/opt/java/temurin-11` and symlinks to `/usr/local/bin/java`. Verified via `java -version`:
     `openjdk version "11.0.25" 2024-10-15`
     `OpenJDK Runtime Environment Temurin-11.0.25+9`

3. **Asset Compilation & App Registration**:
   `bench build --app ksa_compliance --app hagag_erp` compiles all frontend bundles at image build time without runtime overhead.

---

### 6. Linter & Code Quality Standards
- **PR Scope Isolation**: All new and modified integration files (`tests_zatca_integration.py`, `tax_engine.py`, `ops/Dockerfile.zatca`) strictly conform to Frappe tab indentation standards and PEP 8 / Ruff linting rules.
- **Legacy Technical Debt Isolation**:
  - Run `42925673248` failed due to legacy repository formatting issues in `wa-baileys-index.js` (Prettier quote rules in `.pre-commit-config.yaml`).
  - To prevent destabilizing the production WhatsApp/Baileys microservice, legacy files were not arbitrarily reformatted.
  - Documented in detail in GitHub Issue: [#5 - Track legacy formatting debt in wa-baileys-index.js](https://github.com/AliAhmedElseidy/hagag-erp/issues/5).

---

### 7. Verification Differentiation & Compliance Requirements
- **Mock / Pure Unit Tests**: Pure mathematical and business logic tests (`tests_zatca_integration.py`) verify 15% VAT, Decimal rounding, Article 50 classification, and IPC reconciliation without any database mutations.
- **Local SDK / CLI Tests**: Verified Adoptium JRE 11 and ZATCA CLI 2.10.0 binary operations for CSR and key generation in persistent storage (`sites/<site>/zatca-files/`).
- **Developer Portal HTTP Probe**: HTTP 200/401 checks only verify network handshake, TLS connection, and routing. **They do not constitute official compliance or invoice clearance.**
- **Official Compliance & Clearance Readiness**: Requires genuine credentials from the ZATCA Fatoora Portal:
  1. Complete company legal registration (15-digit Tax ID, 10-digit CR, 4-digit Building No, 5-digit Postal Code, District).
  2. Owner-generated OTP from ZATCA Fatoora Portal.
  3. Generating Compliance CSID via `POST /compliance`.
  4. Successful submission and validation of 6 required compliance checks.
  5. Issuance of Production CSID for live B2B clearance and B2C reporting.

---

### 8. Environment Isolation & Staging Architecture Clarification
> **⚠️ Critical Architecture Note**:
> The test site `zatca-fresh.local` (and `erp_test.local`) is a multi-tenant Frappe site created inside the existing Frappe bench to test schema creation, patch execution, and app installation.
> **It is NOT a completely isolated Docker staging stack.** It shares container networking, redis instances, and database daemon resources with the bench host.
>
> **Mandatory Pre-Production Requirement**:
> Prior to executing deployment on the live production site (`erp.local`), a full dry-run deployment must be executed on a dedicated, completely isolated Docker staging stack (independent MariaDB daemon, Redis containers, and isolated volumes) to guarantee zero interference with production services.
