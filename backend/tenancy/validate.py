"""Validates org / project profiles against data/onboarding_schema.json (the single source of truth)."""
from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "onboarding_schema.json"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_PATTERNS = {
    "gstin": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    "pan": r"^[A-Z]{5}[0-9]{4}[A-Z]$",
    "pincode": r"^[1-9][0-9]{5}$",
    "phone": r"^\+?[0-9 ()-]{10,16}$",
}


@lru_cache(maxsize=1)
def _load(mtime: float) -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def load_schema() -> dict:
    return _load(SCHEMA_PATH.stat().st_mtime)


def fields_for(scope: str) -> list[dict]:
    return [f for step in load_schema()[scope]["steps"] for f in step["fields"]]


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict)) and not v)


def flatten(scope: str, profile: dict) -> dict:
    """Accept {stepId: {...}} as well as the canonical flat shape."""
    if not isinstance(profile, dict):
        return {}
    keys = {f["key"] for f in fields_for(scope)}
    steps = {s["id"] for s in load_schema()[scope]["steps"]}
    out: dict = {}
    for k, v in profile.items():
        if k in steps and k not in keys and isinstance(v, dict):
            out.update(v)
        else:
            out[k] = v
    return out


def _coerce(field: dict, value: Any, path: str, errors: list, full: dict) -> Any:
    t = field["type"]
    val = field.get("validation") or {}
    label = field.get("label", field["key"])

    def err(msg: str) -> None:
        errors.append({"key": path, "message": msg})

    if t in ("text", "textarea", "gstin", "pan", "pincode", "phone", "email"):
        if isinstance(value, (int, float)) and t in ("pincode", "phone"):
            value = str(int(value))
        if not isinstance(value, str):
            err(f"{label} must be text"); return None
        value = value.strip()
        if t in ("gstin", "pan"):
            value = value.upper().replace(" ", "")
        if t == "email":
            value = value.lower()
            if not EMAIL_RE.match(value):
                err(f"{label} must be a valid email"); return None
        if "minLength" in val and len(value) < val["minLength"]:
            err(f"{label} must be at least {val['minLength']} characters")
        if len(value) > val.get("maxLength", 4000 if t == "textarea" else 500):
            err(f"{label} is too long")
        pattern = val.get("pattern") or DEFAULT_PATTERNS.get(t)
        if pattern and not re.match(pattern, value):
            err(val.get("message") or f"{label} is not valid")
        return value
    if t in ("number", "currency"):
        if isinstance(value, bool):
            err(f"{label} must be a number"); return None
        if isinstance(value, str):
            try:
                value = float(value.replace(",", "").replace("₹", "").strip())
            except ValueError:
                err(f"{label} must be a number"); return None
        if not isinstance(value, (int, float)):
            err(f"{label} must be a number"); return None
        if "min" in val and value < val["min"]:
            err(f"{label} must be at least {val['min']}")
        if "max" in val and value > val["max"]:
            err(f"{label} must be at most {val['max']}")
        return int(value) if float(value).is_integer() else value
    if t == "toggle":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if t == "date":
        s = str(value).strip()[:10]
        try:
            d = dt.date.fromisoformat(s)
        except ValueError:
            err(f"{label} must be a date (YYYY-MM-DD)"); return None
        other = val.get("afterField")
        if other and isinstance(full.get(other), str):
            try:
                if d < dt.date.fromisoformat(full[other][:10]):
                    err(f"{label} must be after {other}")
            except ValueError:
                pass
        return s
    if t in ("select", "multiselect"):
        opts = field.get("options") or []
        by_value = {str(o["value"]): o["value"] for o in opts}
        by_label = {str(o["label"]).lower(): o["value"] for o in opts}
        open_ = bool(field.get("optionsSource")) or not opts

        def one(x: Any) -> Any:
            sx = str(x).strip()
            if sx in by_value:
                return by_value[sx]
            if sx.lower() in by_label:
                return by_label[sx.lower()]
            if open_ and sx:
                return sx
            err(f"{label}: '{sx[:40]}' is not an allowed option")
            return None
        if t == "select":
            if isinstance(value, (list, dict)):
                err(f"{label} must be a single option"); return None
            return one(value)
        if isinstance(value, str):
            value = [v for v in value.split(",") if v.strip()]
        if not isinstance(value, list):
            err(f"{label} must be a list"); return None
        out = []
        for x in value:
            c = one(x)
            if c is not None and c not in out:
                out.append(c)
        return out
    if t == "geo":
        if not isinstance(value, dict):
            err(f"{label} must be {{lat, lng}}"); return None
        try:
            lat, lng = float(value.get("lat")), float(value.get("lng"))
        except (TypeError, ValueError):
            err(f"{label} must be {{lat, lng}}"); return None
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            err(f"{label} is out of range"); return None
        return {"lat": lat, "lng": lng}
    if t == "file":
        if isinstance(value, str):
            return {"name": value.strip()[:300]}
        if isinstance(value, dict) and (value.get("name") or value.get("docId") or value.get("url")):
            return {k: str(value[k])[:500] for k in ("name", "docId", "url", "mime", "size") if value.get(k) is not None}
        err(f"{label} must be an uploaded file reference"); return None
    if t == "repeater":
        if not isinstance(value, list):
            err(f"{label} must be a list"); return None
        if "minItems" in val and len(value) < val["minItems"]:
            err(f"{label} needs at least {val['minItems']} entries")
        if len(value) > val.get("maxItems", 200):
            err(f"{label} has too many entries")
        rows = []
        for i, item in enumerate(value[:200]):
            if not isinstance(item, dict):
                err(f"{label} entry {i + 1} must be an object"); continue
            rows.append(_validate_fields(field.get("fields") or [], item, errors, prefix=f"{path}[{i}]."))
        return rows
    err(f"{label}: unsupported type {t}")
    return None


def _validate_fields(fields: list[dict], data: dict, errors: list, prefix: str = "", partial: bool = False) -> dict:
    out: dict = {}
    for f in fields:
        k = f["key"]
        present = k in data and not _empty(data[k])
        if not present:
            if f.get("required") and not partial:
                errors.append({"key": prefix + k, "message": f"{f.get('label', k)} is required"})
            continue
        v = _coerce(f, data[k], prefix + k, errors, data)
        if v is not None and not _empty(v):
            out[k] = v
    return out


def validate(scope: str, profile: dict, partial: bool = False) -> tuple[dict, list[dict]]:
    """Returns (clean flat profile with only schema keys, errors). partial=True skips required checks."""
    data = flatten(scope, profile or {})
    errors: list[dict] = []
    clean = _validate_fields(fields_for(scope), data, errors, partial=partial)
    g, p = clean.get("gstin"), clean.get("pan")
    if g and p and g[2:12] != p:
        errors.append({"key": "gstin", "message": "GSTIN characters 3-12 must match the PAN"})
    return clean, errors


def completeness(scope: str, profile: dict) -> float:
    fs = fields_for(scope)
    filled = sum(1 for f in fs if not _empty((profile or {}).get(f["key"])))
    return round(filled / len(fs), 3) if fs else 0.0
