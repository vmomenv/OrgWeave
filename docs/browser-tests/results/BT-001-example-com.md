# BT-001 — BrowserSkill connectivity and example.com smoke test

- **Status:** BLOCKED
- **Date:** 2026-11-17
- **Feature:** BrowserSkill MCP availability / basic browser observation
- **Test account:** N/A (public page, no login)
- **Tenant:** N/A
- **Browser session:** not created

## Attempted steps and actual observations

1. BrowserSkill MCP discovery
   - `opencode mcp list` after configuration: `browser-skill` server present.
   - MCP tools discovered: `bsk_session`, `bsk_page`, `bsk_inspect`, `bsk_interact`,
     `bsk_plan`, `bsk_tabs`, `bsk_assist` (+ others).
   - Result: **PASS** (MCP transport/tool discovery).
2. CLI/daemon health
   - `bsk doctor`:
     - `ok daemon running`
     - `ok protocol compatible`
     - `FAIL extension connected — 0 browsers connected`
   - Result: **FAIL**.
3. Start dedicated browser session
   - MCP call: `bsk_session({"action":"browsers"})`
   - Actual response: `{"browsers":[]}`
   - MCP call: `bsk_session({"action":"start","name":"example.com smoke","focus":false})`
   - Actual response:
     ```json
     {"code":"no_browser_connected","exit_code":1,
      "hint":"open the browser-skill extension in your browser and wait for the popup to show \"connected\"",
      "message":"no browser is currently connected"}
     ```
   - Result: **BLOCKED** (`no_browser_connected`).

## Requested scenario

| Step | Result |
|---|---|
| 1. Create new BrowserSkill session | BLOCKED |
| 2. Open https://example.com | NOT EXECUTED |
| 3. Get URL/title | NOT EXECUTED |
| 4. Read visible text | NOT EXECUTED |
| 5. Screenshot | NOT EXECUTED |
| 6. Check obvious errors | NOT EXECUTED |
| 7. Report browser operations | Only the blocked start call above |
| 8. End session | No session to end |

## Evidence

- No screenshot exists; no page was opened.
- Console findings: N/A.
- Network findings: N/A.
- No HTTP request was used as a substitute for browser navigation.

## Defect

- **Defect ID:** BQA-ENV-001
- **Type:** environment / setup, not an OrgWeave product defect
- **Root cause:** no browser extension instance connected to the local BrowserSkill daemon.
- **Resolution (user action):** install/enable the BrowserSkill extension in Chrome or Edge,
  keep that browser window open, and confirm the extension popup shows **Connected**.
- **Reproduce after fix:** run `bsk doctor`; `extension connected` must be `ok`. Then rerun
  BT-001. Only after that may this test be marked PASS/FAIL.
