#!/usr/bin/env python3
"""
Confluence Compliance Monitor
Checks tracked Confluence pages for version changes, re-ingests updated content,
calls Claude API to summarize changes, and writes a report for GitHub Actions.

Usage:
    python3 scripts/monitor.py

Environment variables required:
    CONFLUENCE_EMAIL      - Atlassian email (e.g. dhiraj.kulkarni@id.me)
    CONFLUENCE_API_TOKEN  - Atlassian API token
    CONFLUENCE_BASE_URL   - e.g. https://idmeinc.atlassian.net
    ANTHROPIC_API_KEY     - Anthropic API key

Optional:
    CHROMADB_HOST         - ChromaDB host (default: localhost)
    CHROMADB_PORT         - ChromaDB port (default: 8000)
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic
import requests

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.json"
REPORT_FILE = Path("/tmp/monitor-report.json")

# Checklist phases used in Claude's analysis prompt
CHECKLIST_PHASES = [
    "Design/Planning",
    "API Council",
    "Architecture/ARB",
    "Security/Threat Modeling",
    "Build",
    "Data Retention (DRS)",
    "PRR",
    "Fast Follow",
]

# ── Confluence ──────────────────────────────────────────────────────────────────

def fetch_confluence_page(page_id: str) -> dict:
    email = os.environ["CONFLUENCE_EMAIL"]
    token = os.environ["CONFLUENCE_API_TOKEN"]
    base_url = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
    url = f"{base_url}/wiki/rest/api/content/{page_id}?expand=version,body.storage"
    resp = requests.get(url, auth=(email, token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def html_to_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ── ChromaDB (optional — skipped gracefully if unavailable) ────────────────────

def try_ingest_to_chromadb(page_id: str, title: str, version: int, category: str,
                            text: str, doc_id: str) -> bool:
    """Attempt ChromaDB upsert; returns True on success, False if unavailable."""
    try:
        import chromadb as chromadb_lib

        host = os.environ.get("CHROMADB_HOST", "localhost")
        port = int(os.environ.get("CHROMADB_PORT", "8000"))
        client = chromadb_lib.HttpClient(host=host, port=port)

        collection_name = "idme-processes"
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            collection = client.create_collection(
                collection_name,
                metadata={"description": "ID.me engineering process documents from Confluence"},
            )


        # Remove old versions for this page
        try:
            existing = collection.get(where={"page_id": page_id}, include=["metadatas"])
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            pass

        base_url = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
        new_doc_id = f"{doc_id}-v{version}"
        collection.add(
            documents=[text],
            ids=[new_doc_id],
            metadatas=[{
                "title": title,
                "page_id": page_id,
                "version": version,
                "source": "confluence",
                "url": f"{base_url}/wiki/pages/viewpage.action?pageId={page_id}",
                "category": category,
                "ingested_date": date.today().isoformat(),
            }],
        )
        return True
    except ImportError:
        print("  [chromadb] chromadb package not installed — skipping ingestion")
        return False
    except Exception as e:
        print(f"  [chromadb] Unavailable or error — skipping ingestion: {e}")
        return False

# ── Claude analysis ────────────────────────────────────────────────────────────

def summarize_change(title: str, old_version: int, new_version: int, content: str) -> dict:
    """Call Claude to summarize what changed and which phases are affected."""
    client = anthropic.Anthropic()

    phases_list = "\n".join(f"- {p}" for p in CHECKLIST_PHASES)
    prompt = f"""A Confluence process document has been updated:

Title: {title}
Version change: v{old_version} → v{new_version}

Document content (current version):
{content[:8000]}

Please provide:
1. A concise 2-3 sentence summary of what likely changed in this document (based on the current content and the version jump).
2. Which of these compliance checklist phases are most likely affected by this update:
{phases_list}

