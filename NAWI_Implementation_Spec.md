# NAWI Test Report Software: Implementation Specification

**Project:** Development of a Software Program/Application for Generation of Test Reports for Non-Automatic Weighing Instruments (NAWI) as per OIML Recommendation R 76
**Working name:** WeighCert
**Stack:** Django + SQLite (relational data) + MongoDB (audit trail and report snapshots)
**Regulatory source:** OIML R 76-1, Edition 2006 (E). Everything needed from it is extracted in Section 4, so the PDF does not need to be opened again.

---

## 0. How to use this document

- **Section 4 is the regulatory truth.** Every rule, limit and formula is traceable to a clause of R 76-1 (clause numbers in brackets, for example `[3.5.1]`).
- **Sections 5 to 8 define the software:** architecture, data model, rules engine, workflow.
- **Section 9 defines the pages.** The visual design comes from the **Stitch UI** reference. Stitch is the source of truth for look and layout; this document is the source of truth for behaviour, data and validation.
- **Section 13 is the build order** with acceptance criteria.
- Anything marked **[DECISION]** is a design choice made where the standard leaves room. Anything marked **[CONFIRM]** needs checking against R 76-2 or the competition organisers.

### Corrections to earlier discussion (these supersede anything said before)

| Earlier statement | Correct position (from R 76-1) |
|---|---|
| "At least 10 test loads for initial verification" | 10 loads apply to the *initial intrinsic error in type evaluation* `[A.4.4.1]`. At **verification**, "five loading steps are normally sufficient" `[8.3.3]`. The app defaults to 5 and allows more. |
| "In-service tests have twice the limit" | Only **service inspection** doubles the limit `[8.4.2]`. **Initial verification** and **subsequent verification** both use the normal limits `[8.3.3, 8.4.1]`. |
| "Error = indication minus load" | Correct only when the actual scale interval d is 0.2 e or less. When **d > 0.2 e** (the usual case, d = e) the rounding error **must be eliminated** `[3.5.3.2]` using the changeover-point method `[A.4.4.3]` (Section 4.8). |
| "Discrimination test for every scale" | At verification, discrimination is **not applicable to instruments with digital indication** `[8.3.3]`. It applies only to analog and non-self-indicating instruments. |

---

## 1. Product overview

Legal Metrology officers and calibration labs test weighing scales and issue a test report for each. This software replaces paper and Excel with a guided test workflow:

1. Register the scale (instrument) and the standard weights.
2. Run a guided test: visual inspection, zero check, accuracy (weighing) test, repeatability, eccentricity, plus conditional tests (tare, discrimination).
3. The system calculates every error, looks up the allowed limit, and marks each reading pass or fail, with live feedback while the officer types.
4. An Officer approves the result.
5. The system issues a **numbered, locked PDF report** with a QR code that anyone can use to verify the report online.

### Goals
- **Correctness first:** limits and formulas must match R 76-1 exactly, proven by unit tests (Section 12).
- **Speed for the inspector:** fast data entry, minimal clicks, suggested test loads, instant pass/fail.
- **Tamper-evidence:** issued reports cannot be edited; every change is audited.
- **Ready to use:** login, roles, history, search, PDF, verification, admin settings. No demo-only features.

---

## 2. Scope

### In scope (v1)
- Single-range and **multi-interval** instruments (Section 4.7), classes I, II, III, IIII.
- Three inspection types: initial verification, subsequent verification, service inspection.
- Tests: visual inspection, zero check, accuracy (up and down), repeatability, eccentricity (four loading modes), tare (conditional), discrimination (conditional), sensitivity (conditional, non-self-indicating only).
- Standard weights register with calibration-due checks.
- Approval workflow, locked reports, revisions, QR verification.
- Single-organization installation with invite-only accounts created by the Admin (Section 3.1).
- Audit trail, report archive, search.

### Out of scope (v1)
- Type-approval (type evaluation) tests: influence factors, temperature, humidity, voltage, EMC, creep, zero return, stability of equilibrium, portable weighbridge tests `[3.9, A.5, A.4.11–A.4.13]`.
- Module testing (load cells, indicators) `[Annex C–F]`.
- Integration with any government portal [CONFIRM with organisers].
- Hardware integration (reading a scale over serial/USB).
- Payments, invoicing, notifications centre, public marketing site.
- Self-registration and multi-organization (multi-tenant) support.

---

## 3. Users and roles

Three login roles with clearly separated duties, plus the public (no login).

| Role | Responsibility | Can do | Cannot do |
|---|---|---|---|
| **Inspector** | Fills in machine details and performs the tests | Create and edit owners and instruments; create tests; enter all readings; submit tests to the Officer; fix and resubmit returned tests; create a revision of an issued report; view the standard weights | Approve or issue reports; manage users, weights or settings |
| **Officer** | Reviews and approves | View every test in full; **approve** (issues the report) or **return** with a mandatory comment; view the report archive | Edit any test data, instruments or readings. The Inspector stays responsible for the data. |
| **Admin** | Sets up and maintains the system | Manage users, standard weights, lab settings and report numbering; view the audit log; **view-only access to all tests and reports** (to answer queries and find old reports) | Create, edit, submit or approve tests; edit an issued report |
| **Public (no login)** | Verifies a report | Open the verification page through the QR code or report number; sees validity, instrument, date and result only | Anything else |

Rule: **separation of duties comes from the roles themselves.** Inspectors never approve and Officers never enter readings, so nobody can approve their own test. (An account holds exactly one role.)

### 3.1 Account provisioning (single organization, invite-only)

- **One organization per installation.** Each authority or lab runs its own copy of the software. There is no multi-organization mode in v1, and no organization or tenant field is needed. (Keeping record ownership in a single `LabSettings` row leaves room to add multi-organization later.)
- **No self-registration.** The login page has no "Sign up" link and no public registration URL exists.
- **First Admin:** created once at installation (setup command or Django admin) with the organization's details.
- **All other accounts:** the Admin creates them on the Settings page (full name, official email, employee ID, designation, role = Inspector or Officer). The new user receives a temporary password or a one-time invite link and **must set their own password on first login**.
- **Roles are assigned only by the Admin**, one role per account. Users cannot change their own role.
- **Leavers are deactivated, never deleted,** so their past tests, approvals and audit entries remain intact.
- **Hardening:** optional restriction to official email domains (for example `.gov.in`); lockout after 5 failed logins for 10 minutes; password reset only by the Admin or through an emailed one-time link; optional OTP second step for Officers and Admins; every account creation, role change and deactivation is written to the audit log.

---

## 4. Regulatory reference (extracted from OIML R 76-1:2006)

### 4.1 Source status
- This is **R 76-1** (metrological and technical requirements, test procedures, verification). The official **test report format is in R 76-2**, which is a separate document. [CONFIRM] Until R 76-2 is available, the report layout in Section 10 is derived from the fields R 76-1 requires.

### 4.2 Symbols and terms

| Symbol | Meaning |
|---|---|
| **Max** | Maximum capacity |
| **Min** | Minimum capacity (lower limit of the weighing range) |
| **e** | Verification scale interval, the step used for classification and limits |
| **d** | Actual scale interval, the real step of the display |
| **n** | Number of verification intervals, n = Max / e |
| **m** | A load expressed in verification intervals, m = L / e |
| **L** | Applied load (true value of the test load) |
| **I** | Indicated value (what the instrument shows) |
| **ΔL** | Small extra load added until the display steps up by one interval (changeover method) |
| **P** | Indication prior to rounding |
| **E** | Error prior to rounding |
| **E0** | Error at zero (or close to zero, for example at 10 e) |
| **Ec** | Corrected error, Ec = E − E0 |
| **mpe** | Maximum permissible error (absolute value, symmetrical ±) |
| **T** | Maximum tare effect (additive T+, subtractive T−) |
| **Lim** | Maximum safe load, if marked |

### 4.3 Accuracy classes `[Table 1]`

