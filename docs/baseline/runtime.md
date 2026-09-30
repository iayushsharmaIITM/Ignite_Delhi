# Runtime baseline — 2026-09-30T21:07Z

## Git
- HEAD: 51e86d1 (docs: delta plan — baseline/diagnosis findings + reversible PR sequence)

## Containers (image : tag @ digest)
- cognee-oss: cognee/cognee:1.6.1 (Up 23 hours (healthy))
- kestrel-langfuse: langfuse/langfuse:2 (Up 27 hours)
- kestrel-db: postgres:17-alpine (Up 27 hours (healthy))
- cognee/cognee:1.6.1 digest=sha256:db0973f4b913d73daa4061bc19362cde6edc59d1be8243b6667fade364b06428
- postgres:17-alpine digest=sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
- langfuse/langfuse:2 digest=sha256:85c278dcab96c15db94191a5c1664f85aba2d7fb6771a00e99681c902c4b7015

## Cognee container self-report
- `cognee.__version__` = 1.6.1-local (does not match a published release string — provenance check queued for candidate phase, N11)

## Host app runtime (the interpreter that actually runs app.py)
- python3 = Python 3.13.3 at /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
- launch: ops_stack_up.sh → nohup python3 app.py (no venv)
- key packages (python3 -m pip freeze):
  - alembic==1.17.2
  - cryptography==48.0.1
  - fastapi==0.115.0
  - fastapi-limiter==0.1.6
  - psycopg==3.2.3
  - psycopg-binary==3.2.3
  - pydantic==2.12.5
  - pydantic-ai-slim==2.51.0
  - pydantic-graph==2.51.0
  - pydantic-settings==2.15.0
  - pydantic_core==2.41.5
  - PyJWT==2.10.1
  - PyMuPDF==1.26.7
  - pypdf==6.7.5
  - PyPDF2==3.0.1
  - pypdfium2==5.6.0
  - python-docx==1.2.0
  - python-dotenv==1.0.1
  - python-jose==3.3.0
  - requests==2.32.5
  - requests-oauthlib==2.0.0
  - requests-toolbelt==1.0.0
  - starlette==0.38.6
  - uvicorn==0.32.0

## requirements.txt drift
- requirements.txt pins fastapi==0.141.1; runtime has 0.115.0. Runtime lags the pin — record only, no action this phase.

## 1.6.2 target artifact check (A9)
- tag cognee/cognee:1.6.2 EXISTS in registry
- tag cognee/cognee:1.6.2 EXISTS in registry
- descriptor digest: (single-manifest; see layers)
- platforms: amd64/linux, arm64/linux, unknown/unknown
