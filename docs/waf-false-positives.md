# WAF False Positives — Analysis & Recommended Solution

**Application:** IFRC Network Data Portal (`databank.ifrc.org`)  
**Infrastructure:** Azure Application Gateway + WAF Policy `ifrc-prod-waf-policy01`  
**Rule set:** OWASP CRS 3.2  
**Status:** JSON API refactor complete — WAF path rules pending IT deployment

---

## 1. What is happening

The WAF is running in **Prevention mode** with OWASP CRS 3.2 rules. These rules pattern-match
incoming request parameters for SQL injection, XSS, RFI, and special-character anomalies — without
understanding the application's intent.

The Backoffice routinely POSTs **multilingual JSON blobs** (translation maps, condition logic,
matrix configuration) and **URL strings** as ordinary form fields. CRS rules misclassify this
legitimate data as attacks. Multiple rules fire on the same request, the **anomaly score** (rule
949110) accumulates past the threshold, and the request is **blocked before reaching the Flask
app**.

No real attack was present in any of the blocked transactions reviewed.

---

## 2. Affected URLs and the rules that fire on each

### 2a. `POST /admin/settings`

Blocked repeatedly; anomaly score up to **105**.

| CRS Rule | Trigger |
|----------|---------|
| 931130 | `https://…` URL in `propose_new_indicator_url`, `indicator_details_url_template` |
| 942200 | JSON commas/quotes in translation maps (e.g. `,"es":"<5",`) |
| 942260 | `":"IFRC N` patterns inside JSON strings |
| 942330 | `<5":{"a` — `<5` age group key next to JSON braces |
| 942340 | `"5-17":{"`, `"Male":{"` — nested JSON keys |
| 942370 | `":{"` — any `{"key":{"` nested JSON fragment |
| 942430 | >12 special characters in a single arg (all JSON translation fields) |
| **949110** | **Total score exceeds threshold → BLOCKED** |

### 2b. `POST /admin/items/edit/<id>` (Form Builder — save item)

Blocked; anomaly score 8–44 depending on item complexity.

| CRS Rule | Trigger |
|----------|---------|
| 942200 | `,"conditions":[{"item_id":` in `relevance_condition` JSON |
| 942260 | `label_translations` with long Spanish/French text; `relevance_condition` |
| 942340 | `"logic":"AND"` in `relevance_condition` |
| 942370 | `":[{"` in `relevance_condition`; `"type":"matrix"` in `config` |
| 942430 | Dense JSON in `label_translations`, `config`, `relevance_condition` |
| **949110** | **BLOCKED** |

### 2c. `GET /admin/translations/edit?msgid=…` (Gettext translation editor)

Blocked; anomaly score 5–23. The `msgid` **query parameter** carries raw source strings.

| CRS Rule | Trigger |
|----------|---------|
| 942440 | `-- none --` sentinel → treated as SQL comment |
| 941320 | `<strong>…</strong>` in msgid → XSS |
| 942130 | `strong>Check` — tautology heuristic |
| 942100 | libinjection fires on `%(template)s` Python format string |
| 942150 | `date: %(` — `date` is a SQL function name |
| 942260 | `'%(template)s'` quoted placeholder |
| 942410 | `%(due_date)s` → `date(` SQL pattern |
| 942430 | Multiple `%`, `'`, `(`, `)` in one string |
| **949110** | **BLOCKED** |

---

## 3. Complete inventory of WAF-sensitive parameter names

### Settings page (`/admin/settings`)

**JSON / translation blobs:**
- `document_types_translations`
- `age_groups_translations` ← extra noisy: keys like `<5`, `5-17`, `50+`
- `sex_categories_translations`
- `organization_name_translations`
- `organization_short_name_translations`
- `ai_provider_priority` (JSON array string)
- `template_metadata_json`
- `email_template_suggestion_confirmation_translations`
- `email_template_admin_notification_translations`
- `email_template_security_alert_translations`
- `email_template_welcome_translations`
- `email_template_notification_translations`

