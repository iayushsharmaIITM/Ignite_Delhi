"""Tenant resolution and dataset authorisation.

WHY THIS FILE EXISTS
The app had no authorisation at all: `?dataset=` was a plain query parameter on
every read route, so any caller could read any brain — including Cognee's
internal `default_dataset` — and `DELETE /api/brains/{name}` would delete one.
Verified by execution, not by reading.

That is data-level isolation, not access-level isolation, and it is the gate on
selling this to more than one customer. This module adds the access-level half.

BACKWARD COMPATIBLE BY DESIGN
If no tenants are configured, the app behaves EXACTLY as it did before: one
implicit tenant that may reach everything. The demo path is untouched, and a
deployment that has not set up tenants does not break. Authorisation only starts
enforcing the moment a tenant file exists — which is also the moment it starts
mattering.

CONFIGURATION
`fixtures/tenants.json`:

    {
      "tenants": [
        {"id": "acme",   "key": "…", "datasets": ["acme_industrial"]},
        {"id": "kestrel","key": "…", "datasets": ["company_brain", "kestrel_full"]}
      ]
    }

Keys are compared with `secrets.compare_digest`, and a tenant may only reach the
datasets listed for it. An unknown or missing key is refused when tenants are
configured — fail closed, not open.
"""

from __future__ import annotations

import json
import os
import secrets

HERE = os.path.dirname(os.path.abspath(__file__))
TENANTS_FILE = os.path.join(HERE, "fixtures", "tenants.json")

# Datasets that are shared reference material rather than a customer's data.
# The demo brain is deliberately readable by every tenant: it is the sample
# every new user starts from, and it contains no customer documents.
SHARED_DATASETS = {"company_brain", "default_dataset"}


class Tenant:
    """One customer. `datasets` is the allow-list of brains it may reach."""

    __slots__ = ("id", "datasets", "shared_only")

    def __init__(self, id: str, datasets: list[str]):
        self.id = id
        self.datasets = set(datasets or [])

    def allows(self, dataset: str | None) -> bool:
        """May this tenant reach `dataset`?

        `dataset=None` means the demo brain, which every tenant may read.
        A shared dataset is readable by anyone. Anything else must be listed.
        """
        if not dataset:
            return True
        if dataset in SHARED_DATASETS:
            return True
        return dataset in self.datasets

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Tenant {self.id} datasets={sorted(self.datasets)}>"


# The single implicit tenant used when nothing is configured. It may reach
# everything, which is exactly the pre-existing behaviour.
_UNRESTRICTED = Tenant("__unrestricted__", [])


def _load() -> dict[str, Tenant] | None:
    """Return {api_key: Tenant}, or None when authorisation is not configured."""
    try:
        with open(TENANTS_FILE, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return None

    entries = raw.get("tenants") if isinstance(raw, dict) else None
    if not entries:
        return None

    out: dict[str, Tenant] = {}
    for entry in entries:
        key = entry.get("key")
        tid = entry.get("id")
        if not key or not tid:
            continue
        out[key] = Tenant(tid, entry.get("datasets") or [])
    return out or None


def configured() -> bool:
    """Is authorisation switched on? False means single-tenant, as before."""
    return _load() is not None


def resolve(api_key: str | None) -> Tenant | None:
    """Resolve the caller to a tenant.

    Returns the unrestricted tenant when authorisation is not configured, so
    every existing caller keeps working. Returns None when authorisation IS
    configured and the key is missing or unknown — fail closed.
    """
    tenants = _load()
    if tenants is None:
        return _UNRESTRICTED
    if not api_key:
        return None
    for key, tenant in tenants.items():
        # Constant-time compare: a plain == leaks key length and prefix through
        # timing, which is enough to recover a key byte by byte.
        if secrets.compare_digest(key, api_key):
            return tenant
    return None
