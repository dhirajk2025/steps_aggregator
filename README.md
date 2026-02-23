# Steps Aggregator

AI-assisted workflow for keeping platform API development processes up to date at ID.me.

## What This Is

A knowledge base + compliance checklist system for new platform API development. Ensures every new API follows all required processes: Legal/Privacy review, API Council, ARB, ADR, Threat Modeling, Data Retention, and Production Readiness Review (PRR).

## How It Works

1. **Process documents** (Confluence pages, PDFs) are ingested into ChromaDB for semantic search
2. **Beads** tracks the per-API compliance checklist as a structured epic with dependencies
3. **AI agents** can query the knowledge base to generate checklists, answer questions, and detect process gaps

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

## New Platform API Checklist (Beads Epic: `steps_aggregator-2bj`)

26 issues across 8 phases:

1. **Design/Planning** — Legal+Privacy ticket, Compliance ticket, PRD, QA test cases
2. **API Council** — Prepare artifacts, get async approval (#api-council)
3. **Architecture** — ARB shepherd+pre-read, ARB approval, ADR(s)
4. **Security** — Submit threat model, all findings addressed
5. **Build** — OpenAPI spec, /v1 versioning, observability, E2E tests, CI/CD
6. **Data Retention** — deleted_at schema, DRS YAML contract, staging test
7. **PRR** — SRE JIRA ticket, deploy/rollback plan, runbooks, sign-off
8. **Fast Follow** — Load testing, DR/BCP, data retention verified

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

- **Revoke the API token** used during setup and generate a fresh one for automation
- PDF process documents are excluded from git (internal company docs)
- ChromaDB collection: `idme-processes`
- Beads prefix: `steps_aggregator`
