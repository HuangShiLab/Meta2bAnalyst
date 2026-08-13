"""
Meta2bAnalyst Knowledge Base
============================
Structured domain knowledge for microbiome analysis.

Modules:
- loader: SQLite-backed knowledge base with taxon, method, and disease lookups
"""
from app.knowledge.loader import (
    get_knowledge_base,
    lookup_taxon,
    fuzzy_lookup_taxon,
    find_taxa_by_function,
    lookup_method,
    lookup_disease,
)

__all__ = [
    "get_knowledge_base",
    "lookup_taxon",
    "fuzzy_lookup_taxon",
    "find_taxa_by_function",
    "lookup_method",
    "lookup_disease",
]
