# Damon real-model gate V1

## Scope and decision

REAL-MODEL-GATE = CLOSED. REAL MODEL SMOKE = NO-GO.

V1 cannot authorize a real request. OS_EGRESS and COST_CAP remain UNVERIFIED;
there is no environment flag, operator confirmation, report argument, or HTTP
parameter that opens the gate. Endpoint allowlisting, three attempts, timeout,
and 512 tokens do not establish a monetary hard cap or OS network isolation.

## Boundaries and call chain

Damon API → frozen server Profile snapshot → ChatRegistry →
`stream_snapshot_text` → `_openai_client` → SDK. The stream entry rejects real
execution, and the shared factory independently rejects any explicit `base_url`
configuration before constructing HTTPX or SDK clients. Presence of the keyword,
including None or invalid values, selects this branch; model names, protocol
names, endpoint strings and call-stack inspection are not used to identify callers.

The legacy factory branch omits `base_url` and retains its original global
configuration, retry count and HTTP client behavior. The old assistant dispatcher,
Settings, authentication and credential store are unchanged. There is no fallback
to those paths on gate rejection. The existing Damon API emits its safe generic
upstream error terminal; it does not expose a new gate-status endpoint. Existing
Profile resolution precedes streaming and may resolve a server-side credential;
the gate itself neither loads nor prints credential values.

Trusted offline tests may inject an exact `httpx.MockTransport` through the Python
adapter seam. It is not a browser/API parameter, an authorization credential or a
sandbox for untrusted Python callbacks. DAMON-OFFLINE continues to inject its
FakeModel and does not reach this real-client branch.

## Eight checks

| Check | V1 meaning |
| --- | --- |
| EXECUTION_ISOLATION | Observe the actual fresh Sandbox, temporary data/env paths, import guard, single-worker/no-reload declaration and absence of loaded business modules/extra threads. Missing evidence is UNVERIFIED; conflicting evidence FAIL. This is preflight observation, not deployment or OS proof. |
| REQUEST_BUDGET | Server-side process-local locked primitive: at most three admissions, one active lease, no refund for failure/timeout/cancel; uncertain cancellation holds its lease and closes future admission. Missing runtime is UNVERIFIED. |
| PROMPT_LIMITS | Last user input 1–1000 Python Unicode code points; complete message contents including system prompt at most 3000; max_tokens 1–512. Missing request is UNVERIFIED. |
| ENDPOINT_ALLOWLIST | Fixed `api.openai.com`, HTTPS, port 443, empty/root/v1 path. ASCII host comparison ignores case and one trailing dot. Reject userinfo, IP literals, encoded authority, query/fragment, IDN/punycode and arbitrary hosts. No DNS resolution or DNS-rebinding guarantee. |
| PROXY_ENVIRONMENT | Dedicated client options trust_env=False, follow_redirects=False, retries=0; verified using real SDK plus fake transport, including inherited proxy variables. Legacy clients unchanged. |
| OS_EGRESS | Always UNVERIFIED: no machine-verifiable OS/container/firewall enforcement exists in V1. |
| COST_CAP | Always UNVERIFIED: no machine-verifiable provider/gateway hard monetary cap exists. |
| CREDENTIAL_AVAILABILITY | Only the existing configuration reference structure is accepted. PASS means structural reference only, not presence or validity of a real key; absent reference FAIL. No secret read, hash, log or connection probe. |

Reports contain overall_status, ready, checks, check_id, status, reason_code,
human_summary and fixed evidence codes. Required FAIL/UNVERIFIED prevents ready.
`GateClosedError` has a fixed message and structured safe report. Even an altered
report cannot open the V1 client guard.

The budget/prompt policy is a tested server primitive for future integration;
V1 has no admitted real dispatch. It must be bound to actual request lifecycle
before a future opening is considered. Chat Completions maps 512 to max_tokens;
Responses maps it to max_output_tokens. Both are tested through the real SDK with
MockTransport. Existing 60-second server deadline, 70-second browser fallback,
16000-code-point output contract and cancellation logic remain unchanged.

## Preflight

From backend, using the existing locked environment:

```powershell
uv run --frozen --no-sync --offline python -B scripts/damon_real_preflight.py
```

The script accepts no arguments. It creates and removes a fresh Sandbox before
any app/config/auth/provider/logging imports, constructs no model client, reads no
credential value, opens no listener, and prints JSON. Exit **2** is expected
CLOSED/NO-GO; invalid arguments fail with exit 1. No success/open exit is provided.
Its reference endpoint is a static policy example, not discovered configuration.
Without a request or credential reference, prompt is UNVERIFIED and credential
reference FAIL; OS and cost remain UNVERIFIED even when all local checks pass.

