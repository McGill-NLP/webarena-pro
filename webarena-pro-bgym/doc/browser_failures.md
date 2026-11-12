# Browser renderer failures

`Frame.evaluate: Target crashed` during DOM marking is an environment failure.
The runner must not interpret a renderer crash as an agent mistake or silently
repeat the preceding action: it may already have changed server state.

## Recorded evidence and behavior

At the first observation, each experiment logs its runtime and writes
`browser_runtime.json` in its experiment directory. It records Python/platform,
AgentLab, BrowserGym and Playwright versions, the running browser version,
Playwright's bundled Chromium revision, and any configured browser channel or
executable override. The bundled revision describes the installed Playwright
package; an explicit executable override can run a different binary.

The adapter watches existing pages and new popups for Playwright's `crash`
event. It also recognizes Playwright renderer-crash exceptions, including those
raised before the first observation. An observed crash or explicit crash error
raises `WebArenaProBrowserCrashError`, records `environment_error` /
`renderer_crash`, and writes `browser_failure.json`. This includes task ID, sites,
operation, completed-step count, page URL, whether the crash event was seen,
and runtime versions. The preceding traceback remains in the ordinary experiment
log. URLs omit credentials, query strings and fragments; for example, Metabase
`/question/notebook#...` is recorded as `/question/notebook`.

The existing fatal-worker path discards the runtime. No browser operation is
retried by this adapter, and a failed environment rejects further steps or
resets. Worker replacement and study resume remain the runner's responsibility.
Ordinary page closure, detached frames, execution-context changes and timeouts
are not reclassified as renderer crashes. A crash event is sufficient even when
BrowserGym or an optional media handler catches the underlying exception.

Diagnostic collection uses cached browser/page metadata, never a fresh
screenshot, DOM evaluation or CDP request against the failed renderer. Sidecar
files are created with private permissions; a filesystem failure to write them
does not replace the original exception.
