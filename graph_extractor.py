"""Structured Entity and Relation Extractor for Kestrel Native Knowledge Graph.

Extracts domain entities and relationships from document chunks using schema-constrained
LLM generation, canonicalizes entity names, and returns validated ExtractionResult.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from ontology import (
    EntityType,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    RelationType,
)

SYSTEM_PROMPT = """You are a precise Knowledge Graph Extraction engine for enterprise documentation.
Your job is to read the provided text chunk and extract key domain entities and directed relationships.

Strict constraints:
1. Only extract entities that belong to these types: Organization, Person, Contract, Policy, System, Incident, Obligation, Concept.
2. Only extract relationships with these predicates: PARTY_TO, GOVERNED_BY, OWNS, MAINTAINS, REPORTS_TO, ASSIGNED_TO, AFFECTS, DEPENDS_ON, SUPERSEDES, OBLIGATED_TO, RELATED_TO.
3. Every relationship must include an exact verbatim 'evidence_text' snippet from the input text that proves the relationship.
4. Do not invent entities or relationships not supported by the text.
5. Return ONLY a valid JSON object matching this schema:
{
  "entities": [
    {"name": "...", "entity_type": "...", "description": "...", "aliases": ["..."]}
  ],
  "relations": [
    {"source_entity": "...", "target_entity": "...", "relation_type": "...", "description": "...", "confidence": 1.0, "evidence_text": "..."}
  ]
}"""


def canonicalize_entity_name(name: str) -> str:
    """Normalize an entity name for consistent matching and deduplication.

    - Lowercase
    - Collapses internal whitespace
    - Strips leading/trailing quotes and brackets
    - Normalizes common acronym periods (e.g. 'S.O.C. 2' -> 'soc 2')
    """
    if not name:
        return ""
    # Strip quotes, parens, brackets
    cleaned = re.sub(r'^[\s"\'`\(\[\{]+|[\s"\'`\)\]\}]+$', '', name)
    # Normalize acronyms like S.O.C. -> soc
    cleaned = re.sub(r'(?<=[a-zA-Z])\.(?=[a-zA-Z]|\s|$)', '', cleaned)
    # Collapse multiple whitespaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
    return cleaned


def parse_extraction_json(raw: str) -> ExtractionResult:
    """Parse JSON string (handling markdown fences if present) into ExtractionResult."""
    text = raw.strip()
    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(f"Failed to parse extraction output as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Extraction JSON must be an object with entities[] and relations[]")

    raw_entities = data.get("entities") or []
    raw_relations = data.get("relations") or []

    valid_entities: list[ExtractedEntity] = []
    for e in raw_entities:
        try:
            # Coerce entity_type to valid enum if casing differs
            etype_str = str(e.get("entity_type", "")).strip()
            etype = next(
                (t for t in EntityType if t.value.lower() == etype_str.lower()),
                EntityType.CONCEPT,
            )
            valid_entities.append(
                ExtractedEntity(
                    name=str(e.get("name", "")).strip(),
                    entity_type=etype,
                    description=str(e.get("description", "")).strip(),
                    aliases=[str(a).strip() for a in e.get("aliases", []) if str(a).strip()],
                )
            )
        except Exception:
            continue

    valid_relations: list[ExtractedRelation] = []
    for r in raw_relations:
        try:
            rtype_str = str(r.get("relation_type", "")).strip()
            rtype = next(
                (t for t in RelationType if t.value.upper() == rtype_str.upper()),
                RelationType.RELATED_TO,
            )
            valid_relations.append(
                ExtractedRelation(
                    source_entity=str(r.get("source_entity", "")).strip(),
                    target_entity=str(r.get("target_entity", "")).strip(),
                    relation_type=rtype,
                    description=str(r.get("description", "")).strip(),
                    confidence=float(r.get("confidence", 1.0)),
                    evidence_text=str(r.get("evidence_text", "")).strip(),
                )
            )
        except Exception:
            continue

    return ExtractionResult(entities=valid_entities, relations=valid_relations)


def extract_from_chunk(text: str, model: Optional[str] = None) -> ExtractionResult:
    """Extract entities and relations from a single text chunk.

    In mock mode (PROVIDER=mock), returns deterministic domain entities for test corpora.
    In cloud/live mode, invokes the configured LLM with temperature=0.0.
    """
    if os.getenv("PROVIDER") == "mock":
        entities = []
        relations = []
        lower = text.lower()
        if "bluepeak" in lower:
            entities.append(
                ExtractedEntity(
                    name="Bluepeak Inc",
                    entity_type=EntityType.ORGANIZATION,
                    description="Customer organization",
                    aliases=["Bluepeak"],
                )
            )
        if "msa" in lower or "contract" in lower:
            entities.append(
                ExtractedEntity(
                    name="MSA-2025-0114",
                    entity_type=EntityType.CONTRACT,
                    description="Master Services Agreement",
                    aliases=["MSA"],
                )
            )
        if "soc 2" in lower or "sec-review" in lower:
            entities.append(
                ExtractedEntity(
                    name="Policy SEC-REVIEW-01",
                    entity_type=EntityType.POLICY,
                    description="Annual security review policy",
                    aliases=["SEC-REVIEW-01"],
                )
            )
        if len(entities) >= 2:
            relations.append(
                ExtractedRelation(
                    source_entity=entities[0].name,
                    target_entity=entities[1].name,
                    relation_type=RelationType.PARTY_TO if entities[1].entity_type == EntityType.CONTRACT else RelationType.GOVERNED_BY,
                    description=f"{entities[0].name} related to {entities[1].name}",
                    confidence=0.99,
                    evidence_text=text[:150],
                )
            )
        return ExtractionResult(entities=entities, relations=relations)

    # Cloud/Live extraction via requests to LLM endpoint
    import requests
    import llm

    chat_url = llm.chat_url() or "https://tokenharbor.ai/v1/chat/completions"
    api_key = llm.api_key()
    chosen_model = model or llm.default_model()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": chosen_model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract entities and relations from this text chunk:\n\n{text}"},
        ],
    }

    resp = requests.post(
        chat_url,
        headers=headers,
        json=payload,
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"LLM extraction request failed ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ExtractionResult(entities=[], relations=[])

    content = choices[0].get("message", {}).get("content", "")
    return parse_extraction_json(content)
