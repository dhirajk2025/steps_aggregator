#!/usr/bin/env python3
"""
Confluence → ChromaDB ingestion script.
Fetches Confluence pages, detects version changes, and updates ChromaDB.

Usage:
    python3 confluence_ingest.py

Environment variables required:
    CONFLUENCE_EMAIL      - Your Atlassian email
    CONFLUENCE_API_TOKEN  - Your Atlassian API token
    CONFLUENCE_BASE_URL   - e.g. https://idmeinc.atlassian.net

Add new pages to PAGES_TO_TRACK below.
"""

import os
import re
import sys
import json
import requests
import chromadb
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────

PAGES_TO_TRACK = [
    {
        "page_id": "4034101286",
        "doc_id": "prr-process",          # ChromaDB document ID prefix
        "category": "process",
        "description": "Production Readiness Review Process",
    },
    {
        "page_id": "2512158864",
        "doc_id": "threat-model",
        "category": "security",
        "description": "Threat Modeling Service",
    },
    {
        "page_id": "4100390931",
        "doc_id": "api-council",
        "category": "process",
        "description": "API Council Operating Guide",
    },
    {
        "page_id": "3935502401",
        "doc_id": "building-apis",
        "category": "standards",
        "description": "Building APIs Guide",
    },
    {
        "page_id": "4039540737",
        "doc_id": "adr-003-versioning",
        "category": "standards",
        "description": "ADR 003 - API Versioning Strategy",
    },
    # Add more pages here:
]

CHROMA_COLLECTION = "idme-processes"

# ── Confluence client ──────────────────────────────────────────────────────────

def get_confluence_page(page_id: str) -> dict:
    email = os.environ["CONFLUENCE_EMAIL"]
    token = os.environ["CONFLUENCE_API_TOKEN"]
    base_url = os.environ["CONFLUENCE_BASE_URL"]

    url = f"{base_url}/wiki/rest/api/content/{page_id}?expand=version,body.storage"
    resp = requests.get(url, auth=(email, token))
    resp.raise_for_status()
    return resp.json()


def html_to_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_gdrive_links(html: str) -> list[str]:
    """Extract unique Google Doc/Drive URLs from Confluence page HTML."""
    pattern = r'https://docs\.google\.com/(?:document|spreadsheets|presentation)/d/[A-Za-z0-9_-]+'
    return sorted(set(re.findall(pattern, html)))

# ── ChromaDB client ────────────────────────────────────────────────────────────

def get_collection():
    client = chromadb.HttpClient(host="localhost", port=8000)
    try:
        return client.get_collection(CHROMA_COLLECTION)
    except Exception:
        return client.create_collection(
            CHROMA_COLLECTION,
            metadata={"description": "ID.me engineering process documents from Confluence"},
        )


def get_stored_version(collection, doc_id: str) -> int | None:
    try:
        result = collection.get(ids=[doc_id], include=["metadatas"])
        if result["ids"]:
            return result["metadatas"][0].get("version")
    except Exception:
        pass
    return None


def upsert_page(collection, page_data: dict, config: dict):
    version = page_data["version"]["number"]
    title = page_data["title"]
    html = page_data["body"]["storage"]["value"]
    text = html_to_text(html)
    doc_id = f"{config['doc_id']}-v{version}"
    base_url = os.environ["CONFLUENCE_BASE_URL"]

    metadata = {
        "title": title,
        "page_id": config["page_id"],
        "version": version,
        "source": "confluence",
        "url": f"{base_url}/wiki/pages/viewpage.action?pageId={config['page_id']}",
        "category": config["category"],
        "ingested_date": datetime.now().strftime("%Y-%m-%d"),
        "last_updated_by": page_data["version"].get("by", {}).get("email", "unknown"),
    }

    # Remove old versions
    try:
        existing = collection.get(
            where={"page_id": config["page_id"]},
            include=["metadatas"],
        )
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
            print(f"  Removed {len(existing['ids'])} old version(s)")
    except Exception:
        pass

    collection.add(documents=[text], ids=[doc_id], metadatas=[metadata])
    return version, title

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Checking Confluence pages...\n")

    for page_config in PAGES_TO_TRACK:
        page_id = page_config["page_id"]
        desc = page_config["description"]
        print(f"Checking: {desc} (page {page_id})")

        try:
            page_data = get_confluence_page(page_id)
            remote_version = page_data["version"]["number"]
            print(f"  Remote version: {remote_version}")

            # Check ChromaDB via MCP (ChromaDB is managed via MCP in this project)
            # For standalone use, you'd connect directly:
            # collection = get_collection()
            # stored_version = get_stored_version(collection, page_config["doc_id"])

            # Save to a JSON file for MCP-based ingestion
            html = page_data["body"]["storage"]["value"]
            gdrive_links = extract_gdrive_links(html)
            out = {
                "page_id": page_id,
                "doc_id": page_config["doc_id"],
                "version": remote_version,
                "title": page_data["title"],
                "category": page_config["category"],
                "url": f"{os.environ['CONFLUENCE_BASE_URL']}/wiki/pages/viewpage.action?pageId={page_id}",
                "text": html_to_text(html),
                "gdrive_links": gdrive_links,
                "last_updated_by": page_data["version"].get("by", {}).get("email", "unknown"),
                "fetched_at": datetime.now().isoformat(),
            }

            out_path = f"/tmp/confluence_{page_id}_v{remote_version}.json"
            with open(out_path, "w") as f:
                json.dump(out, f, indent=2)

            print(f"  Saved to: {out_path}")
            print(f"  Title: {out['title']}")
            print(f"  Content length: {len(out['text'])} chars")
            if gdrive_links:
                print(f"  Google Doc links found ({len(gdrive_links)}):")
                for link in gdrive_links:
                    print(f"    {link}")

        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

        print()

    print("Done. Use Claude Code to ingest /tmp/confluence_*.json files into ChromaDB.")


if __name__ == "__main__":
    main()
