"""
Knowledge Base Loader
=====================
SQLite-backed cached loader for taxon, method, and disease knowledge bases.
On first load, builds an in-memory SQLite DB for fast fuzzy/lookup queries.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Resolve paths relative to this file
_KNOWLEDGE_DIR = Path(__file__).parent.resolve()


class KnowledgeBase:
    """
    Singleton-style knowledge base manager.
    Loads JSON/YAML files into an in-memory SQLite DB for fast querying.
    """

    _instance: Optional["KnowledgeBase"] = None
    _db: Optional[sqlite3.Connection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        self._db = sqlite3.connect(":memory:")
        self._db.row_factory = sqlite3.Row
        self._load_taxon_db()
        self._load_method_db()
        self._load_disease_db()
        logger.info("Knowledge base initialized in memory.")

    # ── Taxon ───────────────────────────────────────────────────────

    def _load_taxon_db(self):
        path = _KNOWLEDGE_DIR / "taxon_db.json"
        if not path.exists():
            logger.warning("taxon_db.json not found")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._db.execute(
            """
            CREATE TABLE taxon (
                name TEXT PRIMARY KEY,
                gram_stain TEXT,
                oxygen TEXT,
                main_products TEXT,      -- JSON list
                known_functions TEXT,    -- JSON list
                health_markers TEXT,     -- JSON list
                notes TEXT
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE taxon_disease (
                taxon_name TEXT,
                disease TEXT,
                association TEXT,
                FOREIGN KEY (taxon_name) REFERENCES taxon(name)
            )
            """
        )
        for name, info in data.items():
            self._db.execute(
                """
                INSERT INTO taxon (name, gram_stain, oxygen, main_products,
                                   known_functions, health_markers, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    info.get("gram_stain"),
                    info.get("oxygen"),
                    json.dumps(info.get("main_products", [])),
                    json.dumps(info.get("known_functions", [])),
                    json.dumps(info.get("health_markers", [])),
                    info.get("notes"),
                ),
            )
            for disease, association in info.get("disease_associations", {}).items():
                self._db.execute(
                    "INSERT INTO taxon_disease (taxon_name, disease, association) VALUES (?, ?, ?)",
                    (name, disease, association),
                )
        self._db.commit()

    def lookup_taxon(self, name: str) -> Optional[Dict[str, Any]]:
        """Exact match lookup for a taxon name."""
        cur = self._db.execute("SELECT * FROM taxon WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_taxon(row)

    def fuzzy_lookup_taxon(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fuzzy search: matches if query is a substring of the taxon name."""
        cur = self._db.execute(
            "SELECT * FROM taxon WHERE name LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        )
        return [self._row_to_taxon(r) for r in cur.fetchall()]

    def find_taxa_by_function(self, function_keyword: str) -> List[Dict[str, Any]]:
        """Find taxa whose known_functions contain the keyword."""
        cur = self._db.execute(
            "SELECT * FROM taxon WHERE known_functions LIKE ?",
            (f"%{function_keyword}%",),
        )
        return [self._row_to_taxon(r) for r in cur.fetchall()]

    def find_taxa_by_disease(self, disease: str, association: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find taxa associated with a disease (optionally filtered by association type)."""
        if association:
            cur = self._db.execute(
                """
                SELECT t.* FROM taxon t
                JOIN taxon_disease td ON t.name = td.taxon_name
                WHERE td.disease LIKE ? AND td.association = ?
                """,
                (f"%{disease}%", association),
            )
        else:
            cur = self._db.execute(
                """
                SELECT t.* FROM taxon t
                JOIN taxon_disease td ON t.name = td.taxon_name
                WHERE td.disease LIKE ?
                """,
                (f"%{disease}%",),
            )
        return [self._row_to_taxon(r) for r in cur.fetchall()]

    def _row_to_taxon(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "name": row["name"],
            "gram_stain": row["gram_stain"],
            "oxygen": row["oxygen"],
            "main_products": json.loads(row["main_products"]),
            "known_functions": json.loads(row["known_functions"]),
            "health_markers": json.loads(row["health_markers"]),
            "notes": row["notes"],
        }

    # ── Method ──────────────────────────────────────────────────────

    def _load_method_db(self):
        path = _KNOWLEDGE_DIR / "method_db.yaml"
        if not path.exists():
            logger.warning("method_db.yaml not found")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._db.execute(
            """
            CREATE TABLE method (
                name TEXT PRIMARY KEY,
                category TEXT,
                assumptions TEXT,     -- JSON list
                cautions TEXT,        -- JSON list
                follow_up TEXT,       -- JSON list
                prerequisites TEXT,   -- JSON list
                typical_runtime TEXT
            )
            """
        )
        for name, info in data.items():
            self._db.execute(
                """
                INSERT INTO method (name, category, assumptions, cautions,
                                    follow_up, prerequisites, typical_runtime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    info.get("category"),
                    json.dumps(info.get("assumptions", [])),
                    json.dumps(info.get("cautions", [])),
                    json.dumps(info.get("follow_up", [])),
                    json.dumps(info.get("prerequisites", [])),
                    info.get("typical_runtime"),
                ),
            )
        self._db.commit()

    def lookup_method(self, name: str) -> Optional[Dict[str, Any]]:
        cur = self._db.execute("SELECT * FROM method WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "category": row["category"],
            "assumptions": json.loads(row["assumptions"]),
            "cautions": json.loads(row["cautions"]),
            "follow_up": json.loads(row["follow_up"]),
            "prerequisites": json.loads(row["prerequisites"]),
            "typical_runtime": row["typical_runtime"],
        }

    # ── Disease ─────────────────────────────────────────────────────

    def _load_disease_db(self):
        path = _KNOWLEDGE_DIR / "disease_db.json"
        if not path.exists():
            logger.warning("disease_db.json not found")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._db.execute(
            """
            CREATE TABLE disease (
                name TEXT PRIMARY KEY,
                indicators TEXT,      -- JSON list
                key_genera TEXT,      -- JSON list
                functional_shift TEXT, -- JSON list
                description TEXT
            )
            """
        )
        for name, info in data.items():
            self._db.execute(
                """
                INSERT INTO disease (name, indicators, key_genera, functional_shift, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    json.dumps(info.get("indicators", [])),
                    json.dumps(info.get("key_genera", [])),
                    json.dumps(info.get("functional_shift", [])),
                    info.get("description"),
                ),
            )
        self._db.commit()

    def lookup_disease(self, name: str) -> Optional[Dict[str, Any]]:
        cur = self._db.execute("SELECT * FROM disease WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "indicators": json.loads(row["indicators"]),
            "key_genera": json.loads(row["key_genera"]),
            "functional_shift": json.loads(row["functional_shift"]),
            "description": row["description"],
        }


# ── Module-level convenience functions ─────────────────────────────

_kb: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


def lookup_taxon(name: str) -> Optional[Dict[str, Any]]:
    return get_knowledge_base().lookup_taxon(name)


def fuzzy_lookup_taxon(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    return get_knowledge_base().fuzzy_lookup_taxon(query, limit)


def find_taxa_by_function(function_keyword: str) -> List[Dict[str, Any]]:
    return get_knowledge_base().find_taxa_by_function(function_keyword)


def lookup_method(name: str) -> Optional[Dict[str, Any]]:
    return get_knowledge_base().lookup_method(name)


def lookup_disease(name: str) -> Optional[Dict[str, Any]]:
    return get_knowledge_base().lookup_disease(name)


def get_all_diseases() -> List[str]:
    """Return all disease names in the knowledge base."""
    kb = get_knowledge_base()
    cur = kb._db.execute("SELECT name FROM disease")
    return [row["name"] for row in cur.fetchall()]


def get_all_taxa() -> List[str]:
    """Return all taxon names in the knowledge base."""
    kb = get_knowledge_base()
    cur = kb._db.execute("SELECT name FROM taxon")
    return [row["name"] for row in cur.fetchall()]