**URL strings (931130):**
- `indicator_details_url_template`
- `propose_new_indicator_url`

### Form builder — sections & templates

- `name_translations`
- `page_name_translations`
- `relevance_condition` (JSON rule object)

### Form builder — items

- `label_translations`
- `description_translations`
- `definition_translations`
- `options_json`
- `options_translations_json`
- `list_filters_json`
- `matrix_list_filters_json`
- `config` ← matrix JSON; generic name, most important to disambiguate
- `plugin_config` ← injected by JS for plugin / map items
- `relevance_condition`
- `validation_condition`

### Translation admin (`/admin/translations/edit`)

- `msgid` (query parameter on GET; form field on POST) — carries raw gettext source strings
  including HTML, `--`, Python `%(…)s` placeholders

---

## 4. Why this keeps happening

The WAF inspects **parameter values as text**. CRS has no awareness that:
- `{"es":"<5","fr":"<5"}` is a translation map, not SQL
- `https://indicatorbank.ifrc.org/` is a configured link, not a file-include attack
- `-- none --` is a UI sentinel value, not a SQL comment
- `%(due_date)s` is a Python format string, not a SQL function call

Every one of these is a **true false positive**. No application-layer protection (Flask-WTF,
SQLAlchemy parameterised queries, server-side JSON validation) has any relation to whether CRS
fires — they operate at different layers.

The **root architectural cause** is that structured data (JSON blobs, translation maps, rule
objects) is being sent as ordinary `application/x-www-form-urlencoded` fields — the same wire
format that CRS was designed to inspect for injection attacks. WAF tools at GitHub, Notion, Linear,
Salesforce, and government-facing systems all encounter this problem. The established solutions
are described below.

---

## 5. Options — industry-standard approaches

### Option A — WAF Managed Rule Exclusions (scoped)

Add **per-rule, per-argument-name, per-URI** exclusions to the WAF policy. The WAF continues
inspecting all other parameters normally.

**Pros:**
- No application code changes; can be done by IT team alone
- Narrowest possible blast radius
- Standard first-response for production emergencies

**Cons:**
- Must enumerate every sensitive parameter name (~30 today; grows as features are added)
- Exclusions do not self-document: future developers may not know why a field is excluded
- Must be revisited when new JSON fields are added; easily forgotten

**When used:** Any WAF-protected system as an emergency fix. Also used permanently on legacy
systems where code refactoring is not feasible.

---

### Option B — Convert complex admin POSTs to `application/json` APIs ✅ Best long-term

The root cause is form-encoding structured data. The industry-standard fix is to separate concerns:

| Layer | Protocol | WAF treatment |
|-------|----------|---------------|
| Page navigation, simple CRUD | `application/x-www-form-urlencoded` | Normal CRS, no exclusions |
| Structured data (translations, JSON rules, config) | `application/json` POST to an API path | Relaxed per-path WAF rule |
| File uploads | `multipart/form-data` | Normal CRS |

**How it works in practice:**
1. The JS already uses `fetch` for most form-builder saves. Change the `Content-Type` to
   `application/json` and send a proper JSON body instead of a `FormData` object.
2. Flask handlers receive data via `request.get_json()` instead of `request.form.get()`.
3. On the WAF, one policy rule: *exempt `POST /api/admin/*` from per-argument SQLi/XSS
   inspection for authenticated sessions*. This is a **path-scoped** rule, not a field-name rule.

**Pros:**
- Eliminates the mismatch permanently — WAF never sees structured data as form args
- One WAF policy rule covers all current and future structured-data endpoints
- Cleaner API design; no more large hidden `<input>` fields in HTML
- Self-maintaining: new JSON fields automatically covered by the path rule
- Standard pattern used by GitHub, Notion, Linear, Atlassian, and most SaaS admin UIs

**Cons:**
- Requires a focused development sprint (~2–3 weeks)
- CSRF protection must be passed as a header (`X-CSRFToken`) instead of a hidden field
  (Flask-WTF supports this out of the box)
- Full round of QA needed after the refactor