| Class | Name |
|---|---|
| **I** | Special accuracy |
| **II** | High accuracy |
| **III** | Medium accuracy |
| **IIII** | Ordinary accuracy |

### 4.4 Classification limits `[Table 3, 3.2]`

| Class | Verification interval e | n minimum | n maximum | Min (lower limit) |
|---|---|---|---|---|
| I | 0.001 g ≤ e | 50,000 | none | 100 e |
| II | 0.001 g ≤ e ≤ 0.05 g | 100 | 100,000 | 20 e |
| II | 0.1 g ≤ e | 5,000 | 100,000 | 50 e |
| III | 0.1 g ≤ e ≤ 2 g | 100 | 10,000 | 20 e |
| III | 5 g ≤ e | 500 | 10,000 | 20 e |
| IIII | 5 g ≤ e | 100 | 1,000 | 10 e |

Notes:
- For the **Min** column, `[3.4.3]` says to use the actual scale interval **d** instead of e. Minimum capacity is reduced to **5 e** for *grading instruments* (instruments that determine a transport tariff or toll, for example postal scales and waste weighing).
- Class I with d < 0.1 mg may have n below 50,000 `[3.4.4]`. Class I "e ≥ 0.001 g" is not normally verifiable below 1 mg because of test-load uncertainty.
- **[DECISION]** All classification checks are **warnings, not hard blocks** at registration, because the instrument is already built and marked by the manufacturer. A failed check is shown on the instrument and printed on the report.

### 4.5 Relationship between e and d `[3.4.2]`
- d < e ≤ 10 d. For many digital scales d = e.
- e is of the form 1×10^k, 2×10^k or 5×10^k in the unit used, k being a whole number (positive, negative or zero). The text extracted from the PDF garbled the exponent; this series is the standard's usual one. **[DECISION]** Treat this as a soft validation (warning only).
- Exception: class I with d < 1 mg uses e = 1 mg `[Table 5b]`.

### 4.6 Maximum permissible errors on initial verification `[3.5.1, Table 6]`

Load m is in verification intervals (m = L / e). The limit is the same for increasing and decreasing loads. Boundaries are **inclusive on the upper side** (for example class III: m = 500 gives ±0.5 e, m = 501 gives ±1.0 e).

| MPE | Class I | Class II | Class III | Class IIII |
|---|---|---|---|---|
| ±0.5 e | 0 ≤ m ≤ 50,000 | 0 ≤ m ≤ 5,000 | 0 ≤ m ≤ 500 | 0 ≤ m ≤ 50 |
| ±1.0 e | 50,000 < m ≤ 200,000 | 5,000 < m ≤ 20,000 | 500 < m ≤ 2,000 | 50 < m ≤ 200 |
| ±1.5 e | 200,000 < m | 20,000 < m ≤ 100,000 | 2,000 < m ≤ 10,000 | 200 < m ≤ 1,000 |

The absolute mpe is 0.5 e, 1.0 e or 1.5 e (no sign) `[3.5.1 note]`. A load above the class's highest band (for example class III with m > 10,000) is outside the class and must be flagged as an invalid instrument/test configuration.

**Limit multiplier by inspection type**

| Inspection type | Clause | Multiplier |
|---|---|---|
| Initial verification | `[8.3.3]` | **1×** |
| Subsequent verification | `[8.4.1]` | **1×** |
| Service inspection | `[8.4.2, 3.5.2]` | **2×** |

For all tests, the mpe used is the mpe for the **applied load** (net load when a tare is in use `[3.5.3.3]`).

### 4.7 Multi-interval instruments `[3.3, 3.3.4, A.4.4.3 note]`
- The instrument has partial weighing ranges i = 1, 2, …, each with its own e_i and Max_i, with e_(i+1) > e_i. Min_i = Max_(i−1) for i > 1; the first range uses the instrument's Min.
- n_i = Max_i / e_i. Each e_i and n_i must satisfy Table 3 for the class, and Min must too.
- Condition on range capacities (all except the last range) `[Table 4]`: **Max_i / e_(i+1)** must be at least **50,000** (class I), **5,000** (II), **500** (III), **50** (IIII).
- **Limit for a load L:** find the partial range i where L falls (a load exactly equal to Max_i belongs to range i). Compute m = L / e_i. Apply the Table 6 band for that m, and give the mpe in multiples of **e_i**. At or near zero use e = e_1.
- **Tare:** requirements apply to the net load for every tare value `[3.3.4]`.
- **Official worked example** (class III, Max 2 / 5 / 15 kg, e = 1 / 2 / 10 g, so n_1 = 2,000, n_2 = 2,500, n_3 = 1,500):

| Load | mpe |
|---|---|
| 0 to 500 g | ±0.5 e1 = ±0.5 g |
| above 500 g to 2,000 g | ±1 e1 = ±1 g |
| above 2,000 g to 4,000 g | ±1 e2 = ±2 g |
| above 4,000 g to 5,000 g | ±1.5 e2 = ±3 g |
| above 5,000 g to 15,000 g | ±1 e3 = ±10 g |

These five rows are mandatory unit tests (Section 12).

### 4.8 Error evaluation `[3.5.3.2, A.4.4.3]`
- **Rule:** the rounding error in a digital indication **must be eliminated if the actual scale interval d is greater than 0.2 e** `[3.5.3.2]`. The changeover method applies to digital instruments without a device showing a smaller interval (not greater than 1/5 e) `[A.4.4.3]`.
- **Changeover method** at a load L:
  1. Note the indication I.
  2. Add extra weights, about 1/10 e at a time, until the indication increases unambiguously by one interval (to I + e). The total extra load added is ΔL.
  3. **P = I + ½ e − ΔL** (indication before rounding)
  4. **E = P − L = I + ½ e − ΔL − L**
  5. **Ec = E − E0** (corrected error), where E0 is the error found the same way at zero or near zero load (for example at 10 e).
  6. Compliance: **|Ec| ≤ mpe**.
- For a multi-interval instrument, the "½ e" term is ½ e_i or ½ e_(i+1) according to the partial range in which the indication **(I + e)** appears, and the extra weights are added in steps of 1/10 e_i `[A.4.4.3 note]`.
- **Simple method** (when d ≤ 0.2 e, or analog): E = I − L, and Ec = E − E0 where applicable.
- **Official worked example:** e = 5 g. Load 1,000 g, indication 1,000 g, the display changes to 1,005 g after adding 1.5 g. P = 1,000 + 2.5 − 1.5 = 1,001 g. E = +1 g. If E0 = +0.5 g then Ec = **+0.5 g**. (Mandatory unit test.)
- **[DECISION]** The software enforces the changeover method when d > 0.2 e (the ΔL field becomes required). An admin setting "allow simplified error calculation" lets a lab proceed without ΔL, in which case every affected report prints a visible note "Rounding error not eliminated; error computed as I − L". Default: off.

### 4.9 Verification: what must be done `[8.3, 8.3.2, 8.3.3, 8.4.1, 8.4.2]`

**Preconditions `[8.3]`**
- Initial verification only if conformity to the approved type and/or R 76 is established.
- It may be done at the manufacturer or elsewhere only if (a) transport does not require dismantling, (b) installation at the place of use needs no assembly or technical work that could affect performance, and (c) local gravity is taken into account or the instrument is insensitive to gravity. Otherwise tests are done at the place of use. If performance is gravity-sensitive, verification can be done in two stages, the second at the place of use. A gravity zone or zone of use may be defined instead of a location.
- Conformity declaration `[8.3.1]` covers: correct operation of all devices (zero-setting, tare, calculating), construction material and design where metrologically relevant, proof of module compatibility if the modular approach is used, and (if appropriate) a list of tests performed.

**Visual inspection before testing `[8.3.2]`:** check metrological characteristics (accuracy class, Min, Max, e, d), software identification if applicable, module identification if applicable, and prescribed inscriptions and positions for verification and control marks. Consider whether the location and conditions of use are appropriate if known.

