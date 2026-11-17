# BT-001 — BrowserSkill MCP example.com smoke test

- **Status:** PASS
- **Date:** 2026-11-17
- **Feature:** BrowserSkill MCP connectivity and basic browser observation
- **Browser session:** `rrnl` (stopped after test)
- **Browser:** Chrome 157.0.0.0, BrowserSkill extension 0.5.0, protocol 1.9
- **Test account / tenant:** N/A (public page, no login)

## Connection checks

- BrowserSkill MCP configured in `opencode.json` (`bsk mcp`); tools discovered.
- `bsk_session({"action":"browsers"})` returned one connected Chrome instance (`533c3840`).
- `bsk doctor`: daemon running, protocol compatible, extension connected.

## Actual user/browser steps

1. Created a dedicated BrowserSkill session:
   `bsk_session(action=start, browser=533c3840, name="OrgWeave Browser QA - example.com")`
   → `session_id=rrnl`, Agent Window `716109367`.
2. Navigated:
   `bsk_page(action=navigate, session=rrnl, url=https://example.com, wait_until=domcontentloaded)`
   → `final_url=https://example.com/`, reached `domcontentloaded`.
3. Synchronized and observed VOM:
   `bsk_session(action=sync, session=rrnl, policy=target)`
   → RootWebArea **"Example Domain"**, one `Learn more` link to iana.org.
4. Read DOM fields:
   `bsk_inspect(action=read)` → `page_url=https://example.com/`, `title="Example Domain"`,
   first paragraph text returned (multilingual documentation notice).
5. Captured screenshot:
   `bsk_inspect(action=screenshot)` → PNG 937×979; saved as
   `docs/browser-tests/screenshots/BT-001-example-com.png` (82 KB).
6. Inspected Console:
   `bsk_inspect(action=console, limit=100)` → **0 entries**, no errors.
7. Inspected Network:
   `bsk_inspect(action=network, limit=100)`:
   - `GET https://example.com/` → 200, `text/html` (Document)
   - `GET https://example.com/s.js` → 200, `text/javascript`
   - data:image PNG response → 200
   No failed requests.
8. Stopped the session: `bsk_session(action=stop, session=rrnl)` → `{"stopped":["rrnl"]}`.

## Expected vs actual

| Item | Expected | Actual |
|---|---|---|
| Page URL | `https://example.com/` | `https://example.com/` |
| Title | `Example Domain` | `Example Domain` |
| Visible text | Documentation example notice | Multilingual paragraphs + `Learn more` |
| Screenshot | Captured | `screenshots/BT-001-example-com.png` (937×979) |
| Console errors | None | 0 console entries |
| Network failures | None | Document/script/image all 200 |
| Session cleanup | Stopped | `{"stopped":["rrnl"]}` |

## Result

**PASS.** BrowserSkill MCP was used for every browser action; no HTTP/source-reading
substitute was used. No password, cookie, token, or secret was recorded.
