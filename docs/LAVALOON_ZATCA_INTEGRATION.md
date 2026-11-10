# LavaLoon KSA Compliance & ZATCA Phase 2 Integration Guide
## Elsaidy ERP (hagag_erp) & Elsaidy Contracting

### 1. Executive Summary & Upstream Release Pinning
- **Selected Upstream Package**: [LavaLoon KSA Compliance](https://github.com/lavaloon-eg/ksa_compliance)
- **Evaluated Release**: `0.62.0` (November 10, 2026)
- **Pinned Git Commit**: `39a3817e098e98066af2c1539d6ad6ed18ad0225`
- **Frappe / ERPNext Compatibility**: Native compatibility with Frappe v16 Desk (`frappe 16.54.0` / `erpnext 16.53.0`).
- **Core Policy**: Zero modifications to ERPNext, Frappe, Raven, or LavaLoon vendor core files.

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
   - Official ZATCA UBL 2.1 XML generation (Invoice, Credit Note, Debit Note).
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

### 4. Verification Differentiation & Compliance Requirements
- **Mock / Pure Unit Tests**: Pure mathematical and business logic tests (`tests_zatca_integration.py`) verify 15% VAT, Decimal rounding, Article 50 classification, and IPC reconciliation without any database mutations.
- **Local SDK / CLI Tests**: Verified Adoptium JRE 11 and ZATCA CLI 2.10.0 binary operations for CSR and key generation in persistent storage (`zatca-files/`).
- **Developer Portal HTTP Probe**: HTTP 200/401 checks only verify network handshake, TLS connection, and routing. **They do not constitute official compliance or invoice clearance.**
- **Official Compliance & Clearance Readiness**: Requires genuine credentials from the ZATCA Fatoora Portal:
  1. Complete company legal registration (15-digit Tax ID, 10-digit CR, 4-digit Building No, 5-digit Postal Code, District).
  2. Owner-generated OTP from ZATCA Fatoora Portal.
  3. Generating Compliance CSID via `POST /compliance`.
  4. Successful submission and validation of 6 required compliance checks.
  5. Issuance of Production CSID for live B2B clearance and B2C reporting.

---

### 5. Environment Isolation & Staging Architecture Clarification
> **⚠️ Critical Architecture Note**:
> The test site `zatca-fresh.local` (and `erp_test.local`) is a multi-tenant Frappe site created inside the existing Frappe bench to test schema creation, patch execution, and app installation.
> **It is NOT a completely isolated Docker staging stack.** It shares container networking, redis instances, and database daemon resources with the bench host.
>
> **Mandatory Pre-Production Requirement**:
> Prior to executing deployment on the live production site (`erp.local`), a full dry-run deployment must be executed on a dedicated, completely isolated Docker staging stack (independent MariaDB daemon, Redis containers, and isolated volumes) to guarantee zero interference with production services.

---

### 6. Reproducible Version-Pinned Docker Deployment Pipeline
**STRICT POLICY: Never use manual `pip install` or direct git cloning inside live running production containers.**
All production deployments must follow an immutable, version-pinned container build workflow:

1. **Pinned Source Manifest (`zatca_dependencies.json`)**:
   - `ksa_compliance`: Git commit `39a3817e098e98066af2c1539d6ad6ed18ad0225` (Release 0.62.0).
   - Java JRE: Adoptium OpenJDK 11 Headless.
   - ZATCA CLI: Version 2.10.0.

2. **Reproducible Container Build (`Dockerfile.zatca`)**:
   ```dockerfile
   FROM frappe/erpnext:v16.53.0
   USER root
   RUN apt-get update && apt-get install -y --no-install-recommends \
       openjdk-11-jre-headless \
       && rm -rf /var/lib/apt/lists/*
   USER frappe
   # Clone and install pinned LavaLoon KSA Compliance
   RUN git clone https://github.com/lavaloon-eg/ksa_compliance.git /home/frappe/frappe-bench/apps/ksa_compliance \
       && cd /home/frappe/frappe-bench/apps/ksa_compliance \
       && git checkout 39a3817e098e98066af2c1539d6ad6ed18ad0225 \
       && /home/frappe/frappe-bench/env/bin/pip install -e /home/frappe/frappe-bench/apps/ksa_compliance
   ```

3. **Deterministic Staged Rollout**:
   - Build image: `docker build -f Dockerfile.zatca -t registry.elsaidy.org/elsaidy-erp:zatca-v0.62.0 .`
   - Update `docker-compose.yml` image tag to `registry.elsaidy.org/elsaidy-erp:zatca-v0.62.0`.
   - Execute migrations via CI/CD deployment runner: `bench --site <site> migrate`.
   - Preserve `zatca-files/` volume for cryptographic keys and certificates.