**Tests at verification `[8.3.3]`** (error limits are the initial-verification mpe; doubled for service inspection)

| Test | Clause | Applicability |
|---|---|---|
| Errors of indication (weighing test) | 3.5.1, 3.5.3.3, 3.5.3.4, A.4.4–A.4.6 | Always. "Five loading steps are normally sufficient"; Min is included only if Min ≥ 100 mg |
| Accuracy of zero-setting and tare devices | 4.5.2, 4.6.3, A.4.2.3, A.4.6.2 | If the devices exist |
| Repeatability | 3.6.1, A.4.10 (3rd paragraph) | Always |
| Eccentric loading | 3.6.2, A.4.7 | Always (not needed if operating conditions cannot produce eccentric loading `[A.4.7 note]`) |
| Discrimination | 3.8, A.4.8 | **Not applicable for digital indication** |
| Tilt (mobile instruments) | 4.18, A.5.1.3 | Mobile instruments only |
| Sensitivity (non-self-indicating) | 6.1, A.4.9 | Non-self-indicating instruments only |

Other tests may be done in special cases (unusual construction, doubtful results, as indicated in the OIML certificate). The responsible authority may require the applicant to provide test loads, equipment and personnel.

**Marking and securing `[8.3.4, 7.2]`:** according to national legislation, verification may be testified by verification marks (which may indicate the month or year of verification or when reverification is due). Components whose dismantling could alter the metrological characteristics may need securing. A place for the marks is required (stamping area at least 150 mm², or a sticker space of at least 15 mm diameter). The report records whether marks were applied and the seal/sticker reference.

**Subsequent verification `[8.4.1]`:** normally only inspection and tests per 8.3.2 and 8.3.3, with initial-verification limits; the stamping date is the date of the subsequent verification.
**Service inspection `[8.4.2]`:** the same inspection and tests, but with **twice** the initial-verification limits.

### 4.10 Test procedures and pass criteria

**A. Zero check** `[4.5.1, 4.5.2, A.4.2.3, A.4.3]`
- After zero setting, the effect of the zero deviation on a weighing result is not more than **±0.25 e** `[4.5.2]`.
- Determine the zero error E0 by the changeover method (with weights of about 1/10 e added until the display steps) for digital instruments `[A.4.2.3.1]`.
- Maximum effect of zero-setting devices `[4.5.1]`: overall effect of zero-setting and zero-tracking not more than **4 %** of Max; initial zero-setting device not more than **20 %** of Max. This does not affect class IIII unless used for commercial transactions. A wider initial range is allowed if 3.5, 3.6, 3.8 and 3.9 are met within it. When the initial zero-setting range exceeds 20 % of Max, a supplementary weighing test using the upper limit of the range as zero is required `[A.4.4.2]`.
- Zero-setting range tests are procedures `[A.4.2.1]`; v1 records the measured range and checks it against the 4 % / 20 % limits as optional fields.

**B. Weighing (accuracy) test** `[A.4.4.1, 3.5.1, 3.6]`
- Apply test loads from zero up to and including Max, then remove them back to zero. Loads are **progressively increased** then **progressively decreased**.
- Selected loads must include **Max**, **Min** (only if Min ≥ 100 mg), and values **at or near those at which the mpe changes**. Verification default: at least 5 loads. [DECISION] For multi-interval instruments the "mpe change" points include every band boundary in every partial range, including range changeovers.
- Before each weighing test the instrument is preloaded once to Max (or Lim, if defined) `[A.4.1.10]`. Allow recovery between tests `[A.4.1.9]`.
- Automatic zero-setting or zero-tracking may be in operation during the test (error at zero then determined per A.4.2.3.2), except for the temperature test.
- **Every row (increasing and decreasing) must satisfy |Ec| ≤ mpe at its load.** The error of any single weighing result must by itself not exceed the mpe `[3.6]`.

**C. Tare tests** `[3.5.3.3, 3.5.3.4, 4.6.3, A.4.6]`
- Required only if the instrument has a tare device. Mpe applies to the **net value** for every possible tare except preset tare values `[3.5.3.3]`.
- Weighing tests (loading and unloading) with different tare values, at least **5 load steps** including values close to Min (Min only if ≥ 100 mg), values at or near the mpe change points, and a value close to the maximum possible net load `[A.4.6.1]`.
  - Subtractive tare: one tare value between **1/3 and 2/3** of the maximum tare.
  - Additive tare: two tare values, about **1/3 and 3/3** of the maximum tare effect.
- Accuracy of tare setting: the tare device must set the indication to zero within **±0.25 e** (electronic instruments and any analog indication) or **±0.5 d** (mechanical instruments with digital indication). For multi-interval instruments e is replaced by e1 `[4.6.3, A.4.6.2]`.
- A tare weighing device (if any): results for the same load by the tare weighing device and the indicating device are compared; the same mpe applies to the tare weighing device as the instrument `[3.5.3.4, A.4.6.3]`.
- Where multiple indicating devices exist, their indications must agree within the absolute mpe, and exactly (zero difference) between a digital display and a printing device `[3.6.3, A.4.5]`.

**D. Repeatability** `[3.6.1, A.4.10]`
- Rule: the **difference between the results of several weighings of the same load must not be greater than the absolute mpe for that load** `[3.6.1]`, and every single result must also be within the mpe `[3.6]`.
- **Verification:** one series at about **0.8 Max** is sufficient. Number of weighings: **3 for classes III and IIII, 6 for classes I and II** `[A.4.10]`.
- (Type approval, for reference only: series at about 50 % and about 100 % of Max, 10 weighings each if Max < 1,000 kg, otherwise at least 3.)
- Take readings when loaded and when the unloaded instrument has come to rest. If the zero deviates between weighings, reset to zero without determining the error at zero. If automatic zero-setting or zero-tracking exists, it stays on.
- **Evaluation:** compute the error of each weighing (Section 4.8), then spread = highest error minus lowest error. Pass if spread ≤ |mpe| and each |error| ≤ mpe.

