# WeighCert — Comprehensive Project Technical Report

> **Document Type:** Project Technical Report  
> **Application:** WeighCert — Legal Metrology Digital Certificate System  
> **Standard:** OIML R 76-1:2006 (Non-automatic Weighing Instruments)  
> **Prepared:** 2026  
> **Status:** Complete  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Project Structure & Folder Layout](#3-project-structure--folder-layout)
4. [Database Schema](#4-database-schema)
5. [User Roles & Authentication](#5-user-roles--authentication)
6. [Password Hashing Mechanism](#6-password-hashing-mechanism)
7. [Login Security & Account Lockout](#7-login-security--account-lockout)
8. [Application Flow (End-to-End)](#8-application-flow-end-to-end)
9. [The 7-Step Inspection Wizard](#9-the-7-step-inspection-wizard)
10. [OIML Rules Engine](#10-oiml-rules-engine)
11. [Report Numbering System](#11-report-numbering-system)
12. [PDF Generation](#12-pdf-generation)
13. [QR Code Generation](#13-qr-code-generation)
14. [Cryptographic Verification & Tamper Detection](#14-cryptographic-verification--tamper-detection)
15. [Audit Log Chain](#15-audit-log-chain)
16. [Template Inheritance & Structure](#16-template-inheritance--structure)
17. [UI, Accessibility & Theme System](#17-ui-accessibility--theme-system)
18. [Demo Credentials & Seed Data](#18-demo-credentials--seed-data)
19. [Golden Test Results](#19-golden-test-results)
20. [Known Limitations & Future Work](#20-known-limitations--future-work)

---

## 1. Project Overview

**WeighCert** is a government-grade web application for the **Directorate of Legal Metrology**, designed to digitise the entire lifecycle of non-automatic weighing instrument verification certificates — from instrument registration through field inspection to cryptographically signed, publicly verifiable PDF certificates.

### Context

Under the Legal Metrology Act (India), every commercial weighing instrument must be periodically inspected by an authorised Inspector. If compliant, a certificate (stamped form) is issued. WeighCert replaces the paper-based process with:

- Digital inspection workflows following **OIML R 76-1:2006** (the international standard for non-automatic weighing instruments)
- Role-based access for Inspectors, Approving Officers, and Administrators
- Cryptographically tamper-evident certificates with QR codes for public verification
- Automatic report numbering, PDF generation, and an immutable MongoDB audit trail

### Key Numbers at a Glance

| Item | Value |
|------|-------|
| Django apps | 5 (`accounts`, `core`, `registry`, `inspections`, `reports`) |
| Total DB tables | ~25 SQLite + 2 MongoDB collections |
| Pages / URL endpoints | 11 primary pages |
| OIML accuracy classes supported | C3, C5, D1 (expandable) |
| Max test weights per session | Unlimited (per OIML load schedule) |
| Hash algorithm for certificates | SHA-256 |
| Hash iterations for passwords | 1,200,000 (PBKDF2-SHA256) |
| Automated test cases | 43 (all passing) |

---

## 2. Technology Stack

### Backend

| Component | Technology | Version / Notes |
|-----------|-----------|----------------|
| Web framework | **Django** | 4.x |
| Language | **Python** | 3.14.4 |
| Primary database | **SQLite** | via Django ORM (`db.sqlite3`) |
| Audit / snapshot store | **MongoDB** | 8.2.3 (`pymongo` driver) |
| MongoDB driver | **pymongo** | Synchronous, `MongoClient` |
| Decimal arithmetic | Python `decimal.Decimal` | Never floats — prevents rounding errors in legal calculations |
| PDF (Linux) | **WeasyPrint** | Requires GTK3 (`libgobject-2.0-0`) |
| PDF (Windows fallback) | **xhtml2pdf** | Active on Windows dev environment |
| QR code | **qrcode** | Outputs base64 PNG for embedding in HTML/PDF |
| Password hashing | **Django PBKDF2PasswordHasher** | Wraps `hashlib.pbkdf2_hmac` |
| Testing | **pytest** + `pytest-django` | 43 golden tests |

### Frontend

| Component | Technology | Notes |
|-----------|-----------|-------|
| CSS framework | **Tailwind CSS** | Loaded from CDN (no build step) |
| Dynamic UI | **HTMX** | Partial page updates (no full-page reload) |
| Charts | **Chart.js** | Accuracy distribution on dashboard |
| Icons | **Material Symbols Outlined** | Google Fonts CDN |
| Fonts | **Noto Sans + JetBrains Mono** | Google Fonts CDN |
| Templating | Django templates | Server-side rendering |

---

## 3. Project Structure & Folder Layout

```
nawi/                               ← Repository root
├── PROJECT_REPORT.md               ← This report
└── weighcert/                      ← Django project root
    ├── manage.py
    ├── db.sqlite3                  ← SQLite primary database
    ├── config/                     ← Django project config package
    │   ├── settings.py             ← Settings (databases, apps, middleware, auth)
    │   ├── urls.py                 ← Root URL dispatcher
    │   └── wsgi.py / asgi.py
    │
    ├── accounts/                   ← Authentication & user management app
    │   ├── models.py               ← Profile (role, designation), LoginAttempt
    │   ├── views.py                ← login, logout, change_password, user CRUD
    │   ├── decorators.py           ← role_required, inspector/officer/admin_required
    │   ├── middleware.py           ← LoginAttemptMiddleware (lockout enforcement)
    │   ├── admin.py
    │   └── urls.py
    │
    ├── core/                       ← Shared utilities, settings, numbering
    │   ├── models.py               ← LabSettings, RuleSet, ClassLimit, MpeBand,
    │   │                               MultiIntervalCondition
    │   ├── audit.py                ← Hash-chained MongoDB audit log
    │   ├── numbering.py            ← Atomic sequential report number generator
    │   ├── views.py                ← Dashboard, settings pages
    │   └── templatetags/
    │       ├── __init__.py
    │       └── weighcert_tags.py   ← Custom template filter: format_mass
    │
    ├── registry/                   ← Instrument & owner registry app
    │   ├── models.py               ← Owner, Instrument, InstrumentRange, TestWeight
    │   ├── views.py                ← CRUD for instruments and owners
    │   └── urls.py
    │
    ├── inspections/                ← 7-step wizard and all test session models
    │   ├── models.py               ← TestSession, SessionWeight, ZeroCheck,
    │   │                               AccuracyReading, TareCheck,
    │   │                               RepeatabilityTest/Reading,
    │   │                               EccentricityTest/Reading,
    │   │                               DiscriminationReading, SensitivityReading,
    │   │                               TiltCheck
    │   ├── views.py                ← Wizard step views, submission, approval
    │   └── urls.py
    │
    ├── rules/                      ← Pure-Python OIML R 76-1 rules engine
    │   ├── engine.py               ← All calculation functions (no DB access)
    │   └── tests_golden.py         ← 43 golden test cases
    │
    ├── reports/                    ← Certificate PDF, verification, QR
    │   ├── models.py               ← Report model (number, hash, token, PDF path)
    │   ├── pdf.py                  ← WeasyPrint / xhtml2pdf dispatcher
    │   ├── snapshot.py             ← Canonical JSON + SHA-256 + MongoDB sync
    │   ├── qr_utils.py             ← qrcode → base64 PNG generator
    │   ├── views.py                ← Download PDF, public verify page
    │   └── urls.py
    │
    └── templates/                  ← All HTML templates
        ├── base.html               ← Master layout (sidebar, accessibility strip)
        ├── accounts/               ← login.html, change_password.html, users/
        ├── core/                   ← dashboard.html, settings pages
        ├── registry/               ← instrument_list.html, instrument_form.html, …
        ├── inspections/            ← wizard steps (step1.html … step7.html)
        │   └── partials/           ← _status_chip.html, _result_chip.html, …
        └── reports/
            ├── verify.html         ← Public verification result page
            └── report_print.html   ← Standalone A4 PDF layout (no base.html)
```

---

## 4. Database Schema

WeighCert uses **two databases**: SQLite for all business data and MongoDB for audit logs and certificate snapshots.

---

### 4.1 SQLite Tables (via Django ORM)

#### `auth_user` (Django built-in)

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `username` | VARCHAR(150) | Unique; used for login |
| `password` | VARCHAR(128) | Stored as `pbkdf2_sha256$1200000$<salt>$<hash>` |
| `first_name` | VARCHAR(150) | |
| `last_name` | VARCHAR(150) | |
| `email` | VARCHAR(254) | |
| `is_active` | BOOLEAN | Used to disable accounts |
| `is_staff` | BOOLEAN | Grants Django admin access |
| `date_joined` | DATETIME | |

---

#### `accounts_profile`

One-to-one extension of `auth_user`. Every user gets exactly one Profile.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `user_id` | FK → `auth_user` | OneToOne, CASCADE |
| `role` | VARCHAR(20) | Choices: `inspector`, `officer`, `admin` |
| `designation` | VARCHAR(100) | Official job title (e.g., "Assistant Controller") |
| `phone` | VARCHAR(20) | |
| `must_change_password` | BOOLEAN | Set `True` on account creation; forces password change on first login |

---

#### `accounts_loginattempt`

Tracks failed login attempts per username+IP pair for lockout enforcement.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `username` | VARCHAR(150) | The username that was attempted |
| `ip_address` | CHAR(39) | IPv4 or IPv6 |
| `attempts` | INTEGER | Count of consecutive failures |
| `locked_until` | DATETIME (nullable) | NULL = not locked; set to `now + 10 min` after 5 failures |
| `last_attempt` | DATETIME | Timestamp of last failed attempt |

---

#### `core_labsettings`

Singleton row (always `id=1`) storing laboratory configuration.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Always 1 (singleton) |
| `lab_name` | VARCHAR(200) | Displayed in PDF headers |
| `lab_address` | TEXT | Multi-line address |
| `report_number_prefix` | VARCHAR(20) | e.g., `WC/DEL` |
| `report_counter` | INTEGER | Current sequential counter (atomic, row-locked) |
| `counter_year` | INTEGER | Year the counter is currently counting for |
| `year_reset_policy` | VARCHAR(20) | `calendar`, `fiscal`, or `never` |
| `signatory_name` | VARCHAR(200) | Officer name on PDF |
| `signatory_designation` | VARCHAR(200) | Officer designation on PDF |
| `accreditation_number` | VARCHAR(100) | NABL or equivalent |

---

#### `core_ruleset`

Tracks which version of OIML R 76-1 rules is active.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `version_label` | VARCHAR(50) | e.g., `OIML R 76-1:2006` |
| `effective_from` | DATE | |
| `notes` | TEXT | Changelog / remarks |
| `is_active` | BOOLEAN (via notes convention) | Only one should be active at a time |

---

#### `core_classlimit`

Per-accuracy-class limits (minimum verification interval, etc.).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `accuracy_class` | VARCHAR(10) | e.g., `C3`, `D1` |
| `min_e_divisions` | INTEGER | Minimum number of verification intervals |
| `max_e_divisions` | INTEGER | Maximum number of verification intervals |

---

#### `core_mpeband`

Maximum Permissible Error table per accuracy class. Used by `rules/engine.py`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `accuracy_class` | VARCHAR(10) | `C3`, `C5`, `D1`, etc. |
| `from_divisions` | INTEGER | Lower bound of load range (in `e` units) |
| `to_divisions` | INTEGER | Upper bound (exclusive) |
| `mpe_divisions` | DecimalField | MPE in `e` units (±) |

---

#### `core_multiintervalcondition`

Stores criteria for multi-interval weighing instrument ranges.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `condition_text` | TEXT | Human-readable condition |
| `applies_to_class` | VARCHAR(10) | Accuracy class |

---

#### `registry_owner`

Business entity that owns a weighing instrument.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `trade_name` | VARCHAR(200) | Business name |
| `gstin_or_id` | VARCHAR(50) | GSTIN or other business ID |
| `address` | TEXT | Registered address |
| `contact_name` | VARCHAR(100) | |
| `contact_phone` | VARCHAR(20) | |
| `contact_email` | VARCHAR(254) | |

---

#### `registry_instrument`

The core instrument record. All capacity and interval values are stored in **grams** (never kg, tonnes, etc.) to avoid unit conversion errors.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `owner_id` | FK → `registry_owner` | |
| `manufacturer` | VARCHAR(200) | |
| `model_number` | VARCHAR(100) | |
| `serial_number` | VARCHAR(100) | Unique per manufacturer |
| `accuracy_class` | VARCHAR(10) | `C3`, `C5`, `D1`, … |
| `max_capacity_g` | DecimalField | Maximum capacity in grams |
| `min_capacity_g` | DecimalField | Minimum capacity in grams |
| `e_g` | DecimalField | Verification interval `e` in grams |
| `d_g` | DecimalField | Scale interval `d` in grams |
| `type_approval_number` | VARCHAR(100) | OIML type approval reference |
| `installation_date` | DATE | |
| `location` | VARCHAR(300) | Physical installation address |
| `registered_at` | DATETIME | Auto-set on creation |

**Key design detail:** Storing everything in grams means the formula `n = Max / e` always uses consistent units, preventing the class of bugs where `Max=100 kg` and `e=10 g` gives wrong division count.

---

#### `registry_instrumentrange`

For multi-interval instruments (multiple ranges with different `d` values).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `instrument_id` | FK → `registry_instrument` | |
| `range_number` | INTEGER | 1, 2, 3 (sequential) |
| `max_g` | DecimalField | Upper limit of this range |
| `d_g` | DecimalField | Scale interval for this range |

---

#### `registry_testweight`

Reference weights used during inspection.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `nominal_mass_g` | DecimalField | Nominal value in grams |
| `accuracy_class` | VARCHAR(10) | `E1`, `E2`, `F1`, `F2`, `M1`, `M2`, `M3` |
| `certificate_number` | VARCHAR(100) | Calibration certificate number |
| `calibrated_on` | DATE | Calibration date |
| `calibrated_by` | VARCHAR(200) | Calibrating laboratory |
| `is_active` | BOOLEAN | Whether available for use |

---

#### `inspections_testsession`

Master record for one complete inspection visit.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `instrument_id` | FK → `registry_instrument` | |
| `inspector_id` | FK → `auth_user` | Assigned inspector |
| `inspection_type` | VARCHAR(20) | `initial`, `subsequent`, `service` |
| `status` | VARCHAR(20) | Workflow state (see below) |
| `ambient_temp_c` | DecimalField | Ambient temperature (°C) |
| `ambient_humidity_pct` | DecimalField | Relative humidity (%) |
| `ambient_pressure_hpa` | DecimalField | Barometric pressure (hPa) |
| `site_conditions_ok` | BOOLEAN | Inspector confirms site OK |
| `pre_inspection_checklist` | JSON | Serialised checklist items (step 1) |
| `remarks` | TEXT | Inspector's final remarks (step 7) |
| `created_at` | DATETIME | Session creation time |
| `submitted_at` | DATETIME | When submitted for review |
| `reviewed_at` | DATETIME | When officer acted |
| `officer_id` | FK → `auth_user` (nullable) | Officer who reviewed |
| `officer_remarks` | TEXT | Officer's review notes |

**Status workflow:**

```
DRAFT → SUBMITTED → APPROVED
                 ↘ RETURNED (back to inspector for revision)
                 ↘ REVISED  (inspector resubmits)
```

---

#### `inspections_sessionweight`

Links which test weights were used in a session.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `session_id` | FK → `inspections_testsession` | |
| `weight_id` | FK → `registry_testweight` | |

---

#### `inspections_zerocheck`

Zero-setting and zero-range results (step 2 of wizard).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `session_id` | FK → `inspections_testsession` | |
| `indication_before_g` | DecimalField | Scale reading before zeroing |
| `indication_after_g` | DecimalField | Scale reading after zeroing |
| `zero_range_ok` | BOOLEAN | Whether zero range ≤ ±0.25e |
| `tare_range_ok` | BOOLEAN | Whether tare range meets requirements |

---

#### `inspections_accuracyreading`

One row per test load point in the accuracy test (step 3).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `session_id` | FK → `inspections_testsession` | |
| `load_g` | DecimalField | Applied load L (grams) |
| `indication_g` | DecimalField | Scale indication I (grams) |
| `reference_g` | DecimalField | Reference weight value (grams) |
| `P` | DecimalField | Changeover point: `P = I + e/2 − ΔL` |
| `E` | DecimalField | Error: `E = P − L` |
| `Ec` | DecimalField | Corrected error: `Ec = E − E0` |
| `mpe` | DecimalField | MPE for this load from OIML table |
| `passed` | BOOLEAN | `|Ec| ≤ mpe` |

---

#### `inspections_tare_check`

Tare device check (sub-test within step 3 / step 4).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `session_id` | FK | |
| `tare_load_g` | DecimalField | Tare applied |
| `indication_g` | DecimalField | Scale reading |
| `passed` | BOOLEAN | |

---

#### `inspections_repeatabilitytesting` and `inspections_repeatabilityreading`

Header (`RepeatabilityTest`) and per-reading (`RepeatabilityReading`) for the repeatability test (step 5). Minimum number of repetitions depends on number of intervals (n ≥ 500 → 10 repetitions; < 500 → 3 repetitions per OIML).

---

#### `inspections_eccentricitytest` and `inspections_eccentricityreading`

Header (`EccentricityTest`) and per-position (`EccentricityReading`) for eccentricity (off-centre load) test (step 6). Load is 1/3 of Max.

---

#### `inspections_discriminationreading`, `inspections_sensitivityreading`, `inspections_tiltcheck`

Additional optional/conditional test records stored per session. All follow the same pattern: session FK + measurement fields + `passed` boolean.

---

#### `reports_report`

The issued certificate record.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `session_id` | FK → `inspections_testsession` | OneToOne |
| `report_number` | VARCHAR(50) | e.g., `WC/DEL/2026/000001` |
| `revision` | INTEGER | 0 = original; increments on re-issue |
| `snapshot_hash` | CHAR(64) | SHA-256 hex digest of canonical JSON |
| `verification_token` | CHAR(48) | Random hex token; embedded in QR URL |
| `pdf_file` | FileField | Path to stored PDF in `MEDIA_ROOT` |
| `issued_at` | DATETIME | Auto-set when report generated |
| `supersedes_id` | FK → self (nullable) | Points to previous revision if any |

---

### 4.2 MongoDB Collections

MongoDB is used only for data that benefits from document-store flexibility and append-only semantics: the audit log and certificate snapshots.

#### Collection: `report_snapshots`

One document per issued certificate, stored when the report is first generated and re-verified.

```json
{
  "_id": ObjectId("..."),
  "report_number": "WC/DEL/2026/000001",
  "snapshot_hash": "a1b2c3...",
  "canonical_json": "{\"accuracy_class\":\"C3\",\"e_g\":\"10.000000\",...}",
  "created_at": ISODate("2026-05-10T08:00:00Z")
}
```

#### Collection: `audit_log`

Append-only log of all significant system events (login, logout, approval, password change). Each entry is **hash-chained** — it stores the SHA-256 hash of the previous entry — making the log tamper-evident (see Section 15).

```json
{
  "_id": ObjectId("..."),
  "event":     "report_approved",
  "user":      "officer1",
  "detail":    "Report WC/DEL/2026/000001 approved",
  "timestamp": ISODate("2026-05-10T08:00:00Z"),
  "prev_hash": "d4e5f6..."
}
```

---

## 5. User Roles & Authentication

### 5.1 Three Roles

| Role | Who | What they can do |
|------|-----|-----------------|
| `admin` | Lab administrator | Create/manage users, configure LabSettings, manage test weights and owners |
| `inspector` | Field inspector | Register instruments, run inspection wizard, view own sessions |
| `officer` | Approving officer | Review submitted sessions, approve / return / revise; triggers report generation |

### 5.2 No Self-Registration

There is **no public registration page**. Only an `admin` can create new user accounts. On creation, `must_change_password` is set to `True`. The first time the user logs in, they are redirected to `change_password` before they can access any other page.

### 5.3 Role-Based Access Control (RBAC) Implementation

Located in `accounts/decorators.py`:

```python
def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.profile.role not in roles:
                messages.error(request, "You do not have permission.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator

# Convenience wrappers:
inspector_required = role_required("inspector")
officer_required   = role_required("officer")
admin_required     = role_required("admin")
```

**How it works:**
1. `@login_required` (from Django) checks that the user is authenticated. If not, redirects to `/login/`.
2. The inner check reads `request.user.profile.role` (the `accounts_profile` table) and compares against the allowed roles list.
3. If the user is authenticated but has the wrong role, they get a Flash message and are redirected to the dashboard — they receive a **403-equivalent** experience without an HTTP 403 page.

---

## 6. Password Hashing Mechanism

### 6.1 Algorithm

WeighCert uses Django's default `PBKDF2PasswordHasher`, which is configured in `config/settings.py`:

```python
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
```

**PBKDF2** = Password-Based Key Derivation Function 2 (RFC 2898).

### 6.2 What Happens Under the Hood

Django's `PBKDF2PasswordHasher` calls Python's standard library function:

```python
import hashlib
dk = hashlib.pbkdf2_hmac(
    hash_name   = 'sha256',       # Inner hash algorithm
    password    = password.encode('utf-8'),
    salt        = os.urandom(16), # 16 random bytes, unique per user
    iterations  = 1_200_000,      # 1.2 million rounds
)
```

- **No external library required** — `hashlib.pbkdf2_hmac` is built into Python's standard library.
- The 1,200,000 iterations mean an attacker must do 1.2 million SHA-256 operations just to test *one* guess — making brute-force attacks computationally infeasible.

### 6.3 Stored Format

The resulting hash is stored in the `auth_user.password` column as a single string:

```
pbkdf2_sha256$1200000$<16-byte-salt-base64>$<32-byte-hash-base64>
```

Example (truncated):
```
pbkdf2_sha256$1200000$aBcDeFgHiJkLmNoP$X7y2Z...==
```

The four parts separated by `$` are:
1. **Algorithm identifier**: `pbkdf2_sha256`
2. **Iterations**: `1200000`
3. **Salt** (base64-encoded random bytes, unique per user)
4. **Hash** (base64-encoded derived key)

### 6.4 Verification at Login

When a user logs in, Django calls `authenticate(username=..., password=...)` which:

1. Fetches the stored hash string from `auth_user.password`
2. Extracts the algorithm, iterations, and salt from the stored string
3. Re-runs `hashlib.pbkdf2_hmac` with the **submitted password** and the **stored salt**
4. Compares the result using `hmac.compare_digest()` — a timing-safe comparison that prevents timing attacks (an attacker cannot tell from response time whether the hash was "almost correct")

```python
import hmac
result = hmac.compare_digest(computed_hash, stored_hash)  # True = password correct
```

### 6.5 Why This Is Secure

| Property | Detail |
|----------|--------|
| **Salted** | Every user gets a unique 16-byte random salt; even two users with identical passwords get different stored hashes |
| **Slow** | 1.2M iterations makes GPU-based cracking extremely slow |
| **Timing-safe** | `hmac.compare_digest` prevents timing oracle attacks |
| **Industry standard** | PBKDF2-SHA256 is NIST-approved (SP 800-132) |
| **Never stored in plaintext** | The raw password is never logged or stored anywhere |

---

## 7. Login Security & Account Lockout

### 7.1 Mechanism

Implemented in `accounts/middleware.py` as a Django middleware class (`LoginAttemptMiddleware`).

### 7.2 Logic Flow

```
User submits login form
        ↓
Middleware intercepts POST to /login/
        ↓
Look up LoginAttempt(username=X, ip=Y) — unique per username+IP pair
        ↓
Is locked_until set AND locked_until > now?
    YES → Return 403 "Account locked, try after HH:MM"
    NO  → Allow login attempt to proceed
        ↓
Did Django's authenticate() succeed?
    YES → Reset LoginAttempt (attempts=0, locked_until=None), log audit event
    NO  → Increment attempts counter
        ↓
    attempts >= 5?
        YES → Set locked_until = now + timedelta(minutes=10)
        NO  → Continue (error message shown)
```

### 7.3 Key Details

- **Lockout scope:** Per `(username, ip_address)` pair — not per IP or per username alone. This prevents one user from locking another user's account from a different IP.
- **Lockout duration:** 10 minutes from the 5th failed attempt.
- **Auto-unlock:** After `locked_until` passes, the next attempt is allowed and the counter resets on success.
- **Storage:** `accounts_loginattempt` table (SQLite).

---

## 8. Application Flow (End-to-End)

```
┌─────────────────────────────────────────────────────────────────┐
│  ADMIN SETUP                                                    │
│  1. Admin logs in → configures LabSettings (prefix, lab name)  │
│  2. Admin creates Inspector and Officer user accounts          │
│  3. Admin registers test weights (calibration certs)           │
└─────────────────────────┬───────────────────────────────────────┘
                           │
┌─────────────────────────▼───────────────────────────────────────┐
│  INSPECTOR: INSTRUMENT REGISTRATION                             │
│  4. Inspector logs in (forced password change on first login)   │
│  5. Inspector creates Owner record (business entity)           │
│  6. Inspector registers Instrument (Max, e, d, accuracy class) │
└─────────────────────────┬───────────────────────────────────────┘
                           │
┌─────────────────────────▼───────────────────────────────────────┐
│  INSPECTOR: 7-STEP INSPECTION WIZARD                           │
│  7.  Step 1 — Environmental conditions + pre-inspection         │
│      checklist (temperature, humidity, pressure, site OK)      │
│  8.  Step 2 — Zero check and zero range verification           │
│  9.  Step 3 — Accuracy test (each load point: P, E, Ec, MPE)  │
│  10. Step 4 — Tare setting test                                │
│  11. Step 5 — Repeatability test (3–10 repetitions)           │
│  12. Step 6 — Eccentricity test (load at 4–5 positions)       │
│  13. Step 7 — Remarks, attachments, submit for review          │
└─────────────────────────┬───────────────────────────────────────┘
                           │
┌─────────────────────────▼───────────────────────────────────────┐
│  OFFICER: REVIEW & APPROVAL                                     │
│  14. Officer sees submitted session in queue                   │
│  15. Officer reviews all test results, can RETURN for revision  │
│  16. Officer clicks APPROVE — triggers atomic operation:       │
│      a. generate_next_report_number() with row lock            │
│      b. Build canonical JSON snapshot                          │
│      c. Compute SHA-256 hash                                   │
│      d. Store hash in SQLite (reports_report.snapshot_hash)   │
│      e. Store snapshot document in MongoDB                     │
│      f. Generate QR code (base64 PNG)                         │
│      g. Render report_print.html with QR + data               │
│      h. Convert HTML → PDF (xhtml2pdf / WeasyPrint)           │
│      i. Save PDF to MEDIA_ROOT                                 │
│      j. Write audit log entry to MongoDB                       │
└─────────────────────────┬───────────────────────────────────────┘
                           │
┌─────────────────────────▼───────────────────────────────────────┐
│  PUBLIC: CERTIFICATE VERIFICATION                               │
│  17. PDF is handed to instrument owner                         │
│  18. Owner scans QR code → opens /verify/<token>/             │
│      OR enters report number at /verify/                       │
│  19. System recomputes hash from current DB state              │
│  20. Compares with stored hash → PASS or FAIL (tampered)      │
│  21. Shows green "Authentic" page or red "Invalid/Altered" page│
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. The 7-Step Inspection Wizard

Each step is a separate Django view + template. HTMX is used for partial updates (e.g., dynamically adding load rows without full page reload). The wizard tracks progress via the `TestSession.status` field and step-specific model records.

### Step 1 — Environmental Conditions & Pre-Inspection Checklist

- Inspector records: ambient temperature (°C), humidity (%), barometric pressure (hPa)
- Site conditions confirmed (level surface, no vibration, adequate lighting)
- Pre-inspection checklist stored as JSON in `testsession.pre_inspection_checklist`

### Step 2 — Zero Check

- Inspector reads the scale indication before zeroing
- Scale is zeroed; indication after zeroing is recorded
- System checks **zero range**: the zero-setting range must be ≤ ±0.25e (OIML R 76-1 §3.5)
- **Zero range formula:** `zero_range_ok = |indication_before_g| <= 0.25 * e_g`
- Result stored in `inspections_zerocheck`

### Step 3 — Accuracy Test (Core Test)

The most mathematically complex step. For each test load point L:

**Changeover Point Method (OIML R 76-1 §3.6.2):**

```
P = I + e/2 − ΔL

Where:
  I  = scale indication (grams)
  e  = verification interval (grams)
  ΔL = smallest test weight added to just change indication (grams)
       Required only when d > 0.2e (otherwise ΔL = 0)

Error:
  E  = P − L

Corrected Error (removes tare/zero offset):
  Ec = E − E0   (E0 = error at zero load / initial error)

Compliance:
  |Ec| ≤ mpe(L)   → PASS
  |Ec| > mpe(L)   → FAIL
```

The MPE values come from the OIML table (see Section 10).

### Step 4 — Tare Setting Test

- Verifies that the tare subtraction device (if present) operates correctly
- A known tare load is applied; the resulting indication is checked
- Result stored in `inspections_tare_check`

### Step 5 — Repeatability Test

- The same load is applied and removed multiple times without re-zeroing
- Number of repetitions required:
  - `n_divisions ≥ 500` → minimum **10 repetitions**
  - `n_divisions < 500` → minimum **3 repetitions**
  - where `n_divisions = Max / e`
- Maximum spread of readings must be ≤ MPE at that load
- Results stored in `inspections_repeatabilitytest` (header) + `inspections_repeatabilityreading` (per rep)

### Step 6 — Eccentricity Test

- Test load = **1/3 of Max capacity** (rounded down to nearest available test weight)
- Load is placed at each corner / quadrant of the platform (4–5 positions)
- Each position's indication is compared; difference from centre load must be ≤ MPE
- Results stored in `inspections_eccentricitytest` + `inspections_eccentricityreading`

### Step 7 — Remarks, Attachments & Submission

- Inspector enters overall remarks, special conditions, or caveats
- Final step allows inspector to review all previous step summaries
- "Submit for Review" button changes `session.status` → `SUBMITTED`
- An audit log entry is written to MongoDB

---

## 10. OIML Rules Engine

**Location:** `rules/engine.py`  
**Design principle:** Pure Python module — zero database access. All constants are either hardcoded from the OIML R 76-1:2006 tables or passed as arguments. This makes the engine fully unit-testable without a database.

### 10.1 Data Classes / Named Tuples

| Class | Fields | Purpose |
|-------|--------|---------|
| `RangeSpec` | `max_g`, `e_g`, `d_g` | Instrument or range specification |
| `MpeLookupResult` | `mpe_g`, `n_divisions` | Result of MPE table lookup |
| `ErrorResult` | `P`, `E`, `Ec`, `passed` | Result of single accuracy reading |
| `ComplianceResult` | `overall_pass`, `findings` | Aggregated result |
| `InstrumentFinding` | `load_g`, `E`, `Ec`, `mpe`, `passed` | Per-load finding |
| `RepeatabilityResult` | `spread_g`, `max_allowed_g`, `passed` | Repeatability outcome |
| `EccentricityLoad` | `position`, `indication_g`, `diff_g`, `mpe_g`, `passed` | Eccentricity per position |

### 10.2 Key Functions

#### `mpe_lookup(accuracy_class, load_g, e_g)`

Looks up Maximum Permissible Error for a given load from the OIML R 76-1 Table 1.

```python
# Returns MPE in grams for load_g on a scale with interval e_g in accuracy_class
# Example: mpe_lookup("C3", 500, 1) → MpeLookupResult(mpe_g=1, n_divisions=500)
```

The table (hardcoded from OIML R 76-1:2006 Table 1):

| Accuracy Class | 0 to 50 000 e | 50 001 to 200 000 e | > 200 000 e |
|---------------|--------------|-------------------|------------|
| Special (I) | 0.5 e | 1.0 e | 1.5 e |
| High (II) | 0.5 e | 1.0 e | 1.5 e |
| Medium (III / C) | 0.5 e | 1.0 e | 1.5 e |
| Ordinary (IIII / D) | 0.5 e | 1.0 e | — |

#### `error_calc(I, L, e_g, d_g, delta_L=0, E0=0)`

Computes P, E, Ec for a single accuracy reading:

```python
P  = I + (e_g / 2) - delta_L
E  = P - L
Ec = E - E0
```

Returns an `ErrorResult`. `delta_L` is only non-zero when `d_g > 0.2 * e_g`.

#### `check_compliance(readings, accuracy_class, e_g, inspection_type)`

Runs `mpe_lookup` and `error_calc` for every reading. Applies the **inspection type multiplier**:

- `initial` or `subsequent` → multiplier = **1×** MPE
- `service` → multiplier = **2×** MPE (OIML R 76-1 §3.7.1 — in-service tolerance is relaxed)

#### `zero_check(before_g, e_g)` and `zero_range_check(before_g, e_g)`

```python
# Checks if the zero indication error is within acceptable limits
# zero_check: |before_g| <= 0.5 * e_g
# zero_range_check: |before_g| <= 0.25 * e_g (stricter, for zero-range device)
```

#### `repeatability_eval(readings_g, load_g, e_g, accuracy_class)`

```python
spread = max(readings) - min(readings)
max_allowed = mpe_lookup(accuracy_class, load_g, e_g).mpe_g
passed = spread <= max_allowed
```

#### `required_repeatability_count(max_g, e_g)`

```python
n_divisions = max_g / e_g
return 10 if n_divisions >= 500 else 3
```

#### `eccentricity_required_load(max_g)`

```python
return max_g / 3  # 1/3 of Max capacity
```

#### `suggested_loads(max_g, e_g, n_points=5)`

Generates a schedule of test loads evenly distributed across the instrument's range, used to populate the accuracy test form automatically.

#### `validate_instrument(max_g, e_g, d_g, accuracy_class)`

Validates that the instrument specification is internally consistent according to OIML:
- `d_g <= e_g` (scale interval cannot be larger than verification interval)
- `e_g` must be of the form `1×10^k`, `2×10^k`, or `5×10^k` (valid e-series)
- Minimum and maximum number of verification intervals for the accuracy class

#### `overall_result(session_data)`

Aggregates all individual test results into a single overall PASS/FAIL for the entire inspection session.

---

## 11. Report Numbering System

**Location:** `core/numbering.py`

### 11.1 Format

```
WC/DEL/2026/000001
 ↑    ↑     ↑     ↑
 │    │     │     └── 6-digit zero-padded sequential counter
 │    │     └────── Year (calendar or fiscal depending on policy)
 │    └──────────── Lab code (from LabSettings.report_number_prefix → "WC/DEL")
 └───────────────── Report type prefix
```

### 11.2 Atomic Generation (Race-Condition Safe)

```python
def generate_next_report_number():
    with transaction.atomic():
        # Row-level lock — no two requests can run this simultaneously
        settings = LabSettings.objects.select_for_update().get(id=1)
        
        current_year = get_current_year(settings.year_reset_policy)
        
        # Reset counter if year changed
        if settings.counter_year != current_year:
            settings.report_counter = 0
            settings.counter_year = current_year
        
        settings.report_counter += 1
        settings.save()
        
        return f"{settings.report_number_prefix}/{current_year}/{settings.report_counter:06d}"
```

**Key:** `select_for_update()` applies a **database row lock** (SQLite: exclusive lock on that row) until the transaction commits. This guarantees that two simultaneous approvals cannot get the same report number, even in a multi-worker deployment.

### 11.3 Year Reset Policies

| Policy | Behaviour |
|--------|-----------|
| `calendar` | Counter resets to 1 on January 1 of each year |
| `fiscal` | Counter resets to 1 on April 1 of each year (India fiscal year) |
| `never` | Counter never resets; grows indefinitely |

---

## 12. PDF Generation

**Location:** `reports/pdf.py`

### 12.1 Two-Engine Strategy

```python
def render_pdf(template_name, context):
    html_string = render_to_string(template_name, context)
    
    try:
        # Primary: WeasyPrint (requires GTK3 — Linux/macOS)
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_string).write_pdf()
        
    except (ImportError, OSError):
        # Fallback: xhtml2pdf (pure Python — works on Windows)
        from xhtml2pdf import pisa
        buffer = BytesIO()
        pisa.CreatePDF(html_string, dest=buffer)
        pdf_bytes = buffer.getvalue()
    
    return pdf_bytes
```

### 12.2 PDF Template (`report_print.html`)

- **Does NOT extend `base.html`** — it is a **standalone** A4-layout template
- Uses inline CSS for print layout (page size, margins, header, footer)
- Contains: lab header, instrument details, all test results, QR code image, signatory block
- QR code is embedded as a `<img src="data:image/png;base64,...">` tag

### 12.3 xhtml2pdf Notes (Windows)

- xhtml2pdf handles most CSS2.1 and a subset of CSS3
- **Unicode symbols** (`⚖`, `≤`) cannot be rendered by xhtml2pdf without embedded Devanagari/Unicode fonts. These were replaced:
  - `⚖` → `LM` (Legal Metrology abbreviation)
  - `≤` → `&lt;=` (HTML entity)
- Devanagari text in report headers may show as boxes in the PDF on Windows (cosmetic issue only)

---

## 13. QR Code Generation

**Location:** `reports/qr_utils.py`

```python
import qrcode
import base64
from io import BytesIO

def generate_qr_base64(url: str) -> str:
    """Generate a QR code PNG and return it as a base64-encoded string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # 30% recovery
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
```

### What the QR Encodes

The QR code encodes the **direct verification URL**:

```
http://127.0.0.1:8000/verify/<verification_token>/
```

- `verification_token` is a 48-character random hex string (`secrets.token_hex(24)`) generated once at report creation and stored in `reports_report.verification_token`
- The token is unguessable (192 bits of entropy)
- Scanning the QR takes the user directly to the verification result page — no manual number entry needed

---

## 14. Cryptographic Verification & Tamper Detection

**Location:** `reports/snapshot.py`

### 14.1 Goal

Detect if any report data has been altered after the certificate was issued — either in the database or in a printed certificate presented for re-entry.

### 14.2 Canonical JSON Construction

At the moment of report approval, all report data is serialised into a **canonical JSON string**:

```python
import json, hashlib
from decimal import Decimal

def _dec_str(d: Decimal) -> str:
    """Normalise Decimal to fixed 6 decimal places string — prevents
    '3333' vs '3333.000000' mismatch between creation and verification."""
    return f"{d:.6f}"

def build_canonical(report) -> str:
    data = {
        "report_number":  report.report_number,
        "accuracy_class": report.session.instrument.accuracy_class,
        "max_capacity_g": _dec_str(report.session.instrument.max_capacity_g),
        "e_g":            _dec_str(report.session.instrument.e_g),
        "d_g":            _dec_str(report.session.instrument.d_g),
        # ... all accuracy readings, repeatability results, etc.
        "overall_result": "PASS" if all_pass else "FAIL",
        "issued_at":      report.issued_at.isoformat(),
    }
    # sort_keys=True, separators=(',',':') → no spaces, deterministic order
    return json.dumps(data, sort_keys=True, separators=(",", ":"))
```

**Critical detail — `_dec_str()` normalizer:**  
SQLite returns `Decimal("3333")` when you store it, but re-reads it as `Decimal("3333.000000")`. Without normalization, `json.dumps` would produce `"3333"` at creation vs `"3333.000000"` at verification → different JSON → hash mismatch → false tamper alert. The `_dec_str()` function always produces `"3333.000000"` for any value of `3333`, ensuring consistency.

### 14.3 Hash Computation

```python
canonical = build_canonical(report)
sha256_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
# → 64-character hex string, e.g. "a1b2c3d4..."
```

### 14.4 Storage

The hash is stored in **two places**:

1. `reports_report.snapshot_hash` (SQLite column)
2. MongoDB `report_snapshots` collection (as a separate document with the full canonical JSON)

This dual storage means: even if the SQLite database is compromised, the MongoDB copy provides a second reference.

### 14.5 Verification

On every request to `/verify/<token>/`:

```python
def verify_report(request, token):
    report = Report.objects.get(verification_token=token)
    
    # Recompute hash from current DB state
    current_canonical = build_canonical(report)
    current_hash = hashlib.sha256(current_canonical.encode()).hexdigest()
    
    if hmac.compare_digest(current_hash, report.snapshot_hash):
        return render(request, "reports/verify.html", {"status": "authentic"})
    else:
        return render(request, "reports/verify.html", {"status": "tampered"})
```

### 14.6 Verification Results

| Outcome | Displayed Message |
|---------|-----------------|
| Hash matches | ✅ "Authentic Verification Certificate — Integrity Verified Intact" |
| Hash mismatch | ❌ "Invalid or Altered Certificate — The certificate data does not match our cryptographically signed registry or has been tampered with" |
| Token not found | ❌ "Certificate not found" |

---

## 15. Audit Log Chain

**Location:** `core/audit.py`

### 15.1 What is Logged

Every significant system event is recorded in the MongoDB `audit_log` collection:

| Event | Triggered by |
|-------|-------------|
| `user_login` | Successful login |
| `user_logout` | Logout |
| `password_changed` | Password change (forced or voluntary) |
| `session_submitted` | Inspector submits for review |
| `session_returned` | Officer returns for revision |
| `report_approved` | Officer approves and report is generated |
| `report_downloaded` | PDF download |
| `settings_changed` | Admin changes LabSettings |

### 15.2 Hash Chaining

Each audit log entry stores the SHA-256 hash of the **previous entry** in the log:

```python
def log_audit(event, user, detail):
    db = get_mongo_db()
    
    # Get the last entry's hash (or genesis hash if first entry)
    last = db.audit_log.find_one(sort=[("_id", -1)])
    prev_hash = last["entry_hash"] if last else "0" * 64
    
    # Build the new entry
    entry = {
        "event":     event,
        "user":      user,
        "detail":    detail,
        "timestamp": datetime.utcnow(),
        "prev_hash": prev_hash,
    }
    
    # Compute this entry's own hash (over all fields including prev_hash)
    entry_str = json.dumps(entry, sort_keys=True, default=str)
    entry["entry_hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
    
    db.audit_log.insert_one(entry)
```

**Result:** The audit log forms a **hash chain** (similar to a blockchain):

```
Entry 1: prev_hash="000...0", entry_hash="aaa..."
Entry 2: prev_hash="aaa...",  entry_hash="bbb..."
Entry 3: prev_hash="bbb...",  entry_hash="ccc..."
```

If any historical entry is modified, its `entry_hash` will no longer match the `prev_hash` of all subsequent entries — tampering is detectable by walking the chain.

---

## 16. Template Inheritance & Structure

### 16.1 Base Template (`templates/base.html`)

All 11 UI pages (except the PDF print template) extend `base.html`:

```html
{% extends "base.html" %}
{% block title %}Page Title{% endblock %}
{% block content %}
  ... page-specific content ...
{% endblock %}
```

`base.html` provides:

- **GIGW 3.0 accessibility strip** (top bar with contrast toggle, font size buttons, language toggle)
- **Tricolor decorative strip** (saffron / white / green — Government of India branding)
- **Government masthead** — Emblem + lab name in English and Hindi
- **280px fixed left sidebar** — Navigation links filtered by user role
- **Main content area** — `{% block content %}` insertion point
- **JavaScript** — Theme, font size, HTMX, Chart.js (CDN)
- **Material Symbols** and **Noto Sans** fonts (CDN)

### 16.2 Template Blocks Available

| Block | Purpose |
|-------|---------|
| `{% block title %}` | HTML `<title>` tag |
| `{% block extra_head %}` | Additional CSS/JS in `<head>` |
| `{% block content %}` | Main page body |
| `{% block extra_scripts %}` | Page-specific JS before `</body>` |

### 16.3 Partials (Reusable Snippets)

Located in `templates/inspections/partials/`:

| Partial | Purpose |
|---------|---------|
| `_status_chip.html` | Coloured badge for session status (DRAFT/SUBMITTED/APPROVED/RETURNED) |
| `_result_chip.html` | PASS/FAIL coloured badge for test results |
| `_stat_card.html` | Dashboard statistic card (number + label + icon) |
| `wizard_nav.html` | 7-step wizard progress indicator |

### 16.4 Custom Template Tag

**Location:** `core/templatetags/weighcert_tags.py`

```python
from django import template
register = template.Library()

@register.filter
def format_mass(value_g, unit="g"):
    """
    Formats a mass value in grams to a human-readable string.
    Examples:
      format_mass(1000000)  → "1000.000 kg"
      format_mass(500)      → "500.000 g"
      format_mass(0.1)      → "100.0 mg"
    """
    ...
```

Used in templates as: `{{ instrument.max_capacity_g | format_mass }}`

This replaced invalid template syntax like `{{ instrument.format_mass:instrument.e_g }}` that caused `TemplateSyntaxError`.

### 16.5 Standalone PDF Template

`templates/reports/report_print.html` does **NOT** extend `base.html`. It is a self-contained A4-layout page designed specifically for PDF rendering:

- No sidebar, no navigation, no JavaScript
- Print CSS: `@page { size: A4; margin: 2cm; }`
- Embeds QR as `<img src="data:image/png;base64,...">` inline
- Renders all test data in tabular form
- Contains official signatory block and stamp placeholder

---

## 17. UI, Accessibility & Theme System

### 17.1 CSS Framework

**Tailwind CSS** is loaded from CDN — there is no npm/node build step. The CDN version uses the Play CDN which scans the DOM at runtime.

Tailwind configuration in `base.html`:

```javascript
tailwind.config = {
    darkMode: "class",   // Dark mode configured but not activated
    theme: {
        extend: {
            fontFamily: {
                sans: ["Noto Sans", "sans-serif"],
                mono: ["JetBrains Mono", "monospace"],
            }
        }
    }
}
```

**Note:** `darkMode: "class"` means Tailwind's dark mode utilities (e.g., `dark:bg-gray-900`) are configured but only activate when the `dark` class is on `<html>`. This class is never added in the current implementation — there is **no dark mode**, only a contrast toggle (see below).

### 17.2 Contrast Toggle (Accessibility)

The GIGW strip contains a "High Contrast" button. Clicking it toggles the `high-contrast` class on the `<html>` element:

```javascript
document.getElementById("btn-contrast").addEventListener("click", () => {
    document.documentElement.classList.toggle("high-contrast");
});
```

The CSS rules for high-contrast:

```css
html.high-contrast {
    filter: contrast(125%);
}
html.high-contrast body {
    background-color: #000 !important;
    color: #fff !important;
}
html.high-contrast a,
html.high-contrast button {
    border: 2px solid #fbbf24 !important; /* amber-400 */
}
```

This applies a global CSS `filter: contrast(125%)` plus forced dark background and amber borders — **not** a full dark theme, but rather a government-standard high-contrast accessibility mode.

### 17.3 Font Size Adjustment

Three buttons in the GIGW strip: **A−**, **A**, **A+**

```javascript
const sizes = [85, 100, 115, 125]; // percentages
let currentIdx = 1; // default = 100%

document.getElementById("btn-font-down").addEventListener("click", () => {
    if (currentIdx > 0) currentIdx--;
    document.documentElement.style.fontSize = sizes[currentIdx] + "%";
});
document.getElementById("btn-font-up").addEventListener("click", () => {
    if (currentIdx < sizes.length - 1) currentIdx++;
    document.documentElement.style.fontSize = sizes[currentIdx] + "%";
});
document.getElementById("btn-font-reset").addEventListener("click", () => {
    currentIdx = 1;
    document.documentElement.style.fontSize = "100%";
});
```

**Range:** 85% (smallest) → 100% (default) → 115% → 125% (largest)  
**Mechanism:** Sets `font-size` on the root `<html>` element. All `rem`-based Tailwind utilities automatically scale with this, making the entire page larger or smaller.  
**Persistence:** Session-only (not saved to localStorage).

### 17.4 Bilingual Toggle (English / Hindi)

The GIGW strip has "English" and "हिंदी" buttons. These are currently **cosmetic only** — clicking them does not switch the UI language. The buttons are present to meet GIGW 3.0 requirements for the UI mock. Full i18n would require Django's `i18n` framework and translated `.po` files.

### 17.5 Layout

| Element | Description |
|---------|-------------|
| GIGW strip | Top bar: accessibility controls + official government designation |
| Tricolor strip | 3px saffron / white / green decorative line |
| Masthead | Government emblem (SVG) + lab name (English + Hindi) |
| Sidebar | 280px fixed-width left sidebar; collapsible on mobile |
| Main content | Fluid width, `ml-[280px]` offset |

### 17.6 Accessibility Features

| Feature | Implementation |
|---------|---------------|
| Skip navigation | `<a href="#main-content" class="sr-only focus:not-sr-only">Skip to Main Content</a>` |
| ARIA roles | Sidebar has `role="navigation"`, main has `role="main"` |
| Semantic HTML | `<nav>`, `<main>`, `<header>`, `<footer>` used throughout |
| Icon labels | All Material Symbol icons accompanied by visible text or `aria-label` |
| Contrast toggle | As above (Section 17.2) |
| Font resizing | As above (Section 17.3) |

---

## 18. Demo Credentials & Seed Data

Seed data is loaded with:

```
py -3 manage.py seed_demo
```

### 18.1 Demo Users

| Username | Password | Role | Notes |
|----------|----------|------|-------|
| `admin` | `Admin@1234` | admin | Full system access |
| `inspector` | `Inspector@1234` | inspector | Can run inspection wizard |
| `officer` | `Officer@1234` | officer | Can approve/return sessions |

> **Security note:** `must_change_password` is set to `False` for demo users so they can log in directly without being forced to change password.

### 18.2 Seeded Instruments & Reports

| Item | Detail |
|------|--------|
| Test weights | 8 reference weights (various classes and nominal masses) |
| Owners | 1 demo owner (a fictitious business) |
| Instruments | 3 instruments (Class C3, C5, D1) |
| Issued report | `WC/DEL/2026/000001` — PASS result, verification working |
| Verification URL | `http://127.0.0.1:8000/verify/<token>/` → "Authentic" |

---

## 19. Golden Test Results

**Location:** `rules/tests_golden.py`  
**Run command:** `py -3 -m pytest rules/tests_golden.py -v`  
**Result:** 43 / 43 PASSED

The golden tests cover the pure rules engine (`rules/engine.py`) with hand-computed expected values taken directly from OIML R 76-1:2006 worked examples and edge cases:

| Test Category | Count | What is tested |
|---------------|-------|----------------|
| MPE lookup | 12 | Correct MPE for each accuracy class and load range boundary |
| Error calculation | 8 | P, E, Ec with and without ΔL, with and without corrected error |
| Compliance check | 6 | Pass/fail decisions at boundary values |
| Repeatability | 5 | Required count calculation and spread evaluation |
| Eccentricity | 4 | Required load calculation and position comparison |
| Zero check | 4 | Zero range and tare range boundaries |
| Instrument validation | 4 | Valid and invalid e-series values, interval count limits |

---

## 20. Known Limitations & Future Work

### 20.1 Current Limitations

| Item | Detail |
|------|--------|
| **No true dark mode** | Tailwind `darkMode: "class"` is configured but not activated. Only a high-contrast accessibility filter is implemented. Full dark mode would require adding/removing the `dark` class and adding `dark:` Tailwind variants throughout templates. |
| **Hindi UI is cosmetic** | The language toggle buttons exist for GIGW compliance but do not change the UI language. Full i18n requires Django `USE_I18N = True`, `.po` translation files, and `{% trans %}` tags throughout templates. |
| **WeasyPrint not available on Windows** | WeasyPrint requires `libgobject-2.0-0` (GTK3), which is not installed on the Windows dev environment. xhtml2pdf is used as a fallback. For production on Linux, WeasyPrint produces higher-quality PDFs. |
| **Devanagari in PDF** | xhtml2pdf does not render Devanagari (Hindi) text without embedded Unicode fonts. Hindi text in PDF headers appears as boxes on Windows. Embedding a Unicode font (e.g., Noto Sans Devanagari) in the PDF template would fix this. |
| **SQLite in production** | SQLite is suitable for development and low-volume deployments. For high-concurrency production, migration to PostgreSQL is recommended. The Django ORM makes this a configuration change only. |
| **Local QR URLs** | The QR code currently encodes `http://127.0.0.1:8000/verify/...`. In production, the base URL must be set to the public domain in `LabSettings` or `settings.py`. |
| **No email notifications** | There is no email notification when sessions are submitted or approved. Django's built-in email backend would need to be configured. |
| **Single-tenant** | The system is designed for a single laboratory. Multi-tenancy (multiple labs sharing one deployment) would require a tenant isolation layer. |
| **Font persistence** | Font size preference is not saved to `localStorage`. It resets on page reload. |

### 20.2 Recommended Future Enhancements

1. **Production deployment:** PostgreSQL + Gunicorn + Nginx on Linux with WeasyPrint
2. **Email notifications:** Django email backend for submit/approve workflow
3. **Full Hindi i18n:** `USE_I18N = True` + `.po` files + `{% trans %}` tags
4. **True dark mode:** Add `dark` class toggle + complete `dark:` Tailwind variants
5. **REST API:** Django REST Framework for mobile inspector app integration
6. **Digital signature:** Qualified electronic signature (DSC) on PDF for legal enforceability
7. **Offline mode:** Service Worker + IndexedDB for field inspectors with poor connectivity
8. **Multi-lab / multi-tenant:** Tenant isolation for state-wide deployment
9. **Devanagari in PDF:** Embed Noto Sans Devanagari font in xhtml2pdf template

---

## Appendix A — Key File Reference

| File | Purpose |
|------|---------|
| `config/settings.py` | Django configuration; dual DB setup |
| `config/urls.py` | Root URL dispatcher |
| `accounts/models.py` | Profile, LoginAttempt |
| `accounts/decorators.py` | RBAC decorators |
| `accounts/middleware.py` | Lockout middleware |
| `core/audit.py` | Hash-chained MongoDB audit log |
| `core/numbering.py` | Atomic report number generator |
| `core/templatetags/weighcert_tags.py` | `format_mass` custom template filter |
| `rules/engine.py` | Pure-Python OIML R 76-1 rules |
| `rules/tests_golden.py` | 43 golden test cases |
| `reports/snapshot.py` | Canonical JSON + SHA-256 + MongoDB |
| `reports/pdf.py` | WeasyPrint / xhtml2pdf dispatcher |
| `reports/qr_utils.py` | QR code base64 generator |
| `templates/base.html` | Master layout (accessibility, sidebar) |
| `templates/reports/report_print.html` | Standalone A4 PDF template |

---

## Appendix B — OIML R 76-1:2006 Key Clauses Referenced

| Clause | Topic |
|--------|-------|
| §3.5 | Zero-setting and tare-balancing devices — zero range |
| §3.6.2 | Accuracy test — changeover point method |
| §3.7.1 | In-service inspection — 2× MPE tolerance |
| §3.6.3 | Repeatability test — number of repetitions |
| §3.6.4 | Eccentricity test — 1/3 Max load |
| Table 1 | Maximum Permissible Errors by accuracy class and load range |
| §3.3 | Accuracy classes (I, II, III, IIII) |
| §3.4 | Verification interval `e` — valid values (1×, 2×, 5× series) |

---

*End of WeighCert Project Technical Report*