## Offline verification and limitations

`tests/test_damon_real_gate.py` covers real API/registry/stream/factory rejection,
forged snapshots, both protocols and model names, constructor/DNS exclusion,
safe exception/log output, endpoint normalization/rejection, Unicode boundaries,
locked concurrent admission, cancellation budgets, SDK proxy behavior and token
mapping, legacy branch preservation and fresh-process preflight cleanup.
Existing SDK logging/parser tests explicitly inject MockTransport; their logging,
terminal-state and cleanup assertions remain in force.

Regression commands and current counts are recorded in the task delivery report.
The regression runner clears inherited business credentials, uses an isolated
temporary DATA_DIR/env and denies external Python audit socket/DNS events and
production data-file access. This is trusted Python test protection, not an OS,
native-code or child-process sandbox. No real credentials, model/network service,
billing, voice, production database or browser smoke test is validated.

### 2026-10-19 candidate verification

Tests used `uv run --frozen --no-sync --offline python -B -c $runner` from backend.
The in-memory runner retained only OS loader/temp variables, cleared business
environment, set a unique `damon-final-regression-*` DATA_DIR and nonexistent env
file, blank AI/TickFlow/auth values, and redirected temp/home/pytest cache paths
to that temporary root. It installed a Python audit guard for non-loopback
socket/DNS operations and repository production data/env reads, self-tested both
external connect/DNS rejection paths, then invoked:

```python
pytest.main(selection + ["-q", "--tb=short", "-o", "cache_dir=" + temporary_cache,
                         "--basetemp=" + temporary_test_directory])
```

No fixture-repair plugin, thread override or excluded test was used. Child
processes inherit the sanitized environment, not the parent's in-memory audit
hook; the fresh preflight/offline child installs its own existing Sandbox guards.

- Final Gate selection: `tests/test_damon_real_gate.py` — 86 PASS, exit 0,
  pytest 11.37s (runner 12.62s).
- Related selection — 280 PASS, exit 0, pytest 152.62s (runner 153.80s):
  `test_auth_env_bootstrap`, `test_ai_provider`, `test_damon_chat`,
  `test_ai_sdk_logging`, `test_damon_ai`, `test_ai_responses`,
  `test_secrets_external_edit`, `test_custom_assistant`,
  `test_custom_assistant_sessions`, `test_extensions`,
  `test_quote_market_boundary`, `test_market_provider_contracts`,
  `test_anomaly_intelligence`, `test_damon_offline` (all under `tests/`, `.py`).
- Complete selection `tests` — **4381 PASS / 1 FAIL / 6 skipped / 1 xfailed**,
  214 warnings, exit 1, pytest 419.29s (runner 421.00s). The failing assertion is
  `tests/backtest/test_worker_process.py::test_spawn_worker_returns_compact_result_and_memory_metrics`:
  worker_exitcode was 3221225477 (`0xC0000005`) instead of zero. This is a native
  exit failure, not proof of the historical ten-second exit-timeout mechanism.
  ROOT CAUSE UNKNOWN. Worker code/tests and thresholds were not changed; no retry
  or controlled-thread pass replaces this failing complete-suite result.
  The parent audit guard counted three denied network events, including its two
  deliberate self-checks. The third event was blocked but its originating test
  was not recorded by this runner, so attribution is NOT VERIFIED. These counts
  cannot establish OS-wide or child-process egress guarantees.
- Earlier Gate iteration: 85 PASS / 1 FAIL; its fake SSE fixture contained only
  a terminal event with no answer. The production parser correctly rejected it.
  The fixture now supplies answer delta plus terminal and asserts the answer;
  no parser assertion or implementation was weakened.
- New Gate/script/tests and two adjusted existing tests: Ruff PASS. Including
  shared `ai_provider.py` reports one BLE001 at the unchanged upstream-error
  body accessor. `git show HEAD:backend/app/services/ai_provider.py` piped to
  Ruff confirms the same baseline BLE001; it was not repaired in this task.
- Frontend/build/browser and real network/model/billing validation: NOT RUN.

### 2026-10-19 causal audit (historical evidence at Git closure)

The implementation-round failure above remains part of the record: **4381 PASS /
1 FAIL**, worker exitcode **3221225477 / 0xC0000005**. The following later green
results do not replace that failure or establish a Worker fix.

