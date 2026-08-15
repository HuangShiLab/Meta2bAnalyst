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
import threading
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
        # check_same_thread=False plus an explicit lock: FastAPI runs sync route
        # handlers in a threadpool, so the singleton is created on one worker
        # thread and then used from others. With the default (True) that raised
        # "SQLite objects created in a thread can only be used in that same
        # thread" -- intermittently, and only under concurrency.
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._load_taxon_db()
        self._load_method_db()
        self._load_disease_db()
        logger.info("Knowledge base initialized in memory.")

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Run a read query under the connection lock."""
        with self._lock:
            return self._db.execute(sql, params).fetchall()

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
                notes TEXT,
                disease_evidence TEXT,   -- JSON map condition -> [evidence]
                rank TEXT,
                auto_generated INTEGER
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
                                   known_functions, health_markers, notes,
                                   disease_evidence, rank, auto_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    info.get("gram_stain"),
                    info.get("oxygen"),
                    json.dumps(info.get("main_products", [])),
                    json.dumps(info.get("known_functions", [])),
                    json.dumps(info.get("health_markers", [])),
                    info.get("notes"),
                    json.dumps(info.get("disease_evidence", {})),
                    info.get("rank"),
                    1 if info.get("auto_generated") else 0,
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
        rows = self._query("SELECT * FROM taxon WHERE name = ?", (name,))
        if not rows:
            return None
        return self._row_to_taxon(rows[0])

    def fuzzy_lookup_taxon(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fuzzy search: matches if query is a substring of the taxon name."""
        return [self._row_to_taxon(r) for r in self._match_taxon_rows(query, limit)]

    def find_taxa_by_function(self, function_keyword: str) -> List[Dict[str, Any]]:
        """Find taxa whose known_functions contain the keyword."""
        rows = self._query("SELECT * FROM taxon WHERE known_functions LIKE ?",
                           (f"%{function_keyword}%",))
        return [self._row_to_taxon(r) for r in rows]

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

    # ── Taxon name matching ─────────────────────────────────────────

    @staticmethod
    def normalize_taxon_name(name: str) -> str:
        """Reduce a taxon label to a comparable key.

        Real feature tables label taxa in several conventions that all refer to
        the same organism::

            Faecalibacterium_prausnitzii                       (KB form)
            s__Faecalibacterium_prausnitzii                    (MetaPhlAn/2bRAD-M)
            Faecalibacterium prausnitzii                       (space separated)
            k__Bacteria|p__Firmicutes|...|s__Faecalibacterium_prausnitzii   (lineage)

        Matching used to be ``KB.name LIKE '%<query>%'``, i.e. it asked whether
        the KB name *contains* the queried label -- backwards for every prefixed
        or lineage form, so only the bare underscore spelling ever hit.
        """
        text = str(name).strip()
        if "|" in text:                       # full lineage -> deepest rank
            text = text.split("|")[-1]
        if ";" in text:                       # QIIME-style lineage
            text = text.split(";")[-1]
        text = text.strip()
        # Strip a leading rank prefix such as s__ / g__ / k__
        if len(text) > 3 and text[1:3] == "__":
            text = text[3:]
        return text.replace(" ", "_").replace("-", "_").strip("_").lower()

    def _match_taxon_rows(self, query: str, limit: int = 5) -> List[sqlite3.Row]:
        """Find taxon rows for a label in any common naming convention."""
        key = self.normalize_taxon_name(query)
        if not key:
            return []

        rows = self._query("SELECT * FROM taxon")
        by_key = {self.normalize_taxon_name(r["name"]): r for r in rows}

        if key in by_key:                                   # exact, after normalising
            return [by_key[key]]

        # Genus-only query ("Faecalibacterium") should surface its species.
        prefix = [r for k, r in by_key.items() if k.startswith(key + "_")]
        if prefix:
            return prefix[:limit]

        # Species label whose genus we know, or any containment either way.
        contains = [r for k, r in by_key.items() if key in k or k in key]
        return contains[:limit]

    def _row_to_taxon(self, row: sqlite3.Row) -> Dict[str, Any]:
        # disease_associations lives in a separate table and was never joined,
        # so consumers testing `if "disease_associations" in info` were dead code
        # and no taxon->disease annotation was ever emitted.
        associations = {
            r["disease"]: r["association"]
            for r in self._query(
                "SELECT disease, association FROM taxon_disease WHERE taxon_name = ?",
                (row["name"],),
            )
        }
        return {
            "name": row["name"],
            "gram_stain": row["gram_stain"],
            "oxygen": row["oxygen"],
            "main_products": json.loads(row["main_products"]),
            "known_functions": json.loads(row["known_functions"]),
            "health_markers": json.loads(row["health_markers"]),
            "notes": row["notes"],
            "disease_associations": associations,
            "disease_evidence": json.loads(row["disease_evidence"] or "{}"),
            "rank": row["rank"],
            "auto_generated": bool(row["auto_generated"]),
        }

    # ── Keyword search ────────────────────────────────────────────

    def search(self, keyword: str, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """Keyword search across taxa and diseases.

        Matches (case-insensitive substring) against taxon name,
        known_functions, main_products, health_markers, notes, and against
        disease name + description. Returns ``{"taxa": [...], "diseases": [...]}``
        each capped at ``limit`` entries.
        """
        kw = f"%{str(keyword).strip()}%"
        if kw == "%%":
            return {"taxa": [], "diseases": []}
        taxon_rows = self._query(
            """
            SELECT * FROM taxon
            WHERE name LIKE ? OR known_functions LIKE ? OR main_products LIKE ?
               OR health_markers LIKE ? OR notes LIKE ?
            LIMIT ?
            """,
            (kw, kw, kw, kw, kw, limit),
        )
        disease_rows = self._query(
            "SELECT * FROM disease WHERE name LIKE ? OR description LIKE ? LIMIT ?",
            (kw, kw, limit),
        )
        return {
            "taxa": [self._row_to_taxon(r) for r in taxon_rows],
            "diseases": [self._row_to_disease(r) for r in disease_rows],
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
        rows = self._query("SELECT * FROM method WHERE name = ?", (name,))
        if not rows:
            return None
        row = rows[0]
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
                description TEXT,
                literature_evidence TEXT  -- JSON map taxon -> [evidence]
            )
            """
        )
        for name, info in data.items():
            self._db.execute(
                """
                INSERT INTO disease (name, indicators, key_genera, functional_shift,
                                     description, literature_evidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    json.dumps(info.get("indicators", [])),
                    json.dumps(info.get("key_genera", [])),
                    json.dumps(info.get("functional_shift", [])),
                    info.get("description"),
                    json.dumps(info.get("literature_evidence", {})),
                ),
            )
        self._db.commit()

    @staticmethod
    def _row_to_disease(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "name": row["name"],
            "indicators": json.loads(row["indicators"]),
            "key_genera": json.loads(row["key_genera"]),
            "functional_shift": json.loads(row["functional_shift"]),
            "description": row["description"],
            "literature_evidence": json.loads(row["literature_evidence"] or "{}"),
        }

    def lookup_disease(self, name: str) -> Optional[Dict[str, Any]]:
        rows = self._query("SELECT * FROM disease WHERE name = ?", (name,))
        if not rows:
            return None
        return self._row_to_disease(rows[0])


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


def search_knowledge(keyword: str, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
    """Keyword search across taxa and diseases; returns {"taxa": [...], "diseases": [...]}."""
    return get_knowledge_base().search(keyword, limit=limit)


def get_all_diseases() -> List[str]:
    """Return all disease names in the knowledge base."""
    kb = get_knowledge_base()
    return [row["name"] for row in kb._query("SELECT name FROM disease")]


def get_all_taxa() -> List[str]:
    """Return all taxon names in the knowledge base."""
    kb = get_knowledge_base()
    return [row["name"] for row in kb._query("SELECT name FROM taxon")]
