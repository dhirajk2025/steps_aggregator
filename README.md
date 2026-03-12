# Steps Aggregator

AI-assisted workflow for keeping platform API development processes up to date at ID.me.

## What This Is

A knowledge base + compliance checklist system for new platform API development. Ensures every new API follows all required processes: Legal/Privacy review, API Council, ARB, ADR, Threat Modeling, Data Retention, and Production Readiness Review (PRR).

## How It Works

1. **Process documents** (Confluence pages, PDFs) are ingested into ChromaDB for semantic search
2. **Beads** tracks per-API compliance as a two-tier epic structure: suite-level + per-API
3. **AI agents** can query the knowledge base, audit GitHub repos, and detect compliance gaps
4. **Jira integration** (once API permissions are configured) cross-references tickets against checklist items

## Knowledge Base (ChromaDB: `idme-processes`)

| Category | Documents |
|----------|-----------|
| PRR | Process overview, GoLive MVP checklist (12 items), Fast Follow, Planning |
| API Standards | Building APIs guide (philosophy, design standards, observability, async) |
| API Versioning | ADR 003 — /v1 path + idme-version header strategy |
| API Council | Operating guide — when/how to get review, what to prepare |
| ARB | Process template v2.1, example submission, ADR vs ARB guide |
| ADR | ID.me RFC, AWS ADR process guide |
| Threat Modeling | Trigger criteria, required inputs, expected outputs |
| Data Retention | DRS design doc — team obligations, schema requirements, YAML contracts |
| Legal/Privacy/Compliance | Informal process captured from team knowledge |
| QA Strategy | AI-generated test cases, dev ownership, manual QA scope |

## Compliance Checklist Structure

### Template Epic (`steps_aggregator-2bj`)

Reusable 26-issue template across 8 phases. Copy this for each new platform API.

| Phase | Items |
|-------|-------|
| 1. Design/Planning | Legal+Privacy ticket, Compliance ticket, PRD, QA test cases |
| 2. API Council | Prepare artifacts, get async approval (#api-council) |
| 3. Architecture | ARB shepherd+pre-read, ARB approval, ADR(s) |
| 4. Security | Submit threat model, all findings addressed |
| 5. Build | OpenAPI spec, /v1 versioning, observability, E2E tests, CI/CD |
| 6. Data Retention | deleted_at schema, DRS YAML contract, staging test |
| 7. PRR | SRE JIRA ticket, deploy/rollback plan, runbooks, sign-off |
| 8. Fast Follow | Load testing, DR/BCP, data retention verified |

### Two-Tier Structure for Multi-API Services

For services that expose multiple APIs (e.g., Face API suite), use a **suite-level epic** + **per-API child epics**:

```
Suite Epic (e.g., steps_aggregator-88v)        ← Legal, ARB, PRR, DRS — done once
├── API Epic: Face Enroll                       ← OpenAPI spec, E2E tests, Observability, CI/CD
├── API Epic: Face Compare
├── API Epic: Face Search
├── API Epic: Face Delete
├── API Epic: Face Catalog (Create/List/Delete)
└── API Epic: Face Liveness Check
```

Suite-level items (Legal, Compliance, PRD, ARB, API Council, Threat Model, DRS, PRR) apply to the whole service.
Per-API items (OpenAPI spec, E2E tests, Observability/SLOs, CI/CD) apply to each individual API.

## Auditing an Existing Service

To audit whether an existing service has met compliance requirements:

### 1. GitHub Repo Scan (automated)
Clone the repo (read-only) and check for:
- `openapi-schema/` or `**/openapi.yaml` — OpenAPI specs
- `**/features/*.feature` — Cucumber E2E tests
- `.github/workflows/` — CI/CD pipelines
- `Dockerfile` — container image tagging
- `persistence/**/changesets/` — DB migrations (deleted_at, user_uuid)
- `local-app-instance/otel-*.yml` — observability config

### 2. Jira Search (requires `read:jira-work` scoped token + Browse Issues permission)
```bash
export JIRA_TOKEN="your-token"
export JIRA_EMAIL="your@id.me"
# Search for compliance tickets across IGAV, DEVLEG, COMP, BIO projects
```

### 3. Confluence Search (requires Confluence API token)
```bash
python3 scripts/confluence_ingest.py
```

## Face API Audit Findings (hydra repo)

| Item | Status | Notes |
|------|--------|-------|
| E2E tests — Enroll | ✅ | `SaveFaceTemplate.feature`, `FaceEnrollContentTypes.feature` |
| E2E tests — Compare | ✅ | `CompareFaceTemplates.feature` |
| E2E tests — Search | ✅ | `SearchFaceTemplate.feature` |
| E2E tests — Delete | ✅ | `DeleteFaceTemplate.feature` |
| E2E tests — Catalog | ✅ | `FaceCatalogManagement.feature` |
| E2E tests — Liveness | ⚠️ | Has `FaceLivenessIT.java` but no Cucumber feature file |
| OpenAPI spec — Enroll | ⚠️ | Internal Paravision adapter spec only; no public-facing spec |
| OpenAPI spec — Compare/Search/Delete/Catalog/Liveness | ❌ | Not found in repo |
| CI/CD pipelines | ✅ | GitHub Actions: build, release, integration tests, lint, coverage |
| Container image tagging | ✅ | Maven auto-versions on merge; SNAPSHOT → release promotion |
| Observability config | ⚠️ | OTel + Prometheus in local dev only; Grafana/Honeycomb managed externally |
| DB schema — deleted_at | ✅ | Present on face_records, face_catalogs, cataloged_face_records, inspections |
| DRS — delete strategy | 🚩 | Schema uses **soft delete** (`deleted_at IS NULL`); biometric data requires **hard delete** per DRS policy |

## Scripts

### `scripts/confluence_ingest.py`

Fetches Confluence pages, detects version changes, and saves content for ChromaDB ingestion.

**Setup:**
```bash
export CONFLUENCE_EMAIL="your@idme.com"
export CONFLUENCE_API_TOKEN="your-token"
export CONFLUENCE_BASE_URL="https://idmeinc.atlassian.net"
pip3 install requests
```

**Run:**
```bash
python3 scripts/confluence_ingest.py
```

**Tracked pages:**
- Production Readiness Review Process (`4034101286`)
- Threat Modeling Service (`2512158864`)
- API Council Operating Guide (`4100390931`)
- Building APIs Guide (`3935502401`)
- ADR 003 — Versioning (`4039540737`)

Add new pages to `PAGES_TO_TRACK` in the script.

## Adding New Processes

1. If it's a Confluence page: add the page ID to `PAGES_TO_TRACK` in `confluence_ingest.py`
2. If it's a PDF: export and run through `pdf-chromadb-processor` agent
3. If it's undocumented: describe it in a ChromaDB document with `source: team_knowledge`
4. Once ingested, re-query ChromaDB to update the Beads epic checklist if needed

## Important Notes

- **Revoke API tokens** after use — never commit tokens to git
- PDF process documents are excluded from git (internal company docs)
- ChromaDB collection: `idme-processes`
- Beads prefix: `steps_aggregator`
- Jira API requires `read:jira-work` scoped classic token + Browse Issues project permission
