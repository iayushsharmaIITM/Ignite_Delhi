# Connector reality states (Phase 10)

| Connector | State | Classification | Prerequisite to go live |
|---|---|---|---|
| Slack | OAuth + scope-picker + vault fully built; 90/90 stub-suite tests pass | **stub-tested** | A real Slack app (SLACK_CLIENT_ID/SECRET) + one real workspace install + live read/post/revoke tests |
| Gmail | Cognee 1.6.2 `gmail` extra installed in the candidate image; Kestrel-side OAuth entry points exist; no sync worker | **implemented but not configured** | Google OAuth client (GOOGLE_DRIVE_* / GMAIL env), founder test account, Google verification decision (restricted scope) |
| Google Drive | Same as Gmail (first-party connector routes exist in-image) | **implemented but not configured** | Same as Gmail + Drive scope test + file-selection UX |

No connector is production-ready. None is advertised as available: the
marketing site says "Coming soon", the app shows honest "not configured"
states (503 with the exact missing prerequisite). The candidate image ships
the Google packages (verified by import), so the remaining work is
configuration + live-account testing, not installation.