**E. Eccentricity** `[3.6.2, A.4.7]`
- Rule: indications for different load positions must **meet the mpe** (each position's error versus the mpe at the applied load).
- Place weights carefully: large weights preferred over several small ones; smaller weights on top of larger; load applied centrally in the segment for a single weight, or spread uniformly over the segment for several small weights. It is enough to load the eccentric segments (not the centre).
- **The load position must be marked on a sketch in the Test Report** `[A.4.7]`.
- Error per position by the changeover method; E0 is the zero error taken before each measurement (normally at the beginning, but before each eccentric loading for special instruments such as class I or high capacity; if the mpe is exceeded, repeat with E0 before each loading). If the instrument has automatic zero-setting or zero-tracking it must **not** be in operation during this test.
- Loading modes:

| Instrument type | Test load | Positions | Clause |
|---|---|---|---|
| Load receptor with **not more than 4 points of support** | **1/3 of (Max + maximum additive tare effect)** | The four quarter-segments of the load receptor, in turn | 3.6.2.1, A.4.7.1 |
| Load receptor with **more than 4 points of support (n)** | **1/(n−1)** of (Max + maximum additive tare effect) | Over each support on an area about 1/n of the receptor surface. If two supports are too close, double the load over twice the area on both sides of their axis | 3.6.2.2, A.4.7.2 |
| **Special receptors** (tank, hopper) with minimal off-centre loading | **1/10** of (Max + maximum additive tare effect) | Each point of support | 3.6.2.3, A.4.7.3 |
| **Rolling loads** (vehicle scale, rail suspension) | Usual rolling load, heaviest and most concentrated one, **not exceeding 0.8 × (Max + maximum additive tare effect)** | Beginning, middle and end of the load receptor in the driving direction, then repeated in the reverse direction if possible (re-zero before changing direction). If the receptor has several sections, test each | 3.6.2.4, A.4.7.4 |
| Mobile instruments | Apply the above as far as applicable; otherwise positions defined by operating conditions | | A.4.7.5 |

- Omission note: if operating conditions mean no eccentric loading can occur, the test may be omitted (record this with a reason).

**F. Discrimination** `[3.8, A.4.8]` (**analog and non-self-indicating only at verification**)
- Performed with **three loads**, for example Min, ½ Max and Max `[A.4.8]`.
- *Non-self-indicating instruments* `[3.8.1, A.4.8.1]`: an extra load of **0.4 × |mpe| at that load** (not less than 1 mg), gently placed or removed at equilibrium, must produce a visible displacement of the indicating element.
- *Self- or semi-self-indicating, analog* `[3.8.2.1]`: an extra load equal to the **|mpe| for the load** (not less than 1 mg) must cause a permanent displacement of the indicating element of at least **0.7 × the extra load**.
- *Digital indication* `[3.8.2.2, A.4.8.2]`: an additional load of **1.4 × d**, gently placed or withdrawn, must change the indication unambiguously. **This applies only to type examination and instruments with d ≥ 5 mg, so it is skipped at verification (8.3.3).**
- Software shows this step only when the indication type is analog or non-self-indicating (and, optionally, digital for type-examination use, off by default).

**G. Sensitivity of a non-self-indicating instrument** `[6.1, A.4.9]`
- With the instrument oscillating normally, an extra load equal to the **mpe for the applied load** (not less than 1 mg) is placed on it; for damped instruments apply with a slight impact. The permanent displacement of the indication is recorded. At least **two loads** (for example zero and Max).
- Conditional step, shown only for non-self-indicating instruments.

**H. Tilt (mobile instruments)** `[4.18, A.5.1.3]` is recorded as an optional pass/fail checkbox with a free-text note in v1.

### 4.11 Test standards (weights) `[3.7]`
- Weights should meet OIML R 111 requirements `[3.7.1]`. Their **error must not exceed 1/3 of the instrument's mpe for the applied load**. If the weights are class E2 or better, their *uncertainty* (not error) may be up to 1/3 of the instrument's mpe, provided the actual conventional mass and estimated long-term stability are taken into account.
- An auxiliary verification device, or a separate auxiliary device, must have errors of at most **1/3** of the instrument's mpe for the applied load. If weights are used, the effect of their errors must not exceed **1/5** of the instrument's mpe for the same load `[3.7.2]`.
- **Substitution at the place of use** `[3.7.3, A.4.4.5]`: any constant load may replace part of the standard weights, provided standard weights of **at least 1/2 Max** are used. If the repeatability error (3 placements of the substitution load near the substitution value) is **not greater than 0.3 e**, the standard weights portion may be reduced to **1/3 Max**; **not greater than 0.2 e**, to **1/5 Max**. Allowed only during verification at the place of use.

### 4.12 Descriptive markings to capture `[7.1]`
- **Compulsory:** manufacturer name or mark; accuracy class (Roman numeral in an oval); Max; Min; e.
- **If applicable:** manufacturer's agent for an imported instrument; serial number; identification of each unit of a multi-unit instrument; type approval mark; software identification (compulsory for software-controlled instruments); d if d < e; maximum additive tare effect T = +…; maximum subtractive tare effect T = −… (if different from Max); counting ratio; range of a digital comparator; ratio between weight platform and load platform; maximum safe load Lim; special temperature limits.
- **Additional markings** (examples): not for direct sales to the public, use exclusively for…, the stamp does not guarantee…, to be used only as follows…

### 4.13 Ambiguities and decisions

| Topic | Decision |
|---|---|
| Boundary condition at a band limit | Upper-inclusive (m = 500 stays in the 0.5 e band) per the "≤" in Table 6. |
| Absolute compliance test | |Ec| ≤ mpe, inclusive (a value exactly at the limit passes). |
| Number arithmetic | Use decimal arithmetic (no binary floating point). Store values in the base unit (grams) with a defined precision. |
| e series check and Min check | Warnings only. |
| Test weight error check | Block "Pass" computation until weights are selected for each accuracy row, or show an explicit warning that the 1/3 rule was not checked. |
| True load L | L = sum of (nominal + certified correction) of the weights placed, if a correction is recorded; otherwise the nominal sum. |
| Sensitivity, tilt | Simple recorded checks in v1. |

---

## 5. Architecture and technology

### 5.1 Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | **Django** (current LTS) | Django auth + groups for roles, ORM for SQLite |
| Relational DB | **SQLite** | All business data: users, owners, instruments, weights, tests, readings, reports |
| Document DB | **MongoDB** (via `pymongo`) | Audit trail and frozen report snapshots only (append-only) |
| Templates | Django templates | The Stitch UI export is converted to templates (Section 9.1) |
| Interactivity | **HTMX** or small vanilla JS | Live row calculation in the test wizard |
| Styling | Tailwind CSS (matches Stitch output) | Print stylesheet for the report |
| Charts | Chart.js | Error-versus-load chart |
| PDF | **WeasyPrint** (HTML to PDF) | The on-screen report preview and the PDF use the same template, so they are identical |
| QR codes | `qrcode` library | Encodes the public verification URL |
| Numbers | Python `Decimal` everywhere | Never floats for loads, errors or limits |

### 5.2 Project layout (Django apps)

```
weighcert/
  config/                 # settings, urls, wsgi
  accounts/               # users, roles, profile (signature image, designation)
  core/                   # lab settings, report numbering, audit logging helpers
  registry/               # owners, instruments, instrument ranges, standard weights
  rules/                  # the rules engine (pure Python, no Django imports), reference data, tests
  inspections/            # test sessions, wizard views, readings, workflow
  reports/                # report issuing, PDF, snapshot, QR, public verification
  templates/              # base layout, partials, pages (converted from Stitch)
  static/
  tests/
```

### 5.3 The most important design rule
**One rules engine, used everywhere.** All limit lookups, error calculations and pass/fail decisions live in the `rules` module as pure functions with no database access. The browser may show an instant preview, but **the server recomputes every value on save with the same engine** and stores the result. The browser's numbers are never trusted. This makes the rules unit-testable against the standard's worked examples (Section 12).

### 5.4 Reference data as data, not code
Table 3 (classification limits), Table 6 (mpe bands) and Table 4 (multi-interval condition) are stored as seeded database tables (`ClassLimit`, `MpeBand`, `MultiIntervalCondition`), each row carrying a **rule-set version** (for example `R76-1:2006`). Every stored calculation records the rule-set version it used. Admins can view these tables but cannot edit them in v1.

### 5.5 Deployment
Gunicorn + Nginx, WhiteNoise for static files, SQLite file on a persistent volume with scheduled backups, MongoDB (Atlas free tier or local). Time zone `Asia/Kolkata`. Secrets in environment variables.

---

## 6. Data model

SQLite tables (Django models). `*` means required. All masses stored as Decimal in **grams**, displayed in the instrument's unit.

### 6.1 Accounts and settings
- **User** (Django user) + **Profile**: role (`inspector`, `officer`, `admin`), full name*, designation, employee ID, signature image, active flag.
- **LabSettings** (single row): lab name*, address*, logo, authority/issuing body text, accreditation or authority number, report number prefix, report footer text, signatories, option `allow_simplified_error` (default false), report number counter and year reset policy.

### 6.2 Registry
- **Owner**: name*, address, contact person, phone, email, GSTIN/ID (optional free text).
- **Instrument**:
  - Identity: owner*, manufacturer*, model, serial number*, type approval / OIML certificate number, software identification and version, year of manufacture, status (`active`, `decommissioned`).
  - Metrological: **accuracy class*** (I / II / III / IIII), **Max***, **Min***, **e***, **d***, unit (mg / g / kg / t) for display, `is_multi_interval`, **indication type*** (`digital`, `analog_self_indicating`, `non_self_indicating`), grading-instrument flag (reduces Min limit to 5 e).
  - Tare and zero: `has_tare_device`, tare type (`additive`, `subtractive`, `both`, `preset`), max additive tare T+, max subtractive tare T−, zero-setting device type (`none`, `initial`, `non_automatic`, `semi_automatic`, `automatic_or_tracking`), `used_for_commercial` flag, maximum safe load Lim, special temperature limits.
  - Load receptor: type (`platform`, `tank_hopper`, `rolling_load`, `other`), number of points of support (default 4), `is_mobile`.
  - Location: place of use, address, gravity zone/note.
  - Derived (computed, read-only): **n = Max / e**, classification check results, instrument ID (auto-generated).
- **InstrumentRange** (one row per partial range; a single-range instrument has one row): instrument*, order*, Max_i*, e_i*, d_i, n_i (computed). Min applies to range 1.
- **TestWeight** (standard weights register): label/ID*, nominal mass*, OIML R 111 class*, certificate number*, certified correction (conventional mass error), expanded uncertainty, calibrated on*, **calibration due date***, active flag. A weight past its due date cannot be selected in a new test.

### 6.3 Inspections (test sessions)
- **TestSession**: instrument*, **inspection type*** (`initial_verification`, `subsequent_verification`, `service_inspection`), **limit multiplier** (1 or 2, derived from inspection type and stored), date*, place type (`place_of_use`, `manufacturer`, `other`), location text, gravity note, ambient notes (optional), inspector*, status (Section 8), overall result (`pass`, `fail`, `incomplete`), remarks, officer comment, rule-set version, created/updated timestamps.
  - Visual inspection (`8.3.2`): class OK, Min/Max/e/d markings match records, software ID checked, module IDs checked, prescribed inscriptions present, place for verification marks present (each yes / no / not applicable with note).
  - Conformity declaration (`8.3.1`): devices operate correctly (zero, tare, calculation), construction and material acceptable, notes.
  - Marking and securing (`8.3.4`): marks applied (yes/no), mark type (stamp / sticker), serial or reference, next due date.
- **SessionWeight**: session*, weight* (the standard weights used), used-in-steps note.
- **ZeroCheck**: session*, indication at zero, ΔL (if changeover), computed E0, within ±0.25 e (computed), initial zero range measured (optional), zero-setting/tracking range measured (optional), range-limit result (computed vs 20 % and 4 % of Max).
- **AccuracyReading**: session*, sequence*, **phase*** (`up`, `down`), tare state (`none`, or tare value and tare kind), applied (net) load L*, weights used (text list), indication I*, ΔL (required when d > 0.2 e unless simplified mode), then computed and stored: m, partial range used, e used, P, E, E0 used, Ec, mpe, result (`pass`/`fail`), weight-error check (`ok`/`warn`).
- **TareCheck** (conditional): session*, tare kind, measured tare-setting error, limit (0.25 e or 0.5 d), result; optional tare-weighing-device comparison reading.
- **RepeatabilityTest**: session*, load*, required count (3 or 6, from class), computed spread, spread limit, result. **RepeatabilityReading**: test*, sequence*, indication*, ΔL, computed error and per-reading result.
- **EccentricityTest**: session*, mode (`up_to_4_supports`, `more_than_4_supports`, `tank_hopper`, `rolling_load`), required test load (computed), actual test load*, E0 basis, positions count, **sketch positions** (stored as labelled points). **EccentricityReading**: test*, position label*, indication*, ΔL, computed E, E0 used, Ec, mpe, result.
- **DiscriminationReading** (conditional): session*, load step* (Min / ½Max / Max), extra load applied, observed (`visible_displacement` yes/no, or displacement measured), required threshold (computed 0.4 × mpe, or mpe with 0.7 × displacement), result.
- **SensitivityReading** (conditional): session*, load*, extra load (= mpe), displacement recorded, result (recorded pass/fail with note).
- **TiltCheck** (mobile only, optional): pass/fail + note.

### 6.4 Reports
- **Report**: session* (one-to-one per revision), report number* (unique), revision* (0 for the first issue), status (`issued`, `superseded`), issued at, approved by, PDF file path, **snapshot hash** (SHA-256), **verification token** (random, unguessable), supersedes (previous report).

### 6.5 MongoDB collections (append-only)
- **audit_log**: timestamp, user id and name, action (`create`, `update`, `delete`, `submit`, `approve`, `return`, `issue`, `login`, `export`), entity type, entity id, **before** and **after** values, IP address, `prev_hash` and `hash` (each entry hashes its content plus the previous entry's hash, making any removal or edit detectable).
- **report_snapshots**: report id, report number, revision, **canonical JSON** of the full report content as issued (instrument, session, all readings with computed values, weights with certificate numbers, lab details, rule-set version), SHA-256 of that JSON.

### 6.6 Seeded reference tables
- **ClassLimit**: class, e-range condition, n_min, n_max, Min factor (Table 3).
- **MpeBand**: class, m upper bound (nullable for open-ended), factor (0.5 / 1.0 / 1.5) (Table 6).
- **MultiIntervalCondition**: class, minimum Max_i / e_(i+1) (Table 4: 50,000 / 5,000 / 500 / 50).
- **RuleSet**: version label (for example `R76-1:2006`), effective date, notes.

---

## 7. Rules engine specification

All functions are pure (inputs in, results out), use Decimal, and have no side effects.

### 7.1 Instrument validation
Given class, Max, Min, e, d, ranges:
1. n = Max / e. Check n_min ≤ n ≤ n_max for the class and e-range (Table 3). Out of range gives a warning.
2. Check d < e ≤ 10 d (class I exception for d < 1 mg). Check e belongs to the 1/2/5 × 10^k series (warning).
3. Check Min ≥ Min factor × d (reduced factor 5 for grading instruments).
4. Multi-interval: e_(i+1) > e_i for every range; every range's n_i within Table 3; for each range except the last, Max_i / e_(i+1) ≥ the Table 4 value; Min_i = Max_(i−1).
5. Return a list of findings (code, severity, message, clause).

### 7.2 mpe lookup
Inputs: class, e (or range list), load L, limit multiplier (1 or 2).
1. Choose the partial range (single range = the only range). A load equal to Max_i belongs to range i. A load above Max (plus the maximum additive tare effect where relevant) is flagged as out of range.
2. m = L / e_i.
3. Find the band in Table 6 for the class (upper-inclusive). If m is above the last band, return an "outside class limits" error (do not extrapolate).
4. mpe = factor × e_i × limit multiplier.
5. Return mpe, m, the range used, e used and the factor.

### 7.3 Error calculation
Inputs: indication I, applied load L, d, e (e_i), ΔL (optional), E0, mode flags.
- If d > 0.2 e: ΔL is required (unless simplified mode is enabled in settings). P = I + ½ e − ΔL; E = P − L. The "½ e" term for a multi-interval instrument uses the e of the range in which I + e falls.
- Else: E = I − L.
- Ec = E − E0 (E0 = 0 when no zero correction is available, and the report flags that).
- Result: pass if |Ec| ≤ mpe.

### 7.4 Test-specific evaluations
- **Zero:** compute E0. Pass if |E0| ≤ 0.25 e (use e1 for multi-interval). Optional range checks against 20 % and 4 % of Max.
- **Accuracy:** evaluate each row (7.3). Completeness check (7.5). Test result = pass only if all rows pass.
- **Repeatability:** compute each weighing's error; spread = max − min; pass if spread ≤ |mpe| at the load and every |error| ≤ mpe.
- **Eccentricity:** required load by mode (Section 4.10 E); each position evaluated per 7.3; pass only if all positions pass. Warn if the actual test load differs from the required load by more than the practical rounding of available weights (for example more than 10 %). [DECISION]
- **Tare:** tare-setting error ≤ 0.25 e (electronic or analog) or ≤ 0.5 d (mechanical with digital indication); weighing rows evaluated on **net load**.
- **Discrimination:** analog non-self-indicating: visible displacement for an extra load of 0.4 × |mpe|; analog self-indicating: displacement ≥ 0.7 × extra load for an extra load equal to |mpe|; extra load never below 1 mg. Three load steps. Digital: skipped at verification.
- **Overall result:** pass only if **every applicable test passes** and all mandatory tests exist. Failing a mandatory check yields `fail`; missing mandatory data yields `incomplete`. The first failing item per test is surfaced in the summary with its row and reason.

### 7.5 Suggested loads and completeness check (wizard helper)
Generate the suggested accuracy load list:
1. Always include **Max** and 0 (zero point is covered by the zero check).
2. Include **Min** only if Min ≥ 100 mg.
3. Include loads at and just above each mpe band boundary for the class (for class III: 500 e and about 2,000 e; for every partial range in a multi-interval instrument).
4. Fill with evenly spaced loads to reach the minimum count (5 for verification, user-adjustable upward).
5. The same loads are used going **down** (decreasing phase), ending at zero.
Completeness check blocks submission if Max is missing in either phase or if fewer than the required number of load points exist (counted separately for up and down).

### 7.6 Weight-error check
For each accuracy row, the selected weights' combined error (sum of absolute certified corrections, or sum of class tolerances if no certificate correction is recorded) must be at most **1/3 of the instrument mpe** at that load `[3.7.1]`. Class E2 or better weights may use uncertainty instead. Show a green tick or amber warning per row. [DECISION] This is a warning in v1, and the report lists the weights used with certificate numbers.

---

## 8. Workflow and statuses

```
Draft ──submit──► Submitted ──approve──► Issued (locked)
  ▲                  │
  └────── return ────┘ (officer comment required)
Issued ──revise──► new Draft (revision n+1); the old report becomes Superseded on issue of the new one
```

Rules:
- **Draft / Returned:** the inspector can edit all data in the session.
- **Submitted:** read-only for the inspector; the Officer can approve or return with a mandatory comment (the Officer cannot edit any data).
- **Approve** generates: the report number, the PDF, the snapshot (SQLite hash + MongoDB document), the verification token and QR code. This is atomic; if any part fails nothing is issued.
- **Issued:** completely locked. Even Admin cannot edit it. A correction means creating a **revision**: a new session copied from the issued one, reviewed and issued as `<same number>` revision n+1; the earlier revision is marked **Superseded** and the verification page shows a clear "superseded by revision n+1" banner.
- Report numbers are `PREFIX/YEAR/000001`, generated in a database transaction so numbers never repeat or skip silently.
- A session cannot be submitted unless: mandatory tests are complete, weights are selected and in calibration, instrument passes registration (warnings are allowed but listed), and visual inspection and conformity are filled.

---

## 9. Pages and UI specification

Desktop-first (1440 px design width, usable down to 1280 px). Left sidebar navigation, top bar with global search and a "New Test" button. **11 pages only.**

### 9.1 Stitch UI reference and how to use it
- Use the Stitch designs as the **visual source of truth**: layout, spacing, colours, typography, component styling.
- Convert each Stitch screen into a Django template that extends one `base.html` (sidebar + top bar). Repeated pieces (stat card, status chip, data table, form field, stepper, banner) become template partials.
- **Behaviour, field lists, validation and colours for states come from this document.** If Stitch shows something not listed here (for example a notification bell), leave it out.
- Suggested Stitch screen list (one screen each): Login, Dashboard, Instruments list, Instrument form, Instrument detail, Test wizard (Instrument/Conditions step, Zero step, Accuracy step, Repeatability step, Eccentricity step, Discrimination/Tare step, Review step), Report preview, Reports archive, Public verification, Standard weights, Settings.
- **Design tokens:** light theme; white cards on a soft grey background; one deep-blue primary; **green = pass, red = fail, amber = warning, grey = not applicable/incomplete**; clean sans-serif (Inter-like); tabular, right-aligned numerals in data tables; generous spacing; fine row dividers; no decorative illustrations.
- **Status chips:** Draft (grey), Submitted (blue), Returned (amber), Issued (green), Superseded (grey outline), PASS (green), FAIL (red), INCOMPLETE (amber).

### 9.2 Page list

| # | Page | Who | Purpose |
|---|---|---|---|
| 1 | Login | All staff | Sign in; password reset by Admin |
| 2 | Dashboard | Staff | Work overview |
| 3 | Instruments (list) | Staff | Search, filter, open or add |
| 4 | Instrument form and detail | Inspector (create/edit); Officer and Admin (view) | Create, edit, view history of one scale |
| 5 | New Test wizard | Inspector | The core guided test entry |
| 6 | Test review | Inspector, Officer, Admin (view only) | Full result summary; submit, approve, return |
| 7 | Report preview | Staff | A4 report on screen, Download PDF, Print |
| 8 | Reports archive | Staff | Search all issued reports and drafts |
| 9 | Public verification | Public | QR-code landing page |
| 10 | Standard weights | Admin, Inspector (view) | Weight register and calibration due dates |
| 11 | Settings | Admin | Lab details, users, numbering, reference tables, audit log |

### 9.3 Page details

**1. Login**
Username and password only. **No sign-up link.** First login with a temporary password forces a password change. Failed-attempt lockout after 5 tries for 10 minutes. Password reset by the Admin or via a one-time link.

**2. Dashboard**
- Stat cards: Tests in progress (my drafts), Awaiting approval, Passed this month, Failed this month, Weights due for calibration in 30 days.
- "Needs your attention" table: returned tests (inspector) or submitted tests (Officer), oldest first.
- Recent issued reports table with PASS/FAIL chips.
- Quick action: New Test.

**3. Instruments (list)**
Search (serial, owner, manufacturer), filters (class, owner, status), table columns: Instrument ID, Owner, Make/Model, Serial, Class, Max / e, Last tested date, Last result, actions. "Add instrument" button.

**4. Instrument form and detail**
- Form sections: Identity, Metrological data (class, Max, Min, e, d, unit, indication type), Ranges (shown if multi-interval; add/remove partial ranges), Tare and zero devices, Load receptor (type, number of points of support), Location, Markings (type approval no., software ID, T+, T−, Lim, special temperature limits, additional markings).
- **Live panel:** n = Max / e, and a compliance checklist against Table 3 / 3.4.2 / Table 4 with green ticks and amber warnings and the clause number.
- **Owner:** pick existing or add new inline.
- Detail tab: test history table (date, type, result, report number, PDF link) and "Start new test" button.

**5. New Test wizard** (the heart of the product)
Layout: horizontal stepper on top (steps shown depend on the instrument), main entry area on the left, a sticky **live summary panel** on the right (instrument strip, current step result, steps done/pending, overall status). Autosave on every step (a draft is created at step 1). Keyboard-friendly: Tab/Enter moves through cells; Enter on the last cell adds a row.

*Step 1: Instrument and conditions*
- Select instrument (search). Inspection type (initial verification / subsequent verification / service inspection) with a visible note showing the limit multiplier (1× or 2×). Date, place type, location, gravity note.
- Standard weights used (multi-select from active, in-calibration weights; shows class and due date; expired weights are disabled).
- Visual inspection checklist (class, Min/Max/e/d, software ID, module IDs, inscriptions, mark place) and the conformity declaration checklist (zero, tare, calculation devices).

*Step 2: Zero check*
- Indication at zero, ΔL (if required), computed E0, ±0.25 e result chip. Optional zero-range fields. Skipped with a reason if no zero-setting device.

*Step 3: Accuracy test*
- Info strip: Class, Max, Min, e, d, n, inspection type, multiplier.
- **Suggested loads panel** with checkboxes (Max, Min if ≥ 100 mg, loads at each mpe change point, filler loads) and a "Generate rows" button. Rows can also be added manually.
- Data table, two sections **Increasing** and **Decreasing**: Load, Weights used, Indication, ΔL (shown or required per d > 0.2 e), and computed (read-only) columns: Error (Ec), Allowed limit (mpe), Result chip. Computed cells update as soon as the row is complete.
- Row-level hints: weight error warning (1/3 rule), "load outside class limits".
- Right panel: error-versus-load chart with ± mpe step lines, and a row completeness list.
- Tare (conditional): a "Tare values" sub-panel when the instrument has a tare device. The officer adds tare values (the recommended values 1/3–2/3 or 1/3 and 3/3 are suggested), and each tare value gets its own accuracy table on net load, plus the tare-setting accuracy check.

*Step 4: Repeatability*
- Load (default 0.8 Max, editable), required count (3 for III/IIII, 6 for I/II), reading rows. Live spread, spread limit and result chip.

*Step 5: Eccentricity*
- Mode (auto-selected from the instrument's receptor type and number of supports, editable), computed required load and positions, actual load applied. Positions are shown on a **schematic platform sketch**; each position has Indication, ΔL, computed error, mpe, result. Option to mark the test as not applicable with a mandatory reason.

*Step 6: Discrimination and other conditional tests*
- Shown only for analog/non-self-indicating instruments (discrimination at three loads, sensitivity at two loads) and mobile instruments (tilt checkbox). For digital instruments this step shows an info note: "Not applicable for digital indication at verification (R 76-1, 8.3.3)" and is skipped.

*Step 7: Remarks and finish*
- Remarks text, marking and securing details, then "Go to review".

**6. Test review**
- Big overall banner: PASS (green), FAIL (red) or INCOMPLETE (amber).
- Collapsible section per test with the full tables and the first failure highlighted.
- Warnings list (instrument registration warnings, weight warnings, missing optional data).
- Buttons by role and status: Inspector: Edit / Submit for approval. Officer: Approve and issue / Return (comment required). Admin: view only.
- Audit timeline (who did what, when).

**7. Report preview**
A4 "paper" on a grey canvas, exactly the PDF template. Buttons: Download PDF, Print, Copy verification link, (if issued) Create revision. Shows a "Draft preview, not valid" watermark until issued.

**8. Reports archive**
Filters: date range, result, report status, owner, serial number, report number, inspector, inspection type. Table with report number, date, owner, instrument, result, status, PDF download, view. Export the filtered list to CSV.

**9. Public verification** (no login)
Reached by `/verify/<token>` (QR code) or by entering report number + verification code. Shows a centred card:
- **Valid** (green check): report number, revision, issue date, lab name, instrument make/model/serial, class, Max/e, inspection type, result, and "Integrity: matches the issued record".
- **Superseded** (amber banner) with a link to the current revision.
- **Not found or altered** (red).
No test readings or owner address are shown publicly. [DECISION]

**10. Standard weights**
Table: ID, nominal, class, certificate number, certified correction, uncertainty, calibrated on, due date, status chip (OK, due soon, expired). Add / edit / deactivate (Admin).

**11. Settings** (tabs)
- Lab details and logo, signatories.
- Users and roles: create account (name, official email, employee ID, designation, role), send invite or temporary password, change role, deactivate/reactivate, reset password. This is the only place accounts are created.
- Report numbering (prefix, year reset) and `allow_simplified_error` toggle.
- Reference tables (read-only): classification limits, mpe bands, multi-interval condition, rule-set version.
- Audit log viewer with filters and a "verify chain integrity" button.

### 9.4 Form and validation rules (global)
- Numbers: decimal input with the instrument's unit shown beside the field; reject non-numeric; show unit in column headers.
- Loads must be within 0 to Max (+ T+ for tare tests); show "outside class limits" if m exceeds the top mpe band.
- Computed fields are read-only and visually distinct.
- Confirm dialogs: submit, approve, return, create revision, deactivate weight.
- Empty states: concise text and a primary action ("No instruments yet. Add instrument").
- Errors appear next to the field; save is never silently blocked.

---

## 10. Report specification (PDF and on-screen)

One HTML template rendered to PDF with WeasyPrint. A4 portrait, multi-page, header and footer on every page ("Report No. … · Page x of y"). [CONFIRM] Align the layout with R 76-2 when available; the content below is what R 76-1 requires to be recorded.

1. **Header:** lab logo and name, address, authority text, report title ("Test Report: Non-Automatic Weighing Instrument, OIML R 76-1:2006"), report number and revision, issue date, QR code.
2. **Applicant/owner and instrument:** owner, manufacturer, model, serial number, instrument ID, type approval number, software ID, class, Max, Min, e, d, n, ranges (if multi-interval), indication type, tare/zero devices, load receptor type and supports, location of use, gravity note.
3. **Inspection details:** type (initial verification / subsequent verification / service inspection) and the applied limit multiplier, date, place, inspector, approving officer.
4. **Standard weights used:** table (ID, nominal, class, certificate number, due date).
5. **Visual inspection and conformity:** checklist results.
6. **Zero check:** E0 and result.
7. **Accuracy test:** table with Load, Indication, ΔL (where used), P, Error E, E0, corrected error Ec, mpe, Result, grouped by increasing/decreasing and by tare value; error-versus-load chart.
8. **Tare checks** (if applicable).
9. **Repeatability:** readings, spread, limit, result.
10. **Eccentricity:** **sketch of the load positions** (required by A.4.7), readings, errors, limits, results.
11. **Discrimination / sensitivity / tilt** (if applicable), or "Not applicable" with the clause reference.
12. **Overall result** (large PASS / FAIL banner) and remarks.
13. **Marking and securing:** marks applied, type, reference, next due date.
14. **Notes block:** rule set used (`R76-1:2006`), "error limits are twice the initial verification limits" if service inspection, "rounding error not eliminated" if simplified mode was used.
15. **Signatures:** inspector and officer names, designation, signature images, dates.
16. **Footer:** verification URL, snapshot hash prefix, "This report is not valid if altered", page numbers.

Filename: `NAWI_<ReportNo>_<Serial>_rev<N>.pdf`.

---

## 11. URLs, security and non-functional requirements

### 11.1 Main URL structure
`/login`, `/` (dashboard), `/instruments/`, `/instruments/new`, `/instruments/<id>/`, `/instruments/<id>/edit`, `/tests/new?instrument=<id>`, `/tests/<id>/step/<name>`, `/tests/<id>/review`, `/tests/<id>/submit`, `/tests/<id>/approve`, `/tests/<id>/return`, `/tests/<id>/revise`, `/reports/`, `/reports/<id>/`, `/reports/<id>/pdf`, `/verify/<token>` (public), `/weights/`, `/settings/` (+ tabs), `/api/rules/preview` (live calculation endpoint, authenticated).

### 11.2 Security
- Django auth, session cookies (HttpOnly, SameSite, Secure in production), CSRF on every form and AJAX/HTMX request.
- Role checks on every view; object-level checks (an inspector sees only what the lab allows; configurable).
- Verification token: at least 128 bits of randomness. The public page confirms authenticity by recomputing the snapshot hash and comparing it with the stored hash and the MongoDB snapshot.
- **Audit:** every create/update/delete and every status change logged to MongoDB with before/after and the hash chain. Admin "verify chain" detects tampering.
- Uploads (logo, signature): images only, size and type checked.
- Rate limiting on login and on the public verification endpoint.
- Backups: daily SQLite backup, MongoDB backup; restore procedure documented.

### 11.3 Other non-functional requirements
- Accuracy: Decimal arithmetic end to end; rules engine covered by unit tests with the standard's examples.
- Performance: wizard calculations under 200 ms per request; PDF generation under 5 seconds for a typical report.
- Usability: full keyboard entry in readings tables; no data loss on refresh (autosave); print-friendly CSS.
- Browser support: current Chrome, Edge, Firefox; laptop screens 1280 px and up.
- Localisation: English in v1. Text kept in translation files so Hindi can be added later.

---

## 12. Testing plan

### 12.1 Mandatory golden tests for the rules engine
All values must match exactly (Decimal).

**mpe, initial or subsequent verification (multiplier 1)**

| Class | e | Load | m | Expected mpe |
|---|---|---|---|---|
| III | 1 g | 0 g | 0 | 0.5 g |
| III | 1 g | 500 g | 500 | 0.5 g |
| III | 1 g | 501 g | 501 | 1.0 g |
| III | 1 g | 2,000 g | 2,000 | 1.0 g |
| III | 1 g | 2,001 g | 2,001 | 1.5 g |
| III | 1 g | 10,000 g | 10,000 | 1.5 g |
| III | 1 g | 10,001 g | 10,001 | error: outside class limits |
| II | 0.1 g | 500.0 g | 5,000 | 0.05 g |
| II | 0.1 g | 500.1 g | 5,001 | 0.10 g |
| II | 0.1 g | 2,000.0 g | 20,000 | 0.10 g |
| II | 0.1 g | 2,000.1 g | 20,001 | 0.15 g |
| IIII | 10 g | 500 g | 50 | 5 g |
| IIII | 10 g | 510 g | 51 | 10 g |
| IIII | 10 g | 2,010 g | 201 | 15 g |
| I | 1 mg | 50 g | 50,000 | 0.5 mg |
| I | 1 mg | 50.001 g | 50,001 | 1.0 mg |
| I | 1 mg | 200.001 g | 200,001 | 1.5 mg |

**Service inspection (multiplier 2):** class III, e = 1 g: load 500 g gives 1.0 g; load 2,001 g gives 3.0 g.

**Multi-interval** (class III, 2 / 5 / 15 kg, e = 1 / 2 / 10 g): 500 g gives 0.5 g; 1,500 g gives 1 g; 3,000 g gives 2 g; 4,500 g gives 3 g; 10,000 g gives 10 g; load exactly 2,000 g belongs to range 1 and gives 1 g; load exactly 5,000 g belongs to range 2 and gives 3 g.

**Changeover error (official example):** e = d = 5 g, L = 1,000 g, I = 1,000 g, ΔL = 1.5 g, E0 = +0.5 g. Expected P = 1,001 g, E = +1 g, Ec = +0.5 g. Class III mpe at m = 200 is 2.5 g, so **PASS**. Variants: Ec = +2.5 g **PASS** (boundary, inclusive); Ec = +2.6 g **FAIL**; Ec = −2.5 g **PASS**.

**Classification (Table 3):** class III, e = 1 g, Max = 10 kg gives n = 10,000 (valid); Max = 10.001 kg gives n = 10,001 (warning); class III, e = 5 g, Max = 2 kg gives n = 400 (warning, below 500); class IIII, e = 10 g, Max = 10 kg gives n = 1,000 (valid).

**Repeatability:** class III (3 weighings) with errors +0.5, 0.0, +1.0 at a load where mpe = 1.0 e: spread 1.0 e, **PASS**; errors +0.5, −0.5, +1.0 gives spread 1.5 e, **FAIL** (also check the single-reading limit).

**Eccentric load:** four-support receptor, Max = 10 kg, T+ = 0: required load = 1/3 × 10 kg ≈ 3.33 kg. Six-support receptor: 1/(6−1) = 1/5 of (Max + T+). Tank/hopper: 1/10 of (Max + T+). Rolling load: cap 0.8 × (Max + T+).

### 12.2 Other tests
- **Unit:** rule-set seeding, completeness check, suggested loads generator, weight-error check, hash and canonical-JSON functions.
- **Workflow:** every status transition and every forbidden transition (for example an inspector approving their own test, editing an issued report).
- **Permissions:** every role against every page.
- **Integration:** full path from instrument creation to issued PDF; QR link opens a valid verification page; modifying a stored value makes the verification page show "altered".
- **Visual:** PDF render check across class I/II/III/IIII, single-range and multi-interval, pass and fail cases, with and without tare.
- **Concurrency:** two approvals at the same time never issue the same report number.

---

## 13. Implementation phases with acceptance criteria

**Phase 0: Setup (1 to 2 days)**
Repository, Django project and apps, SQLite and MongoDB connections, environment config, base layout converted from Stitch (sidebar, top bar), authentication with the three roles.
*Done when:* users can log in and see role-appropriate empty pages.

**Phase 1: Rules engine and reference data (3 to 5 days)**
`rules` module, seeded Table 3 / Table 6 / Table 4, rule-set version, all golden tests from Section 12.1 passing.
*Done when:* the entire golden test table passes with no failing case.

**Phase 2: Registry (3 to 4 days)**
Owners, instruments with validation panel, multi-interval ranges, standard weights with due-date logic, instruments list and detail.
*Done when:* an instrument can be created, validated against Table 3, and a weight past due cannot be selected.

**Phase 3: Test wizard (8 to 10 days)**
Steps 1 to 7 with live calculation endpoint, suggested loads, autosave, conditional steps (tare, discrimination, sensitivity, tilt), completeness check, test review page.
*Done when:* a complete class III single-range test and a multi-interval test can be entered and every computed value matches hand calculation.

**Phase 4: Reports (5 to 6 days)**
Report template, PDF generation, eccentricity sketch, chart, report numbering, snapshot hash, MongoDB snapshot, QR code, public verification page, archive with search and CSV export.
*Done when:* an issued PDF is produced, its QR link verifies, and editing the database value makes the verification page report "altered".

**Phase 5: Workflow and audit (3 to 4 days)**
Submit / approve / return, role enforcement (inspector / officer / admin), lock on issue, revisions and superseding, MongoDB audit log with hash chain and verification, dashboard.
*Done when:* all transitions are enforced and the audit log records each action.

**Phase 6: Polish and hardening (3 to 4 days)**
Admin settings page, security review, rate limiting, accessibility pass, print CSS, seed demo data (a few instruments, weights and sample reports), user guide, backup scripts, deployment.
*Done when:* a new user can run the whole flow without help and the deployment checklist passes.

**Total:** roughly 5 to 6 weeks for one developer; the core usable product (Phases 0 to 4) is reachable in about 3 to 4 weeks.

### 13.1 Definition of done (whole project)
- Every golden test passes; no calculation exists outside the rules engine.
- Server recomputes all values on save; browser values are previews only.
- Issued reports are immutable and independently verifiable.
- Only the 11 listed pages exist.
- An Officer can reproduce any reported error by hand from the stored readings and the formulas in Section 4.

---

## 14. Open questions

1. **R 76-2 report format:** [CONFIRM] obtain it and align Section 10 (field order, wording, tables).
2. **Competition scope:** [CONFIRM] does the problem expect type-approval tests, a government portal integration, or specific instrument types only?
3. **Simplified error mode:** keep default off (compliant) or default on for easier demos? Current default: off.
4. **Public verification privacy:** which fields may be shown publicly? Current default: minimal (Section 9.3, page 9).
5. **Language:** English only for v1, or Hindi and English reports?
6. **Test weight uncertainty handling:** certificate-based correction versus class tolerance when no certificate correction is available (Section 7.6).
7. **Eccentricity test load tolerance:** the practical tolerance when the exact fraction of Max cannot be made from available weights (Section 7.4, current warning at 10 %).

---

## 15. Glossary

- **NAWI:** Non-Automatic Weighing Instrument; a scale where an operator places the load and reads the result.
- **OIML R 76:** the international recommendation on non-automatic weighing instruments (R 76-1 requirements and tests; R 76-2 test report format).
- **Verification:** an official check that an instrument meets legal requirements (initial: before first use; subsequent: periodic).
- **Service inspection:** a check of an instrument already in use, with limits doubled.
- **Changeover point:** the load at which the displayed value steps from one interval to the next; used to remove rounding error.
- **Tare:** a weight (container) subtracted from the gross reading so that only the net load is weighed.
- **mpe:** maximum permissible error.
