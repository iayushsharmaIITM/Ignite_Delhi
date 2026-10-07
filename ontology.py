"""Domain Ontology and Structured Extraction Models for Kestrel Knowledge Graph.

Defines the canonical Labeled Property Graph (LPG) schema for enterprise
documents, supporting Pydantic-based structured LLM extraction and deterministic
provenance grounding.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class EntityType(str, Enum):
    ORGANIZATION = "Organization"
    PERSON = "Person"
    CONTRACT = "Contract"
    POLICY = "Policy"
    SYSTEM = "System"
    INCIDENT = "Incident"
    OBLIGATION = "Obligation"
    CONCEPT = "Concept"


class RelationType(str, Enum):
    PARTY_TO = "PARTY_TO"
    GOVERNED_BY = "GOVERNED_BY"
    OWNS = "OWNS"
    MAINTAINS = "MAINTAINS"
    REPORTS_TO = "REPORTS_TO"
    ASSIGNED_TO = "ASSIGNED_TO"
    AFFECTS = "AFFECTS"
    DEPENDS_ON = "DEPENDS_ON"
    SUPERSEDES = "SUPERSEDES"
    OBLIGATED_TO = "OBLIGATED_TO"
    RELATED_TO = "RELATED_TO"


class ExtractedEntity(BaseModel):
    name: str = Field(description="Canonical or mentioned name of the entity, e.g. 'Bluepeak Inc', 'Ayush Sharma', 'Pulse API'")
    entity_type: EntityType = Field(description="Categorical entity type")
    description: str = Field(description="Summary of what this entity is or its role in context", default="")
    aliases: List[str] = Field(description="Alternative names or abbreviations used in text, e.g. ['MSA', 'Contract MSA-2025']", default_factory=list)


class ExtractedRelation(BaseModel):
    source_entity: str = Field(description="Exact name of the source entity")
    target_entity: str = Field(description="Exact name of the target entity")
    relation_type: RelationType = Field(description="Standard relationship predicate")
    description: str = Field(description="Brief description of the relationship context", default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score between 0.0 and 1.0")
    evidence_text: str = Field(description="Verbatim excerpt from the document backing this relationship", default="")


class ExtractionResult(BaseModel):
    """Structured extraction output returned by LLM extraction pass on one text chunk."""
    entities: List[ExtractedEntity] = Field(default_factory=list, description="List of recognized entities in the chunk")
    relations: List[ExtractedRelation] = Field(default_factory=list, description="List of directed relationships between recognized entities")
