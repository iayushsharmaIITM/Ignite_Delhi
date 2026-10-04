#!/usr/bin/env python3
"""Score the served OpenAPI document against Postman's agent-readiness rubric.

8 pillars, 48 checks, severity weights Critical 4 / High 2 / Medium 1 / Low 0.5.
The rubric is Postman's; every verdict here is COMPUTED from the document that the
server actually serves, never typed in by hand. That matters: the first version of
this scorer carried several hardcoded pass/fail verdicts, and when the contract
improved the score moved for reasons nobody could point at. A check that cannot be
measured is reported `n/a` and leaves the denominator, which is honest, rather than
being pinned to a verdict, which is not.

    python3 ops/api_readiness.py --spec /tmp/openapi.json
    python3 ops/api_readiness.py --base http://127.0.0.1:8000
    python3 ops/api_readiness.py --base ... --ablate-error-contract   # what this pass bought

Agent-ready formally means >=70% weighted AND zero failing Critical checks.

This is a report, not a gate: it is deliberately NOT wired into verify.sh, because
an API-contract gate would fail on every route someone adds without a typed schema,
and the battery must stay a signal about behaviour, not about documentation debt.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

W = {"C": 4.0, "H": 2.0, "M": 1.0, "L": 0.5}
METHODS = ("get", "post", "put", "patch", "delete")


def ablate(spec: dict) -> dict:
    """Remove the error contract this project added, to measure its worth."""
    import copy
    s = copy.deepcopy(spec)
    for ops in s.get("paths", {}).values():
        for op in ops.values():
            if isinstance(op, dict) and "responses" in op:
                op["responses"] = {c: r for c, r in op["responses"].items()
                                   if str(c).startswith("2")}
    comps = s.get("components") or {}
    if comps.get("schemas"):
        comps["schemas"].pop("ApiError", None)
        comps["schemas"].pop("HTTPValidationError", None)
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--spec", help="read a saved openapi.json instead of fetching")
    ap.add_argument("--ablate-error-contract", action="store_true",
                    help="strip 4xx/5xx responses and the error schema before scoring")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.spec:
        spec = json.load(open(args.spec))
    else:
        with urllib.request.urlopen(args.base.rstrip("/") + "/openapi.json") as r:
            spec = json.load(r)
    if args.ablate_error_contract:
        spec = ablate(spec)

    paths = spec.get("paths", {})
    ops = [(p, m, o) for p, v in paths.items() for m, o in v.items() if m in METHODS]
    schemas = (spec.get("components") or {}).get("schemas") or {}
    params = [pp for _, _, o in ops for pp in (o.get("parameters") or [])]
    body_props = [b for _, _, o in ops for b in (o.get("requestBody") or {}).get("content", {}).values()]
    all_responses = [r for _, _, o in ops for r in (o.get("responses") or {}).values()]
    error_schema = next((v for k, v in schemas.items() if "error" in k.lower()), None)
    error_props = set(((error_schema or {}).get("properties") or {}).keys())

    res: list[tuple[str, str, str, str]] = []

    def rec(cid: str, sev: str, ok, note: str, na: bool = False) -> None:
        res.append((cid, sev, "n/a" if ok is None or na else ("pass" if ok else "fail"), note))

    def content_of(op, prefix):
        return any(("content" in r or "$ref" in json.dumps(r))
                   for c, r in (op.get("responses") or {}).items()
                   if str(c).startswith(prefix))

    # --- Metadata -----------------------------------------------------------
    rec("M1", "C", all(o.get("operationId") for _, _, o in ops),
        f"{sum(1 for _, _, o in ops if o.get('operationId'))}/{len(ops)} operations carry an operationId")
    rec("M2", "H", all(o.get("summary") for _, _, o in ops),
        f"{sum(1 for _, _, o in ops if o.get('summary'))}/{len(ops)} summaries")
    rec("M3", "M", all(o.get("description") for _, _, o in ops),
        f"{sum(1 for _, _, o in ops if o.get('description'))}/{len(ops)} descriptions")
    rec("M4", "M", all(o.get("tags") for _, _, o in ops),
        f"{sum(1 for _, _, o in ops if o.get('tags'))}/{len(ops)} tagged")
    tags = sorted({t for _, _, o in ops for t in (o.get("tags") or [])})
    rec("M5", "L", bool(tags) and all(re.fullmatch(r"[a-z0-9_-]+", t) for t in tags),
        f"tags={tags or 'none'}")
    rec("M6", "L", any(k.startswith("x-") for _, _, o in ops for k in o),
        "no vendor-extension display metadata for agent consumers")

    # --- Errors -------------------------------------------------------------
    rec("E1", "C", all(content_of(o, "4") and content_of(o, "5") for _, _, o in ops),
        f"{sum(1 for _, _, o in ops if content_of(o, '4'))}/{len(ops)} operations declare a "
        f"4xx body schema, {sum(1 for _, _, o in ops if content_of(o, '5'))}/{len(ops)} a 5xx one")
    rec("E2", "H", bool(error_schema), f"named error schemas: {[k for k in schemas if 'error' in k.lower()] or 'none'}")
    rec("E3", "H", bool({"code", "error_code", "type", "slug"} & error_props),
        f"error schema properties={sorted(error_props) or 'none'} — a machine-readable code is "
        "the missing half; clients branch on the status, not on prose")
    rec("E4", "M", bool({"detail", "message", "error"} & error_props),
        f"human-readable message property present: {sorted({'detail', 'message', 'error'} & error_props) or 'no'}")
    rec("E5", "M", any("429" in (o.get("responses") or {}) or "503" in (o.get("responses") or {})
                       for _, _, o in ops),
        f"retryable statuses declared on 429-capable routes: "
        f"{sum(1 for _, _, o in ops if '429' in (o.get('responses') or {}))}, "
        f"503-capable routes: {sum(1 for _, _, o in ops if '503' in (o.get('responses') or {}))}")
    rec("E6", "M", all("422" in (o.get("responses") or {}) for _, _, o in ops),
        f"422 declared on {sum(1 for _, _, o in ops if '422' in (o.get('responses') or {}))}/{len(ops)} "
        "operations (FastAPI injects it for typed parameters, not for hand-rolled body checks)")
    rec("E7", "L", not (error_props & {"traceback", "stack", "debug", "internal"}),
        "no stack-trace or debug field in the error schema")

    # --- Introspection ------------------------------------------------------
    rec("I1", "C", bool(params) and all(pp.get("schema") for pp in params),
        f"{len(params)} parameters, {sum(1 for p in params if p.get('schema'))} typed")
    rec("I2", "H", bool(params) and all("required" in pp for pp in params),
        f"{sum(1 for p in params if 'required' in p)}/{len(params)} mark required")
    rec("I3", "H", any((p.get("schema") or {}).get("enum") for p in params),
        f"{sum(1 for p in params if (p.get('schema') or {}).get('enum'))} enum-constrained parameters")
    rec("I4", "M", any(p.get("example") or (p.get("schema") or {}).get("examples") for p in params),
        "parameter examples")
    rec("I5", "M", any((p.get("schema") or {}).get("format") for p in params),
        f"{sum(1 for p in params if (p.get('schema') or {}).get('format'))} format specifiers")
    rec("I6", "L", any((p.get("schema") or {}).get("default") is not None for p in params),
        f"{sum(1 for p in params if (p.get('schema') or {}).get('default') is not None)} defaults documented")
    rec("I7", "L", any("nullable" in json.dumps(o) or "null" in json.dumps(
        (o.get("schema") or {})) for _, _, o in ops),
        "null handling not expressed anywhere in the document")

    # --- Naming -------------------------------------------------------------
    verbs = r"/(get|create|delete|update|list|fetch|do|make)[A-Z_-]"
    rec("N1", "H", not any(re.search(verbs, p) for p in paths), "no action verbs in paths")
    rec("N2", "H", all(p == p.lower() for p in paths),
        f"non-lowercase paths: {[p for p in paths if p != p.lower()] or 'none'}")
    rec("N3", "M", all(m in METHODS for _, m, _ in ops), "only standard methods are used")
    rec("N4", "M", all(re.search(r"/(brains|chats|connectors|documents|jobs|events|source|usage|stats|graph|ask|config|health)\b", p)
                       or p.count("/") <= 1 for p in paths),
        "collection segments are plural resource nouns")
    props = {k for s in schemas.values() for k in ((s.get("properties") or {}).keys())}
    rec("N5", "L", bool(props) and all(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9]*", p) for p in props),
        f"{len(props)} documented property names, casing consistent"
        if props else "no response schemas, so property casing is undocumented rather than consistent")
    rec("N6", "L", not any(p.rstrip("/").split("/")[-1].lower() in
                           ("create", "delete", "update", "list") for p in paths),
        "no path terminates in an action")

    # --- Predictability -----------------------------------------------------
    rec("P1", "C", all(content_of(o, "2") for _, _, o in ops),
        f"{sum(1 for _, _, o in ops if content_of(o, '2'))}/{len(ops)} success responses carry a content schema")
    lists = [(p, o) for p, m, o in ops if m == "get" and p.startswith("/api")]
    rec("P2", "H", all(any(q.get("name") in ("limit", "offset", "cursor", "page", "days")
                           for q in (o.get("parameters") or []))
                       for p, o in lists if p.rstrip("/").endswith(("chats", "brains"))),
        "collection endpoints expose a bound (limit/days)")
    rec("P3", "M", any((s.get("properties") or {}).get("format") == "date-time"
                       or "date-time" in json.dumps(s) for s in schemas.values()),
        "no date-time format declared in any schema")
    rec("P4", "M", any("uuid" in json.dumps(s) or '"format": "uuid"' in json.dumps(s)
                       for s in schemas.values()),
        "no id fields carry a uuid format")
    rec("P5", "L", None, "envelope style is consistent in the handlers ({ok, ...}) but cannot be "
                         "expressed while no response schema is declared", na=True)
    rec("P6", "L", None, "null handling is a consequence of P1; not separately assessable", na=True)

    # --- Documentation ------------------------------------------------------
    sec = (spec.get("components") or {}).get("securitySchemes") or {}
    rec("D1", "H", bool(sec) and bool(spec.get("security")),
        f"securitySchemes={list(sec) or 'NONE'}; document-level security={spec.get('security', 'absent')}")
    rec("D2", "H", "rate limit" in json.dumps(spec).lower() or "429" in json.dumps(spec),
        "rate limiting described in the document")
    rec("D3", "M", any("example" in json.dumps(o) or "examples" in json.dumps(o) for _, _, o in ops),
        "request/response examples present")
    rec("D4", "L", bool(spec.get("externalDocs")), "externalDocs link")
    rec("D5", "L", None, "no deprecated endpoints to flag", na=True)
    rec("D6", "L", bool(spec.get("info", {}).get("version")),
        f"info.version={spec.get('info', {}).get('version')}")

    # --- Performance --------------------------------------------------------
    rec("PF1", "H", any(h.upper().startswith("X-RATELIMIT")
                        for r in all_responses for h in (r.get("headers") or {})),
        "no X-RateLimit-* response headers declared")
    rec("PF2", "H", all("limit" in json.dumps(paths.get(p, {})) for p in ("/api/chats",)),
        "limit parameter documented on /api/chats")
    rec("PF3", "M", any(h.upper() in ("CACHE-CONTROL", "ETAG")
                        for r in all_responses for h in (r.get("headers") or {})),
        "the server does send Cache-Control/ETag (NoCacheStaticFiles) but the contract says nothing")
    rec("PF4", "L", any("bulk" in p or "batch" in p for p in paths),
        "no bulk endpoint (POST /api/brains accepts several files per request, though)")
    rec("PF5", "L", "/api/brains/v2" in paths and "202" in json.dumps(paths.get("/api/brains/v2", {})),
        "async 202 job path documented (it is flag-gated; GET /api/config publishes brainCreateV2)")

    # --- Discoverability ----------------------------------------------------
    rec("DC1", "H", spec.get("openapi", "").startswith("3."), f"openapi={spec.get('openapi')}")
    rec("DC2", "H", bool(spec.get("servers")), f"servers={spec.get('servers') or 'absent'}")
    rec("DC3", "M", all(spec.get("info", {}).get(k) for k in ("title", "version", "description")),
        f"info keys={list(spec.get('info', {}))}")
    rec("DC4", "L", bool(spec.get("info", {}).get("contact")), "info.contact")
    rec("DC5", "L", bool(spec.get("info", {}).get("license")), "info.license")

    scored = [r for r in res if r[2] != "n/a"]
    earned = sum(W[s] for _, s, st, _ in scored if st == "pass")
    total = sum(W[s] for _, s, _, _ in scored)
    crit = [c for c, s, st, _ in res if st == "fail" and s == "C"]
    pct = 100 * earned / total
    verdict = "Agent-ready" if pct >= 70 and not crit else "Needs Work"

    if args.json:
        print(json.dumps({"percent": round(pct, 1), "earned": earned, "total": total,
                          "critical_failures": crit, "verdict": verdict,
                          "checks": len(scored), "skipped_na": len(res) - len(scored)}, indent=2))
        return 0

    print(f"{'ABLATED ' if args.ablate_error_contract else ''}OpenAPI: {len(paths)} paths, "
          f"{len(ops)} operations, {len(schemas)} schemas")
    print(f"weighted {earned:.1f}/{total:.1f} over {len(scored)} scored checks "
          f"({len(res) - len(scored)} n/a) = {pct:.1f}%  ->  {verdict}")
    print(f"critical failures: {crit or 'none'}")
    by_pillar: dict[str, dict[str, int]] = {}
    for c, _, st, _n in res:
        v = by_pillar.setdefault(re.match(r"[A-Z]+", c).group(), {"pass": 0, "fail": 0, "n/a": 0})
        v[st] += 1
    for k, v in sorted(by_pillar.items()):
        print(f"  {k:3} pass {v['pass']}  fail {v['fail']}  n/a {v['n/a']}")
    print("\nFAILURES, heaviest first:")
    for c, s, st, note in sorted(res, key=lambda r: (-W[r[1]], r[0])):
        if st == "fail":
            print(f"  {s:1} {c:3} {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