The causal audit used the candidate worktree and a temporary detached baseline
at `dfeb82bdd339f97bf2386bc3c432c89a4649cbae`. Both used the same virtual-environment
Python, identical uv.lock, default threads, original assertions, diagnostics off,
fresh DATA_DIR/env, empty business credentials and the same Python audit guard.
An observational pytest hook recorded only safe numeric Worker return metrics;
it did not replace Worker functions, fixtures or assertions. Baseline module
resolution and Worker source identity were checked. The temporary baseline
worktree was safely removed after verification.

| Later causal-audit execution | Result | Pytest time / exit |
| --- | --- | --- |
| Candidate targeted Worker, five alternating trials | 5/5 PASS; each worker exitcode 0 | Each runner 5.53–9.95s; exit 0 |
| Baseline targeted Worker, five alternating trials | 5/5 PASS; each worker exitcode 0 | Each runner 6.11–7.84s; exit 0 |
| Candidate complete backend | 4382 PASS / 0 FAIL / 6 skipped / 1 xfailed | 379.45s / 0 |
| Baseline complete backend | 4296 PASS / 0 FAIL / 6 skipped / 1 xfailed | 382.33s / 0 |
| Gate targeted | 86 PASS | 8.94s / 0 |
| Independent DNS-source test, candidate / baseline | 1 PASS each | 1.50s / 1.66s; exit 0 each |

The target returned its complete result in each trial, was not forcibly
terminated and generated no diagnostic directory. Neither the native crash nor
the historical unexpected ten-second exit timeout reproduced in this audit.
Negative trials do not establish causality:

**Worker CAUSALITY = NOT ESTABLISHED. ROOT CAUSE = UNKNOWN.**

The third denied event was reproduced and identified in both complete suites and
in independent runs of `tests/test_abnormal_moves.py::test_build_overview_closeness_and_status`:

```text
test_build_overview_closeness_and_status (test_abnormal_moves.py:259)
  -> abnormal_moves.build_overview (:209)
  -> abnormal_moves._is_closed_session (:36)
  -> trading_day.is_trading_day (:127)
  -> trading_day._probe_tickflow (:90)
  -> TickFlow quotes / HTTPX / httpcore
  -> socket.getaddrinfo (blocked before DNS resolution)
```

Each run recorded two deliberate guard self-checks plus this DNS attempt. The
test leaves the existing trading-day probe unstubbed; the no-key client may use
TickFlow's free service, and the probe catches the guard exception as an unknown
trading-day result. This is an existing test-isolation issue, not an intentional
network-denial assertion or a Damon Gate/model outlet. The relevant test,
abnormal_moves, trading_day and TickFlow wrapper files are identical in candidate
and baseline. They were not changed by either audit or Git closure.

The original historical event has no original stack and cannot be individually
recovered; source attribution rests on the matching current reproductions and
baseline evidence. **Do not claim the complete tests made no outbound attempts.**
The observed attempt was blocked by Python protection, which is not an OS egress
sandbox and does not cover arbitrary native code or spawned processes.

All six Python/test candidates retained their audited SHA-256 values during Git
closure; only this document received the authorized causal-audit supplement.
The full suites above are prior-task evidence, not rerun by Git closure.

**REAL-MODEL-GATE = CLOSED. REAL MODEL SMOKE = NO-GO.**
**OS_EGRESS = UNVERIFIED. COST_CAP = UNVERIFIED.**

### Git-closure validation (2026-10-19)

Only this document was supplemented; all six Python/test file hashes still match
the completed causal audit. The closure task reran the isolated selection
`tests/test_damon_real_gate.py tests/test_ai_sdk_logging.py tests/test_damon_chat.py`:
**134 PASS**, exit 0, pytest 10.08s (runner 10.94s). The only denied network events
were the two deliberate runner self-checks. Ruff passed for real_gate, the
preflight script and these three test files. Complete backend suites were not
rerun; the candidate/baseline counts above remain explicitly prior-task evidence.

The actual standalone preflight returned **exit 2**, as documented for a closed
gate, with ready=false, CLOSED / NO-GO and cleanup_complete=true. Missing request
and credential reference remain unverified/failed local checks; OS_EGRESS and
COST_CAP remain UNVERIFIED. This expected rejection is not a model test failure
or authorization to perform a real request.

Before any future opening: independently verified deployment isolation, OS egress
enforcement and provider/gateway monetary cap; reviewed credential references and
request-bound budget integration; explicit human authorization. SDK upgrades
require renewed logging and transport verification. Worker historical exit-timeout
root cause remains UNKNOWN; passing a suite does not establish a root-cause fix.