**Files that need changes (see Section 7 for detail):**
- `Backoffice/app/routes/admin/settings.py` — `request.form.get()` → `request.get_json()`
- `Backoffice/app/routes/admin/form_builder.py` — same for item/section/template saves
- `Backoffice/app/templates/admin/settings/manage_settings.html` — remove hidden inputs, convert
  form submission to `fetch`
- `Backoffice/app/templates/forms/form_builder/partials/_item_modal.html` — same
- `Backoffice/app/static/js/form_builder/modules/item-modal.js` — change fetch payload

---

### Option C — Base64-encode structured field values (no WAF change required)

When the WAF cannot be tuned (e.g. a third-party managed service), some systems encode all
structured values in base64 before POSTing, and decode them in the backend.

```javascript
// Client — encode before submit
formData.set('label_translations', btoa(JSON.stringify(translations)));
```

```python
# Server — decode after receive
import base64, json
raw = request.form.get('label_translations', '')
translations = json.loads(base64.b64decode(raw).decode('utf-8'))
```

Base64 output contains only `[A-Za-z0-9+/=]` — no quotes, braces, colons, or angle brackets.
**CRS has nothing to match on.** This is used by several government-contract systems operating
under strict WAF policies they cannot modify.

**Pros:**
- Requires zero WAF policy changes
- Works even on WAFs completely outside your control

**Cons:**
- Payloads are ~33% larger
- Every affected field needs matching encode/decode pairs in JS and Python
- Encoded values in network logs/form data are harder to debug
- Does not fix the architectural mismatch; only masks it

---

### Option D — Rename parameters with a shared prefix + "starts-with" WAF exclusion

Rename all WAF-sensitive fields to a common prefix (e.g. `wjson_`) in templates, JS, and Flask
routes. Then one Azure exclusion rule — *"exclude args starting with `wjson_`"* — covers all of
them.

| Current name | Proposed name |
|---|---|
| `config` (matrix item) | `wjson_config` |
| `relevance_condition` | `wjson_relevance_condition` |
| `validation_condition` | `wjson_validation_condition` |
| `plugin_config` | `wjson_plugin_config` |
| `*_translations` (all) | `wjson_*_translations` |
| `*_json` (all) | (already clear; keep or add prefix) |
| `ai_provider_priority` | `wjson_ai_provider_priority` |
| `indicator_details_url_template` | `wurl_indicator_details_url_template` |
| `propose_new_indicator_url` | `wurl_propose_new_indicator_url` |

`msgid` should stay (gettext convention); handle via URI-scoped exclusion only.

**Pros:**
- One WAF exclusion rule instead of ~30 individual ones
- Self-documenting: prefix signals "this is structured data, WAF-excluded by design"
- Smaller PR than Option B

**Cons:**
- ~50–80 coordinated file changes (templates, JS modules, Flask route handlers)
- Requires confirming Azure WAF supports "RequestArgNames starts with" exclusions
- Still sends structured data as form fields — does not fix the architectural root cause
- `msgid` and URL fields still need separate treatment

---

### Option E — Lower anomaly score threshold or switch to Detection mode

Raise the block threshold or put WAF in Detection-only mode globally.

**Not recommended.** This weakens protection for all traffic — public endpoints, auth flows, and
upload endpoints — not just the admin paths causing false positives.

---

## 6. Solution — JSON API refactor (implemented)

All four WAF-sensitive POST endpoints now send `Content-Type: application/json` instead of
`application/x-www-form-urlencoded`. CRS rules that fired on form-field argument names no longer
match because the WAF sees a JSON body, not named `ARGS`.

### What was changed

**Shared utilities:**
- `Backoffice/app/static/js/csrf.js` — added `formDataToJson(form)` and `snapshotToJson(snapshot)`
  helpers that convert form inputs to a plain JS object for `JSON.stringify()`.
