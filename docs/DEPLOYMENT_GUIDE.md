# Elsaidy ERP — Production Deployment & Rollback Guide
## دليل النشر الآمن وخطة التراجع — نظام الصعيدي للمقاولات

**Target Site:** `erp.local` (`https://erp.elsaidy.org`)  
**Target Architecture:** Docker Compose + Frappe v16 + ERPNext v16 + Python 3.14  
**Audience:** Lead Systems Engineer & DevOps  

---

## 1. احتياطات ما قبل النشر (Pre-Deployment Safety Checks)

قبل تنفيذ أي أمر ترحيل أو نشر على الإنتاج:
1. **التحقق من حالة الحاويات النشطة:**
   ```bash
   ssh ali "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
   ```
   تأكد من أن الحاويات التالية في حالة `Up`:
   - `frappe_docker-backend-1`
   - `frappe_docker-frontend-1`
   - `frappe_docker-db-1`
   - `wa-baileys` (منفذ 3001)

2. **أخذ نسخة احتياطية فورية وشاملة (Snapshot Backup):**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local backup --with-files"
   ```
   تحقق من ظهور ملف النسخة الاحتياطية في المسار:
   `/var/lib/docker/volumes/frappe_docker_sites/_data/erp.local/private/backups/`

3. **حماية جلسة واتساب ومنع إعادة التشغيل غير الضرورية:**
   - خدمة `wa-baileys` مستقلة بحاوية منفصلة ولا تتأثر بإعادة تشغيل تطبيق الباك إند.
   - يمنع تشغيل `docker restart wa-baileys` إلا في حال انقطاع الجلسة الفعلي.

---

## 2. تسلسل الدمج البرمجي الموصى به (PR Merge Sequence)

لتجنب أي تعارض في الملفات المشتركة (`setup.py` و `pyproject.toml`):

1. **دمج PR #6 أولاً (`feature/raven-safe-extension`):**
   - يلغي تعديل ملفات vendor raven على القرص.
   - يضيف ملحق الذاكرة `hagag_erp/raven_extension.py`.
   - يحتوي على حزمة اختبارات Raven الشاملة (8/8 نجاح).

2. **إعادة تأسيس (Rebase) ودمج PR #4 ثانياً (`feature/lavaloon-zatca-integration`):**
   - يدمج تكامل LavaLoon KSA compliance v0.62.0.
   - يضيف دالة احتساب مستخلصات المقاولات وحسم الدفعة المقدمة والضريبة.
   - يضيف صورة Dockerfile.zatca المدعومة بـ Java 11 JRE.
   - يحتوي على حزمة اختبارات الزكاة البحتة (8/8 نجاح).

---

## 3. خطوات النشر على خادم الإنتاج (Execution Commands)

عند استلام الاعتماد النهائي:

```bash
# خطوة 1: الدخول إلى مجلد المستودع وجلب أحدث النسخ
ssh ali "cd /root/frappe_docker/hagag-erp-repo && git fetch origin && git checkout main && git pull origin main"

# خطوة 2: تنفيذ ترحيل قاعدة البيانات بهدوء
ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local migrate"

# خطوة 3: بناء الأصول الثابتة لتطبيق المقاولات
ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench build --app hagag_erp"

# خطوة 4: مسح الذاكرة المؤقتة لموقع الإنتاج
ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local clear-cache"

# خطوة 5: إعادة تشغيل معالجات الطلبات والمهام الخلفية
ssh ali "docker restart frappe_docker-backend-1 frappe_docker-queue-short-1 frappe_docker-queue-long-1"
```

---

## 4. التحقق والتوثيق بعد النشر (Post-Deployment Verification)

1. **تشغيل فحص الأستاذ العام الحي (Read-Only GL Balance Check):**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local execute hagag_erp.custody_service.get_employee_live_gl_balance --args \"['HR-EMP-00001', 'ركن سبل الافق']\""
   ```
   يجب أن يعيد بالضبط: `posted_custody_balance: 2185.0`.

2. **تشغيل اختبارات القبول الشاملة على الإنتاج (23 فحصاً آمناً):**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local execute hagag_erp.test_production_acceptance_master.run_all_acceptance_tests"
   ```
   يجب أن تعيد: `23/23 PASSED (100%)`.

3. **التحقق من حالة واتساب:**
   ```bash
   ssh ali 'curl -s -H "Authorization: Bearer $(grep WA_API_TOKEN /root/wa-baileys/.env | cut -d= -f2)" http://localhost:3001/status'
   ```
   يجب أن يعيد: `"connected": true`.

---

## 5. خطة التراجع الآمنة عند الطوارئ (Safe Rollback Procedure)

> [!CAUTION]
> **تنبيه أمني هام:** يحظر تشغيل أمر `bench restore ... --force` بدون كلمة مرور root لقاعدة البيانات أو دون تفعيل وضع الصيانة. الاستعادة العشوائية تؤدي إلى إتلاف جلسات العمل ومسح مفتاح التشفير `encryption_key`. التزم بالخطوات الست التالية:

1. **تفعيل وضع الصيانة فوراً لإيقاف حركة المستخدمين:**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local set-maintenance-mode on"
   ```

2. **أخذ لقطة احتياطية طارئة للحالة الحالية قبل بدء التراجع:**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local backup --with-files"
   ```

3. **التحقق من سلامة ملف النسخة الاحتياطية المستهدفة (Integrity Check):**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 gzip -t /home/frappe/frappe-bench/sites/erp.local/private/backups/<backup_file>.sql.gz"
   ```

4. **تنفيذ الاستعادة الآمنة مع تمرير كلمة مرور root لقاعدة البيانات وخيارات ملفات النظام:**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local restore /home/frappe/frappe-bench/sites/erp.local/private/backups/<backup_file>.sql.gz --db-root-password SuperRootP@ss2026 --with-public-files /home/frappe/frappe-bench/sites/erp.local/private/backups/<backup_public_files>.tar --with-private-files /home/frappe/frappe-bench/sites/erp.local/private/backups/<backup_private_files>.tar --force"
   ```

5. **الرجوع لفرع أو وسم الكود المستقر السابق:**
   ```bash
   ssh ali "cd /root/frappe_docker/hagag-erp-repo && git checkout <stable_tag_or_commit>"
   ```

6. **تفريغ الكاش وإلغاء وضع الصيانة وإعادة تشغيل معالجات المهام:**
   ```bash
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local clear-cache"
   ssh ali "docker exec -w /home/frappe/frappe-bench/sites frappe_docker-backend-1 bench --site erp.local set-maintenance-mode off"
   ssh ali "docker restart frappe_docker-backend-1 frappe_docker-queue-short-1 frappe_docker-queue-long-1"
   ```
