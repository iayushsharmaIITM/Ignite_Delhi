# NEXT — the idea parking lot

Any new idea that arrives after the feature freeze goes here as ONE LINE.
No discussion, no detour. Revisit only after the demo is safe.

| Time | Idea | Verdict |
|------|------|---------|
| 11:20 | Switch to Neo4j backend | Not needed — the cloud tenant already keeps state outside the container. See SPEC §4 |
| 11:35 | Add a Cypher query panel | Deferred — the graph view already proves the data is ours |
| 12:10 | Enable `CONTRADICTION_DETECTION` | Not enabled; the contradiction surfaced anyway from graph traversal |
| 12:40 | Real Slack connector | Killed — the graph is the hard part, the connector is a polling loop |

---

## Kill list (decided at minute 0 — do not relitigate)

- Auth, roles, admin panel
- Payments, emails
- CI/CD, Docker, i18n, dark-mode toggle
- Refactors and "proper architecture"
- More than 4 smoke checks
- Any new framework or unowned abstraction

### Domain-specific additions, decided once PS-2 was chosen

- Real Slack / GitHub / Linear connectors
- Multi-tenancy
- Live ingestion on stage
- Fine-tuning, custom embeddings, agent swarms
- A hand-rolled graph renderer beyond `/graph`

Every item above is a real feature. Each was declined so the features we *did* build
would actually work. **Scope & Prioritisation is worth 5 points on its own** — this list
is a scoring instrument, not an apology.