- `Backoffice/app/utils/request_utils.py` — added `_JsonFormProxy` class, `get_request_data()`,
  `get_request_field()`, and `get_request_list()`. `get_request_data()` returns a proxy that
  behaves identically to `request.form` (`.get()`, `.getlist()`, `in`, `[]`) but reads from the
  parsed JSON body when `Content-Type` is `application/json`.

**Central JS fetch:**
- `Backoffice/app/static/js/form_builder/modules/form-submit-ui.js` — `submitViaAjax` now sends
  `JSON.stringify(snapshotToJson(snapshot))` with `Content-Type: application/json`. Falls back to
  `FormData` if `snapshotToJson` is not available.

**Flask route handlers — all use `data = get_request_data()` instead of `request.form`:**
- `Backoffice/app/routes/admin/form_builder/items.py` — `edit_item`, `new_section_item`,
  `delete_item`, `duplicate_item`, `unarchive_item`
- `Backoffice/app/routes/admin/form_builder/sections.py` — `edit_template_section`,
  `new_template_section`, `delete_template_section`, `duplicate_template_section`,
  `unarchive_section`, `configure_dynamic_section`, `configure_repeat_section`
- `Backoffice/app/routes/admin/form_builder/templates.py` — `edit_template` (Save Template block)
- `Backoffice/app/routes/admin/settings.py` — `manage_settings` POST block

**Section save JS:**
- `Backoffice/app/static/js/form_builder/main.js` — section form submit now uses `formDataToJson`
  and sends JSON via `csrfFetch` with AJAX response handling.

**Settings save JS:**
- `Backoffice/app/templates/admin/settings/manage_settings.html` — settings orchestrator now
  sends `JSON.stringify(formDataToJson(form))` with `Content-Type: application/json`.

**Helper modules (unchanged — already use parameter-based API):**
- `Backoffice/app/routes/admin/form_builder/helpers/item_updaters.py` — receives `request_form`
  parameter, which is now the `_JsonFormProxy` instead of `request.form`.
- `Backoffice/app/routes/admin/form_builder/helpers/item_factories.py` — same pattern.
- `Backoffice/app/routes/admin/form_builder/helpers/template_mgmt.py` — same pattern.

---

## 7. WAF exclusion request for IT

### Step 1 — Ask IT one question first

> *"Is `requestBodyCheck` enabled on the WAF policy, and does CRS inspect JSON request body
> values as `ARGS_JSON`?"*

The answer determines whether you need 1 exclusion or 5.

---

### Always needed (regardless of JSON body inspection)

**Exclusion 1 — `msgid` query parameter on translation editor**

| Field | Value |
|-------|-------|
| URI | `/admin/translations/edit` |
| Methods | GET, POST |
| Match variable | `RequestArgNames` equals `msgid` |
| Rules to exclude | 941320, 942100, 942130, 942150, 942260, 942410, 942430, 942440 |

**Why:** `msgid` is a GET query parameter that carries raw gettext source strings. These strings
contain HTML tags (`<strong>…</strong>`), Python format placeholders (`%(due_date)s`), and
sentinel values (`-- none --`). This triggers XSS (941320), SQL function detection (942100,
942150, 942410), SQL comment detection (942440), and special-character rules (942130, 942260,
942430). This is a GET parameter and cannot be sent as a JSON body.

---

### Only needed if JSON body inspection is ON

If IT confirms that `requestBodyCheck` is enabled **and** CRS inspects JSON body values, add
these 4 path-scoped body exclusions. If JSON body inspection is off, skip them — the JSON body
is opaque to CRS and will not trigger any rules.

**Exclusion 2 — Settings save**

| Field | Value |
|-------|-------|
| URI | `/admin/settings` |
| Method | POST |
| Match variable | `RequestBody` |
| Rules to exclude | 931130, 942200, 942260, 942330, 942340, 942370, 942430 |

**Why:** Settings POST contains translation maps with nested JSON (`{"es":"<5","fr":"<5"}`),
configured URLs (`https://…`), and AI provider priority arrays. Rule 931130 fires on URLs,
942330/942340 on nested JSON keys like `<5` and `"Male"`, and 942430 on high special-character
density in JSON values.

