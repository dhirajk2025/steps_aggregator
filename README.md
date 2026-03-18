# Steps Aggregator

AI-assisted workflow for keeping platform API development processes up to date at ID.me.

## What This Is

A knowledge base + compliance checklist system for new platform API development. Ensures every new API follows all required processes: Legal/Privacy review, API Council, ARB, ADR, Threat Modeling, Data Retention, and Production Readiness Review (PRR).

## How It Works

1. **Process documents** (Confluence pages, Google Docs, PDFs) are ingested into ChromaDB for semantic search
2. **Beads** tracks per-API compliance as a two-tier epic structure: suite-level + per-API
3. **AI agents** can query the knowledge base, audit GitHub repos, and detect compliance gaps
4. **Daily monitor** checks Confluence page versions, Google Doc staleness, and Jira epic status changes

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
| Face API | PRR doc, Enroll/Search/Delete/Compare/Liveness/Catalog/Trait API specs, ARB, DRS policy, load test results |

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

## Face API Compliance Status (PM-1313)

Jira initiative: [PM-1313 — Biometrics (Faces)](https://idmeinc.atlassian.net/browse/PM-1313)

### Completed Epics (IGAV project)

| Epic | Description | Owner |
|------|-------------|-------|
| IGAV-704 | Face Template Storage (Enroll) API | Dhiraj Kulkarni |
| IGAV-761 | Face 1:1 Compare API | Dhiraj Kulkarni |
| IGAV-775 | Face 1:N Search API | Dhiraj Kulkarni |
| IGAV-815 | Face Template Delete API | Dhiraj Kulkarni |
| IGAV-781 | Face API Schema | Dhiraj Kulkarni |
| IGAV-776 | Face API Framework | Dhiraj Kulkarni |
| IGAV-886 | Face Liveness as an API | Gaurav Chaubal |
| IGAV-896 | GRC Review | Gary Winklosky |
| IGAV-899 | Production Readiness (PRR) — approved by Geoffrey Claro 2025-11-25 | Gaurav Chaubal |
| IGAV-953 | Expose Face APIs to Ruby apps | Gary Winklosky |
| IGAV-963 | Face Alignment with Skyfall architecture | Jayesh Mahajan |
| IGAV-1227 | Face API Support for NCR Integration | Gyan Radhakrishnan |

### In-Progress / Open Epics

| Epic | Description | Status | Owner |
|------|-------------|--------|-------|
| IGAV-1189 | Data Retention Work for Face Platform API | Refinement | Dhiraj Kulkarni |
| IGAV-1155 | Face Trait API (POST) | Refinement | Jayesh Mahajan |
| IGAV-1249 | Store Legal ID's face into new catalog | Refinement | Dhiraj Kulkarni |
| IGAV-1091 | Face API Operational Improvements | Refinement | — |
| IGAV-1126 | Face Catalog Management APIs | On Hold | Gyan Radhakrishnan |

## Scheduled Monitoring

A GitHub Actions workflow (`confluence-monitor.yml`) runs daily at 9am UTC. It checks three types of changes:

### 1. Confluence Page Version Changes

Fetches current page versions from Confluence API. On change:
- Calls Claude to summarize what changed and which compliance phases are affected
- Commits updated `versions.json` (auditable history)
- Opens a GitHub issue with review checklist

**Tracked pages** (`versions.json`):
- Production Readiness Review Process (`4034101286`)
- Threat Modeling Service (`2512158864`)
- API Council Operating Guide (`4100390931`)
- Building APIs Guide (`3935502401`)
- ADR 003 — API Versioning Strategy (`4039540737`)

### 2. Google Doc Staleness

Tracks last-ingested date for linked Google Docs. Alerts when a doc hasn't been re-ingested within its `stale_after_days` window.

**Tracked docs** (`versions.json → gdrive_docs`):
- PRR Template (30-day window)
- Face API PRR doc (14-day window) — owner: gaurav.chaubal@id.me
- Face Liveness ARB, Enroll/Search/Delete/Catalog API specs, Data Retention, Load Test Results (30–60 days)

### 3. Jira Epic Status Changes

Polls tracked IGAV epics via Jira REST API. Detects status transitions (e.g., Refinement → In Progress → Complete).

**Tracked epics** (`versions.json → jira_epics`):
| Epic | Phase | Current Status |
|------|-------|----------------|
| IGAV-1189 | Data Retention (DRS) | Refinement |
| IGAV-1155 | Build (Trait API) | Refinement |
| IGAV-1249 | Build (Legal ID catalog) | Refinement |
| IGAV-1091 | Fast Follow (Ops) | Refinement |
| IGAV-1126 | Build (Catalog Mgmt) | On Hold |

### Setup: GitHub Secrets

Add these at `Settings → Secrets and variables → Actions`:

| Secret | Value |
|--------|-------|
| `CONFLUENCE_EMAIL` | `dhiraj.kulkarni@id.me` |
| `CONFLUENCE_API_TOKEN` | Classic Atlassian token (used for both Confluence and Jira REST API) |
| `ANTHROPIC_API_KEY` | Anthropic API key |

### Manual trigger

Go to **Actions → Confluence Compliance Monitor → Run workflow**.

### Local run

```bash
export CONFLUENCE_EMAIL="dhiraj.kulkarni@id.me"
export CONFLUENCE_API_TOKEN="your-token"
export CONFLUENCE_BASE_URL="https://idmeinc.atlassian.net"
export ANTHROPIC_API_KEY="your-key"
pip3 install requests anthropic
python3 scripts/monitor.py
```

Expected output when everything is current: `Result: 0 change(s) detected, 0 Jira epic change(s), 0 stale Google Doc(s)`

### Testing end-to-end

Temporarily lower a version number in `versions.json`, then run the monitor — it will detect the "change" and exercise the full Claude + GitHub issue flow.

## Scripts

### `scripts/monitor.py`

Automated daily monitor. Checks Confluence page versions, Google Doc staleness, and Jira epic status changes. Run by GitHub Actions; also runnable locally.

### `scripts/create_issues.py`

Creates GitHub issues for detected changes. Called by the workflow after `monitor.py` writes `/tmp/monitor-report.json`. Handles Confluence changes, stale Google Docs, and Jira epic status transitions.

### `scripts/confluence_ingest.py`

Manual ingestion script. Fetches Confluence pages, extracts embedded Google Doc links, and saves content for MCP-based ChromaDB ingestion.

```bash
export CONFLUENCE_EMAIL="your@id.me"
export CONFLUENCE_API_TOKEN="your-token"
export CONFLUENCE_BASE_URL="https://idmeinc.atlassian.net"
pip3 install requests
python3 scripts/confluence_ingest.py
```

## Adding New Tracking

### New Confluence page
Add to `PAGES_TO_TRACK` in `confluence_ingest.py` and add an entry to `versions.json`.

### New Google Doc
Add an entry under `gdrive_docs` in `versions.json` with `last_ingested`, `stale_after_days`, and optionally `jira_ticket` and `owner`.

### New Jira epic to monitor
Add an entry under `jira_epics` in `versions.json`:
```json
"IGAV-XXXX": {
  "title": "Epic title",
  "status": "Refinement",
  "owner": "email@id.me",
  "phase": "Build",
  "last_checked": "2026-03-18"
}
```

### New process document (PDF or unstructured)
Export as PDF and run through `pdf-chromadb-processor` agent, or describe it as a ChromaDB document with `source: team_knowledge`.

## Important Notes

- **Revoke API tokens** after use — never commit tokens to git
- PDF process documents are excluded from git (internal company docs)
- ChromaDB collection: `idme-processes`
- Beads prefix: `steps_aggregator`
- The same Atlassian API token works for both Confluence and Jira REST APIs
