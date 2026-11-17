# Browser QA

Browser QA is a mandatory gate for user-facing phases and uses **Tencent BrowserSkill MCP**.
HTTP requests, source inspection, and `browser-use`/Puppeteer are not accepted substitutes.

## Prerequisites

1. BrowserSkill CLI installed: `bsk --version` (0.5.0 on this machine).
2. Browser extension installed and connected:
   - Chrome: https://chromewebstore.google.com/detail/hhcmgoofomhgciiibhipgmgkgnoenaoi
   - Edge: https://microsoftedge.microsoft.com/addons/detail/browserskill/emacgiaaaiojkkpkddmmdfhmokgmnikg
3. Keep a browser window open with the extension enabled until the popup shows "connected".
4. Verify: `bsk doctor` must show `ok extension connected`.
5. OpenCode MCP server `browser-skill` is configured in `opencode.json`:
   `bsk mcp`.

## Workflow

1. `bsk_session action=browsers`
2. `bsk_session action=start`
3. `bsk_page action=navigate`
4. `bsk_session action=sync` (obtain `context_id`, `observation_id`, VOM refs)
5. `bsk_inspect` for text/console/network/screenshot
6. `bsk_interact` / `bsk_plan` for interactions
7. `bsk_session action=stop` (always)

Record test results under `results/`, screenshots under `screenshots/`.
Never store passwords, access tokens, cookies, or secrets.

## Status

- MCP connectivity: configured and tools discovered.
- Browser extension connection: **CONNECTED** (Chrome 157, extension 0.5.0).
- BT-001 example.com smoke test: **PASS**; session stopped.
- OrgWeave browser E2E: pending; use this workflow for each user-facing phase.