**Exclusion 3 — Form builder item save**

| Field | Value |
|-------|-------|
| URI | `/admin/items/edit/*` |
| Method | POST |
| Rules to exclude | 942200, 942260, 942330, 942340, 942370, 942430 |

**Why:** Item saves contain `label_translations`, `relevance_condition` (JSON rule logic with
`"conditions":[{"item_id":…}]`), `config` (matrix JSON), and `plugin_config`. The nested JSON
structures trigger SQLi detection rules.

**Exclusion 4 — Form builder section save**

| Field | Value |
|-------|-------|
| URI | `/admin/sections/*` |
| Method | POST |
| Rules to exclude | 942200, 942260, 942330, 942340, 942370, 942430 |

**Why:** Section saves contain `name_translations` (JSON) and `relevance_condition` (JSON skip
logic). Same nested-JSON false positive pattern as items.

**Exclusion 5 — Form builder template save**

| Field | Value |
|-------|-------|
| URI | `/admin/templates/edit/*` |
| Method | POST |
| Rules to exclude | 942200, 942260, 942330, 942340, 942370, 942430 |

**Why:** Template saves contain `name_translations`, `page_name_translations` (JSON), and
shared admin IDs. Same nested-JSON false positive pattern.

---

### What stays fully protected (NOT excluded)

- All public endpoints (`/forms/`, `/api/v1/`, website pages)
- All other admin POST paths (user management, assignments, content, analytics, RBAC)
- Authentication flows (`/auth/`, login, password reset)
- File upload endpoints (`multipart/form-data`)
- Query string parameters on the 4 POST paths (only body is exempted)
- All GET requests except the single `msgid` on `/admin/translations/edit`
- All request headers and cookies on every path

### Self-maintaining guarantee

After the JSON API refactor, all structured data (translations, JSON configs, rule logic) is sent
as `Content-Type: application/json` in the request body. Any new JSON field added to settings,
items, sections, or templates in the future is automatically covered by the path-scoped body
exclusion. No WAF update is needed when fields are added or renamed.

---

## 8. Verification after deployment

Test the following actions manually on staging:

| Action | URL | Signals success |
|--------|-----|----------------|
| Save System Configuration with all tabs | `/admin/settings` | Flash "Settings saved", no WAF 403 |
| Save age groups including `<5` entry | `/admin/settings` | As above |
| Save indicator details URL (`https://…`) | `/admin/settings` | As above |
| Save a form item with label translations | `/admin/items/edit/<id>` | Item saved, translations visible |
| Save a matrix item with `config` JSON | `/admin/items/edit/<id>` | Matrix config preserved |
| Add a relevance rule to an item | `/admin/items/edit/<id>` | Rule saved, shows in edit modal |
| Save a section with translations + skip logic | `/admin/sections/edit/<id>` | Section saved |
| Save template details (name, description) | `/admin/templates/edit/<id>` | Template updated |
| Open translation editor with `-- none --` | `/admin/translations/edit?msgid=--+none+--` | Page loads (no 403) |
| Open translation editor with HTML msgid | `/admin/translations/edit?msgid=<strong>…` | Page loads |

Check WAF logs after each action and confirm no **Blocked** entries in `AGWFirewallLogs`.

---

## 9. Security posture note

The JSON API refactor does **not** weaken security on:
- Public-facing endpoints (`/forms/`, `/api/v1/`, website)
- Admin parameters not listed above
- Authentication flows (`/auth/`)
- Upload endpoints

The admin POST endpoints are protected by:
- Flask-WTF CSRF via `X-CSRFToken` header (set by `csrfFetch`)
- Session authentication (admin-only paths with `@permission_required`)
- Strict `json.loads()` parsing with per-field validation in each route handler
- SQLAlchemy parameterised queries for all DB writes
- `_JsonFormProxy` input sanitization (type coercion, validated `.getlist()`)

The WAF's role on JSON body endpoints shifts to DDoS/rate-limiting and header inspection — which
is the appropriate division of responsibility.
