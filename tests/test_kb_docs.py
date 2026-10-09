"""Every KB doc follows the template and has valid metadata, so retrieval and filters work."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

DOCS = Path(__file__).resolve().parents[1] / "kb" / "docs"
REQUIRED_SECTIONS = [
    "Symptoms",
    "Impact",
    "Diagnosis steps",
    "Mitigation",
    "Rollback",
    "Escalation",
    "Related alerts",
]
POSTMORTEM_EXTRA = ["Summary", "Timeline", "Root cause", "Action items"]
SEVERITIES = {"sev1", "sev2", "sev3", "sev4"}
# S3 Vectors caps filterable metadata at 2 KB per vector; stay well under it.
MAX_METADATA_BYTES = 1024

ALL_DOCS = sorted(DOCS.rglob("*.md"))


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def _metadata(doc: Path) -> dict[str, Any]:
    raw = doc.with_name(doc.name + ".metadata.json").read_text(encoding="utf-8")
    meta: dict[str, Any] = json.loads(raw)["metadataAttributes"]
    return meta


def test_doc_counts():
    assert len(list((DOCS / "runbooks").glob("*.md"))) == 20
    assert len(list((DOCS / "postmortems").glob("*.md"))) == 6


def test_every_metadata_file_has_a_doc():
    for meta in DOCS.rglob("*.metadata.json"):
        assert meta.with_name(meta.name.removesuffix(".metadata.json")).exists(), meta


@pytest.mark.parametrize("doc", ALL_DOCS, ids=lambda p: p.stem)
def test_doc_has_title_and_required_sections_in_order(doc):
    text = doc.read_text(encoding="utf-8")
    assert re.match(r"^# (Runbook|Postmortem): \S", text), "first line must be '# Runbook: ...'"
    sections = _sections(text)
    for name in REQUIRED_SECTIONS:
        assert name in sections, f"missing '## {name}'"
        assert len(sections[name]) >= 20, f"'## {name}' is empty or too short"
    order = [s for s in sections if s in REQUIRED_SECTIONS]
    assert order == REQUIRED_SECTIONS
    if doc.parent.name == "postmortems":
        for name in POSTMORTEM_EXTRA:
            assert name in sections, f"postmortem missing '## {name}'"


@pytest.mark.parametrize("doc", ALL_DOCS, ids=lambda p: p.stem)
def test_metadata_is_valid_and_matches_doc(doc):
    meta = _metadata(doc)
    assert set(meta) == {"doc_id", "doc_type", "title", "service", "severity", "alert_names"}
    assert doc.name.startswith(meta["doc_id"])
    assert meta["doc_type"] == {"runbooks": "runbook", "postmortems": "postmortem"}[doc.parent.name]
    assert meta["severity"] in SEVERITIES
    assert re.fullmatch(r"[a-z][a-z0-9-]+", meta["service"])
    assert meta["alert_names"], "at least one alert name"
    assert all(re.fullmatch(r"[A-Z][A-Za-z0-9]+", a) for a in meta["alert_names"])

    text = doc.read_text(encoding="utf-8")
    assert meta["title"] in text.splitlines()[0]
    listed = re.findall(r"^- (\w+)$", _sections(text)["Related alerts"], flags=re.M)
    assert listed == meta["alert_names"], "Related alerts section and metadata disagree"
    assert len(json.dumps(meta).encode()) <= MAX_METADATA_BYTES


def test_doc_ids_and_titles_are_unique():
    metas = [_metadata(d) for d in ALL_DOCS]
    assert len({m["doc_id"] for m in metas}) == len(metas)
    assert len({m["title"] for m in metas}) == len(metas)