Respond in JSON with this exact structure:
{{
  "summary": "...",
  "affected_phases": ["Phase1", "Phase2"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    # Extract JSON from response (Claude may wrap in markdown code fences)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return {"summary": raw, "affected_phases": []}

# ── Jira epic status tracking ──────────────────────────────────────────────────

def check_jira_epic_changes(versions: dict) -> list[dict]:
    """Detect status changes in tracked Jira epics. Updates versions in-place."""
    email = os.environ.get("CONFLUENCE_EMAIL", "")
    token = os.environ.get("CONFLUENCE_API_TOKEN", "")
    base_url = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")

    if not all([email, token, base_url]):
        return []

    jira_epics = versions.get("jira_epics", {})
    if not jira_epics:
        return []

    changes = []
    today = date.today().isoformat()

    for epic_key, record in jira_epics.items():
        url = f"{base_url}/rest/api/3/issue/{epic_key}?fields=summary,status,assignee"
        try:
            resp = requests.get(url, auth=(email, token), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            new_status = data["fields"]["status"]["name"]
            old_status = record.get("status", "unknown")
            record["last_checked"] = today

            if new_status != old_status:
                changes.append({
                    "epic_key": epic_key,
                    "title": data["fields"]["summary"],
                    "old_status": old_status,
                    "new_status": new_status,
                    "phase": record.get("phase", ""),
                    "owner": record.get("owner", ""),
                    "url": f"{base_url}/browse/{epic_key}",
                })
                record["status"] = new_status
                print(f"  JIRA CHANGED: {epic_key} {old_status!r} → {new_status!r}")
            else:
                print(f"  {epic_key}: No change ({new_status})")
        except Exception as e:
            print(f"  {epic_key}: Error — {e}", file=sys.stderr)

    return changes

# ── Google Docs staleness check ────────────────────────────────────────────────

def check_stale_gdrive_docs(versions: dict) -> list[dict]:
    """Return list of Google Docs that haven't been re-ingested within stale_after_days."""
    stale = []
    gdrive_docs = versions.get("gdrive_docs", {})
    today = date.today()
    for doc_key, record in gdrive_docs.items():
        last_ingested = date.fromisoformat(record.get("last_ingested", "2000-01-01"))
        stale_after = record.get("stale_after_days", 30)
        if (today - last_ingested) >= timedelta(days=stale_after):
            stale.append({
                "title": record["title"],
                "url": record["url"],
                "last_ingested": record["last_ingested"],
                "days_stale": (today - last_ingested).days,
                "source_confluence_page": record.get("source_confluence_page"),
                "jira_ticket": record.get("jira_ticket"),
                "owner": record.get("owner"),
            })
    return stale

# ── GitHub Actions outputs ─────────────────────────────────────────────────────

def set_github_output(key: str, value: str):
    """Write to GITHUB_OUTPUT if running in GitHub Actions."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            # For multiline values, use EOF delimiter
            if "\n" in value:
                delimiter = "EOF"
                f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                f.write(f"{key}={value}\n")

# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    today = date.today().isoformat()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Confluence compliance monitor starting\n")

    # Load tracked versions
    with open(VERSIONS_FILE) as f:
        versions = json.load(f)

    changes = []
    errors = []

    # Check Jira epic status changes
    print("Checking Jira epics for status changes...")
    jira_changes = check_jira_epic_changes(versions)
    if jira_changes:
        print(f"⚠️  {len(jira_changes)} Jira epic(s) changed status:")
        for j in jira_changes:
            print(f"  - {j['epic_key']} ({j['title']}): {j['old_status']} → {j['new_status']}")
    print()

    stale_gdrive = check_stale_gdrive_docs(versions)
    if stale_gdrive:
        print(f"⚠️  {len(stale_gdrive)} stale Google Doc(s) need re-ingestion:")
        for doc in stale_gdrive:
            jira = f" · Jira: {doc['jira_ticket']}" if doc.get("jira_ticket") else ""
            owner = f" · Owner: {doc['owner']}" if doc.get("owner") else ""
            print(f"  - {doc['title']} (last ingested {doc['last_ingested']}, {doc['days_stale']} days ago{jira}{owner})")
            print(f"    {doc['url']}")
        print()

    for page_id, record in versions.items():
        if page_id in ("gdrive_docs", "jira_epics"):
            continue
        title = record["title"]
        known_version = record["version"]
        doc_id = record["doc_id"]
        category = record["category"]
        print(f"Checking: {title} (page {page_id}, known v{known_version})")

        try:
            page_data = fetch_confluence_page(page_id)
            remote_version = page_data["version"]["number"]

            if remote_version == known_version:
                print(f"  No change (v{remote_version})\n")
                record["last_checked"] = today
                continue

            print(f"  CHANGED: v{known_version} → v{remote_version}")
            text = html_to_text(page_data["body"]["storage"]["value"])
            base_url = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
            page_url = f"{base_url}/wiki/pages/viewpage.action?pageId={page_id}"

            # Summarize with Claude
            print("  Calling Claude for change summary...")
            analysis = summarize_change(title, known_version, remote_version, text)
            print(f"  Summary: {analysis.get('summary', '')[:100]}...")

            # Attempt ChromaDB ingest
            ingested = try_ingest_to_chromadb(
                page_id, title, remote_version, category, text, doc_id
            )

            change = {
                "page_id": page_id,
                "title": title,
                "doc_id": doc_id,
                "old_version": known_version,
                "new_version": remote_version,
                "page_url": page_url,
                "summary": analysis.get("summary", ""),
                "affected_phases": analysis.get("affected_phases", []),
                "chromadb_updated": ingested,
            }
            changes.append(change)

            # Update versions record
            record["version"] = remote_version
            record["last_checked"] = today
            print(f"  Done (chromadb_updated={ingested})\n")

        except Exception as e:
            msg = f"Error checking {title} ({page_id}): {e}"
            print(f"  ERROR: {e}\n", file=sys.stderr)
            errors.append(msg)
            record["last_checked"] = today

    # Save updated versions.json
    with open(VERSIONS_FILE, "w") as f:
        json.dump(versions, f, indent=2)
    print(f"Updated {VERSIONS_FILE}")

    # Write report
    report = {
        "run_date": today,
        "changes_detected": len(changes) > 0,
        "changes_count": len(changes),
        "changes": changes,
        "jira_epic_changes": jira_changes,
        "stale_gdrive_docs": stale_gdrive,
        "errors": errors,
    }
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report written to {REPORT_FILE}")

    # GitHub Actions outputs
    has_action_items = len(changes) > 0 or len(stale_gdrive) > 0 or len(jira_changes) > 0
    set_github_output("changes_detected", str(has_action_items).lower())
    set_github_output("changes_count", str(len(changes)))
    summary_lines = []
    for c in changes:
        phases = ", ".join(c["affected_phases"]) if c["affected_phases"] else "unknown"
        summary_lines.append(
            f"- **{c['title']}**: v{c['old_version']} → v{c['new_version']} "
            f"(affects: {phases})"
        )
    for doc in stale_gdrive:
        jira = f" · Jira: {doc['jira_ticket']}" if doc.get("jira_ticket") else ""
        summary_lines.append(
            f"- **{doc['title']}** (Google Doc): stale — last ingested {doc['last_ingested']} "
            f"({doc['days_stale']} days ago){jira} — {doc['url']}"
        )
    for j in jira_changes:
        phase = f" [{j['phase']}]" if j.get("phase") else ""
        summary_lines.append(
            f"- **{j['epic_key']} {j['title']}**{phase}: {j['old_status']} → {j['new_status']} — {j['url']}"
        )
    set_github_output("change_summary", "\n".join(summary_lines) if summary_lines else "No changes detected")

    # Summary
    print(f"\nResult: {len(changes)} change(s) detected, {len(jira_changes)} Jira epic change(s), "
          f"{len(stale_gdrive)} stale Google Doc(s), {len(errors)} error(s)")
    if changes:
        for c in changes:
            print(f"  {c['title']}: v{c['old_version']} → v{c['new_version']}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
