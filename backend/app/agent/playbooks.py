"""Analysis playbooks: curated, study-type-keyed plan templates.

A playbook is the "article archetype" counterpart of paper2agent: where
plan-from-paper reproduces *one specific paper*, a playbook encodes the
common analysis practice for a *class* of studies (longitudinal multi-omics,
case-control 16S, ...), so users get a validated workflow by picking a card
instead of writing a prompt.

Playbooks live as JSON files in ./playbooks/. Each declares its required
data layers and metadata columns (roles like ``group_column``), and its
steps use ``{role}`` placeholders in params. Instantiation resolves the
placeholders against the session's actual metadata, reusing the executor's
column-snapping machinery so playbook, paper2agent, and LLM plans all speak
through the same normalization contract:

- user-supplied ``column_mapping`` wins;
- otherwise the role name snaps to the closest metadata column
  (exact -> normalized -> synonym group);
- ``reference_level``/``reference_group`` resolves against the *levels* of
  the resolved group column (first sorted level by default, which for
  time-ordered designs is the baseline);
- a required role that cannot be resolved is an honest error naming the
  missing role and the available columns — never a silently wrong analysis.

Every resolution is recorded in ``corrections`` so the confirm screen can
disclose exactly how the template met the data.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.executor import _COLUMN_SYNONYMS, _snap_column_name

logger = logging.getLogger(__name__)

PLAYBOOKS_DIR = Path(__file__).parent / "playbooks"

#: roles whose value is a metadata *level* of the resolved group column,
#: not a column name
_LEVEL_ROLES = {"reference_level", "reference_group"}

#: role -> synonym set override (defaults to the executor's per-role set)
_ROLE_SYNONYMS: Dict[str, tuple] = {
    "group_column": _COLUMN_SYNONYMS.get("group_column", ()),
    "subject_column": _COLUMN_SYNONYMS.get("subject_column", ()),
    "time_column": _COLUMN_SYNONYMS.get("time_column", ()),
    "site_column": _COLUMN_SYNONYMS.get("site_column", ()),
    "batch_column": _COLUMN_SYNONYMS.get("batch_column", ()),
}


class PlaybookError(ValueError):
    """Raised for malformed playbooks or unresolvable instantiation."""


_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _load_all() -> Dict[str, Dict[str, Any]]:
    global _cache
    if _cache is None:
        pbs: Dict[str, Dict[str, Any]] = {}
        for path in sorted(PLAYBOOKS_DIR.glob("*.json")):
            pb = json.loads(path.read_text(encoding="utf-8"))
            validate_playbook(pb)
            pbs[pb["id"]] = pb
        _cache = pbs
    return _cache


def validate_playbook(pb: Dict[str, Any]) -> None:
    """Fail fast on malformed playbook files (also exercised by tests)."""
    from app.agent.module_registry import MODULE_REGISTRY

    for key in ("id", "title", "study_type", "required_data",
                "required_columns", "steps"):
        if key not in pb:
            raise PlaybookError(f"playbook missing required key: {key}")
    ids = [s["id"] for s in pb["steps"]]
    if len(ids) != len(set(ids)):
        raise PlaybookError(f"{pb['id']}: duplicate step ids")
    for step in pb["steps"]:
        module = step.get("module")
        if module not in MODULE_REGISTRY:
            raise PlaybookError(
                f"{pb['id']}: step {step['id']} uses unregistered module '{module}'")
        for dep in step.get("depends_on") or []:
            if dep not in ids:
                raise PlaybookError(
                    f"{pb['id']}: step {step['id']} depends on unknown step '{dep}'")
        if step["id"] in (step.get("depends_on") or []):
            raise PlaybookError(f"{pb['id']}: step {step['id']} depends on itself")


def list_playbooks() -> List[Dict[str, Any]]:
    """Card-level metadata for the picker UI (no step bodies)."""
    out = []
    for pb in _load_all().values():
        out.append({
            "id": pb["id"],
            "title": pb["title"],
            "title_en": pb.get("title_en", ""),
            "study_type": pb["study_type"],
            "article_archetype": pb.get("article_archetype", ""),
            "description": pb.get("description", ""),
            "required_data": pb["required_data"],
            "required_columns": pb["required_columns"],
            "optional_columns": pb.get("optional_columns", {}),
            "expected_outputs": pb.get("expected_outputs", []),
            "n_steps": len(pb["steps"]),
        })
    return out


def get_playbook(playbook_id: str) -> Dict[str, Any]:
    try:
        return _load_all()[playbook_id]
    except KeyError:
        raise PlaybookError(
            f"Unknown playbook '{playbook_id}'. "
            f"Available: {sorted(_load_all())}")


def _placeholders(value: Any) -> List[str]:
    """Collect {role} placeholders from a param value (strings only)."""
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        return [value[1:-1]]
    if isinstance(value, list):
        return [r for v in value for r in _placeholders(v)]
    return []


def declared_roles(pb: Dict[str, Any]) -> List[str]:
    """Roles actually used by the steps (may be a subset of declared columns)."""
    roles = set()
    for step in pb["steps"]:
        for v in (step.get("params") or {}).values():
            roles.update(_placeholders(v))
    return sorted(roles)


def instantiate_playbook(
    playbook_id: str,
    metadata_df,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Resolve a playbook's placeholders against session metadata.

    Args:
        playbook_id: playbook to instantiate.
        metadata_df: session metadata (samples x variables); levels are read
            from the resolved group column for reference-level roles.
        column_mapping: optional user override, role -> column name (or
            level name for reference-level roles).

    Returns:
        {"plan": {...}, "resolved_roles": {...}, "corrections": [...]}

    Raises:
        PlaybookError: a required role could not be resolved. The message
            names the missing role and lists the available columns.
    """
    pb = get_playbook(playbook_id)
    mapping = dict(column_mapping or {})
    columns = [str(c) for c in metadata_df.columns] if metadata_df is not None else []

    required = dict(pb.get("required_columns") or {})
    optional = dict(pb.get("optional_columns") or {})
    used = set(declared_roles(pb))

    resolved: Dict[str, str] = {}
    corrections: List[Dict[str, str]] = []
    missing: List[str] = []

    def _note(role: str, to: str, kind: str) -> None:
        corrections.append({"role": role, "to": to, "kind": kind})

    # 1. Column-naming roles (required first, then optional).
    for role in list(required) + [r for r in optional if r not in _LEVEL_ROLES]:
        if role not in used and role not in mapping:
            continue
        user_val = mapping.get(role)
        if user_val:
            if user_val in columns:
                resolved[role] = user_val
                _note(role, user_val, "user_mapping")
                continue
            raise PlaybookError(
                f"column_mapping['{role}'] = '{user_val}' 不在元数据列中。"
                f"可用列: {columns}")
        snapped = _snap_column_name(role, columns, _ROLE_SYNONYMS.get(role, ()))
        if snapped:
            resolved[role] = snapped
            _note(role, snapped, "column_snap")
        elif role in required:
            missing.append(role)

    if missing:
        raise PlaybookError(
            f"该剧本需要元数据列 {missing}（{'; '.join(required[r] for r in missing)}），"
            f"但当前会话的元数据列为: {columns}。"
            f"请补充元数据，或在列映射中手动指定。")

    # 2. Level roles: resolve against the levels of the group column.
    group_col = resolved.get("group_column") or resolved.get("time_column")
    for role in optional:
        if role not in _LEVEL_ROLES:
            continue
        if role not in used and role not in mapping:
            continue
        user_val = mapping.get(role)
        levels: List[str] = []
        if group_col and metadata_df is not None and group_col in metadata_df.columns:
            levels = sorted(str(v) for v in metadata_df[group_col].dropna().unique())
        if user_val:
            if levels and user_val not in levels:
                raise PlaybookError(
                    f"column_mapping['{role}'] = '{user_val}' 不是 {group_col} 的水平。"
                    f"可用水平: {levels}")
            resolved[role] = user_val
            _note(role, user_val, "user_mapping")
        elif levels:
            # First sorted level: baseline (DAY0/T0/Control) in typical designs.
            resolved[role] = levels[0]
            _note(role, levels[0], "level_default")

    # 3. Substitute placeholders in step params; drop unresolved optionals.
    def _sub(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            role = value[1:-1]
            return resolved.get(role, _DROP)
        if isinstance(value, list):
            return [_sub(v) for v in value]
        return value

    steps = []
    for step in pb["steps"]:
        params = {}
        for k, v in (step.get("params") or {}).items():
            sv = _sub(v)
            if sv is not _DROP:
                params[k] = sv
        steps.append({
            "id": step["id"],
            "module": step["module"],
            "params": params,
            "depends_on": step.get("depends_on") or [],
            "description": step.get("description", ""),
        })

    plan = {
        "query": f"playbook:{pb['id']}",
        "n_steps": len(steps),
        "steps": steps,
        "estimated_time": "",
        "notes": [f"playbook {pb['id']}: {c['role']} -> {c['to']} ({c['kind']})"
                  for c in corrections],
    }
    return {"plan": plan, "resolved_roles": resolved, "corrections": corrections,
            "playbook": {k: pb.get(k) for k in
                         ("id", "title", "title_en", "study_type", "expected_outputs")}}


class _Drop:
    def __repr__(self):  # pragma: no cover - debugging aid
        return "<DROP>"


_DROP = _Drop()
