# Mining Worker exit diagnostics v1

## Scope and activation

Opt-in diagnostic instrumentation only. Initial candidate baseline:
`66c4f00a14f119577b9151e02d677b2e623eb97a`; final hardening baseline:
`80339dc95c52d5e40e399c639064d2aa7ebaae0a`.
Set `TSP_WORKER_EXIT_DIAGNOSTICS=1` in the invoking process before running the
existing worker task or tests. Unset it to disable. Other values do not enable it.
No worker timeout, calculation, fixture, exit-code assertion or provider behavior
is changed. No production task is started by enabling the flag.

Each invocation creates a separate `tsp-worker-exit-*` directory in the system
temporary directory. The parent logs the directory location at INFO level.
An internal task-envelope field passes this path to the spawned child; the
caller's task dictionary and business config/result are not mutated.

## Evidence files

- `parent.jsonl`: terminal receipt/missing status, exit wait return (including
  captured wait-start monotonic time), timeout, termination outcome, setup failure
  reason, and parent cleanup completion/incomplete path.
- `child.jsonl`: terminal put start/enqueued, cleanup start, DuckDB close
  start/completed/failed, queue close start/completed/failed, feeder join start/completed/failed,
  cleanup completed/incomplete, diagnostic cleanup start, and the last marker
  before the event log closes and `os._exit(0)` (watchdog already canceled).
- `child-stacks.log`: one bounded Python stack dump, scheduled for 8 seconds
  after entering terminal-message submission. This is before the unchanged
  parent's 10-second exit wait deadline in the normal terminal-delivery sequence.

Each stage includes PID, monotonic time, elapsed milliseconds from that process's
probe initialization and milliseconds since its previous marker. Paired
start/completed markers bound the corresponding operation's duration. Parent
wait records also contain actual wait time, process liveness and exit code.
Parent exit markers are emitted only after the 10-second join and, if needed,
terminate + unchanged 5-second join have completed and the child is no longer alive.
Their emission timestamp is not the original terminal-receipt timestamp;
wait_started_monotonic and waited_ms describe the captured wait interval.
There is no diagnostic file read/write/flush between the expired 10-second wait
and terminate. Only after termination does the parent read the child log tail;
missing, partial or unreadable records yield null (UNKNOWN).

`terminal_enqueued` means `Queue.put` returned, not that the feeder finished.
Only the parent's `terminal_received` proves receipt. `cleanup_completed` requires
successful database closure (or no database created) and queue feeder join.
`process_exit_imminent` does not prove that `os._exit` ran or the OS finished exit;
the parent observes the eventual exit code separately.

## Resource and safety boundaries

Default-off execution opens no diagnostic files and arms no watchdog. Enabled
execution uses synchronous small JSONL writes with flush (no fsync), no new Python
diagnostic thread and one nonrepeating faulthandler watchdog in the spawned child.
Normal cleanup cancels the watchdog before closing its file; all diagnostic file
handles are closed on the exercised normal/error paths. A forced child termination
relies on OS handle reclamation. A closed probe cannot rearm, and even a failed
arming attempt is not retried within that probe.
Logs remain for inspection, with no automatic deletion or rotation across runs.

No task config, result, credentials, request body, exception message or business
identity is serialized by the probes. Python stack dumps include code filenames,
function names and line numbers, not locals or request payloads. Treat them as
local diagnostic artifacts and review before sharing; never commit runtime logs.
File/stack setup failures are best effort and do not replace a business result
with a diagnostic exception for the handled I/O/unsupported-watchdog cases.
Stage and field names are allowlisted; unknown text/fields are discarded, child
tail stages must belong to the same fixed set, and reason values are fixed codes.
No raw cleanup exception is included in diagnostic records.

The parent cleanup guard now starts before context/Queue/Event/Process/RSS/start
preparation. Returned resources are cleaned on each failure stage. Process.close
releases a finished/not-started process handle. Queue close/join and both parent
pipe ends are attempted independently; failures produce fixed incomplete codes.
Before-start Process argument references are cleared and caller Event references
are released (multiprocessing.Event has no public close). Tests retain a start
failure traceback and still verify actual pipes closed and Event weakref dead.
Internal allocation failures inside a constructor remain the constructor/stdlib's
responsibility; this is not a proof against arbitrary native handle failures.
Child business cleanup order stays database close -> queue close -> feeder join.
Child queue-close/join exceptions emit distinct fixed codes and cleanup_incomplete.

The watchdog is process-global within its spawned child; there are no existing
faulthandler watchdog users in this worker path. No repeating dump or process-wide
fatal-signal handler is installed. Native C stacks are not collected. A stall in
diagnostic I/O, scheduling delay, failure before probe initialization, or a native
shutdown issue may still leave incomplete evidence. There is no stack dump after
the parent forcibly kills the child. Missing markers are UNKNOWN, not proof of
failure at that exact operation. Enabled probes add timing/I/O overhead and can
perturb a timing-sensitive failure.

## Historical candidate validation (2026-10-18, before final hardening)

Tests use isolated temporary data and fixed fixtures, without real providers or
production databases. Default native thread configuration and original assertions
are retained. The synthetic slow-child timeout test verifies the existing
10-second wait / 5-second termination join arguments, not a natural reproduction.
The historical independent-child test used an 8.5-second sleep. Final hardening
replaces that timing assumption with observation of the actual dump, a 20-second
poll deadline and a 30-second subprocess timeout; the production trigger stays 8s.
This controlled dump is not a mining-timeout reproduction.

From `backend`, commands use the existing `.venv/Scripts/python.exe` and pytest:

| Mode / pytest selection | Result | pytest seconds | wall seconds | exit |
| --- | --- | --- | --- | --- |
| OFF: `tests/backtest/test_worker_process.py::test_spawn_mining_writes_four_artifacts_and_returns_compact_summary` | 1 passed | 6.97 | 8.54 | 0 |
| OFF: `tests/backtest/test_worker_process.py` (initial regression) | 11 passed | 30.62 | 32.27 | 0 |
| ON: both `tests/backtest/test_worker_process.py tests/backtest/test_worker_exit_diagnostics.py` (final) | 19 passed | 40.13 | 41.78 | 0 |
| OFF: same two modules (final) | 19 passed | 41.36 | 43.08 | 0 |

The two-module commands include `-q --durations=12`, separate short temporary
`--basetemp` directories and temporary `-o cache_dir=...`. The target-only run
uses `--durations=5`. Test subprocess environments use a temporary `DATA_DIR`, a
nonexistent `TICKFLOW_ENV_FILE` and empty AI/TickFlow keys. No POLARS/OMP thread
override is set. The enabled run redirects TEMP/TMP to a dedicated temporary
logs directory. Probe unit tests explicitly enable/disable probes locally as
needed; OFF/ON above describes the outer Worker regression mode.

An initial sandbox launch was NOT EXECUTED by pytest: uv's trampoline reported
permission denied. Normal approved execution outside the sandbox succeeded,
without changing permissions or configuration. A first enabled-module run had
17 passes / 1 failure (40.52 seconds): the new probe consumed the existing
cancellation test's finite mocked lifecycle clock, causing `StopIteration`.
The probe now captures its own monotonic clock reference, with a regression test;
the existing cancellation test and assertions were not changed. Final dual-mode
results above supersede that candidate failure, not the unresolved original hang.

Read-only log inspection verified seven actual spawned workers each wrote all
13 child markers through `process_exit_imminent`; parent records reported natural
exit 0 and all normal stack files were empty. Separate controlled-sleep evidence
contained one actual Python stack dump. The synthetic timeout test verified last
stage reporting, null pre-termination exit code and -15 termination outcome.

Ruff on the changed Python files reports one pre-existing BLE001 in worker.py;
the HEAD baseline reports the same warning. No new Ruff findings remain.
High-confidence secret-pattern scan and candidate diff/whitespace review passed.
Full backend suite: NOT RUN for this candidate, since both modes of the affected
Worker module and all probe tests pass without a new runtime concern. The prior
4252-pass full-suite result predates this instrumentation and is historical only.

Original intermittent timeout: NOT REPRODUCED, NOT FIXED. We can obtain stage
timing and a bounded Python stack when the conditions permit, but no evidence
yet identifies the original stuck operation. Capture a future natural failure
with these probes before proposing a lifecycle fix. No commit or push performed.

## B-WORKER-DIAG-FINAL hardening (2026-10-18)

Scope remains exactly worker.py, worker_exit_diagnostics.py, the probe test module
and this document. Damon/offline harness, authentication, Provider, Preview and
all unrelated modules are unchanged. Real-model gate remains NO-GO.

- P2-1: move all parent post-wait diagnostic I/O after terminate/join. Fault test
  injects slow I/O and asserts join(10) -> terminate -> join(5) happen before any
  such diagnostic action. Captured liveness/exitcode and waited_ms retain the
  pre-termination observations; last child stage is read only afterward.
- P2-2: a single outer finally covers context, queue, event, process, RSS and start
  failures. Injected setup failures preserve their original exception, close
  available resources and record only fixed failure codes. A real multiprocessing
  Queue/Event/Process test proves pipe and pre-start reference cleanup even while
  the failure traceback is retained. Additional tests cover queue/feeder cleanup
  exceptions, unavailable probe/stack files, write/flush failures and child sampler
  initialization failure. They do not claim arbitrary OS errors can be forcibly
  recovered from Python.
- P2-3: wait for the real stack marker and frame with bounded polling, instead of
  an assumed half-second scheduling margin. Normal probe close cancels the timer,
  leaves an empty stack and prevents rearm; repeated arm/close is safe. Trigger
  remains 8 seconds, repeat=False, exit=False; parent wait remains 10 seconds.

Final tests use `uv run --frozen --no-sync --offline python -B -c $runner`.
The in-memory runner clears inherited business configuration before app imports,
uses unique temporary DATA_DIR/HOME/TEMP, a nonexistent TICKFLOW_ENV_FILE and empty
AI/TickFlow keys. A Python audit gate self-check rejects external DNS/connect and
protects production .env/secrets/data. This is not an OS/native-code sandbox and
does not automatically propagate its audit hook to spawned children; those inherit
the empty/temporary environment. No real service request or credential is used.
No thread cap, test exclusion, assertion change or patching pytest plugin is used.

Intermediate executions in this task: probe module 17 passed (8.86s), expanded
probe module 24 passed (8.78s), Worker/Mining four-module OFF 70 passed (36.22s).
The last OFF run preceded the final one-shot watchdog flag; final dual-mode and
full-suite results below supersede it for the finished source. Initial Ruff found
new local style issues, corrected only in these files; the original worker.py
BLE001 is retained and confirmed against HEAD.

Final cleanup preserves error semantics: if a successful business path encounters
a queue cleanup error, that error still propagates after remaining cleanup. If a
setup/task/termination exception is already active, it is preserved rather than
masked by queue cleanup. Both enabled and disabled modes have explicit assertions.

Final-source targeted results so far (pytest times; runner returns exit 0):

| Mode / pytest selection | Result | Seconds |
| --- | --- | --- |
| OFF: `tests/backtest/test_worker_exit_diagnostics.py` | 26 passed | 8.84 |
| OFF: `tests/backtest/test_worker_process.py tests/backtest/test_mining_runtime.py tests/backtest/test_mining.py` | 46 passed, 5 warnings | 26.63 |
| ON: `tests/backtest/test_worker_process.py tests/backtest/test_worker_exit_diagnostics.py` | 37 passed, 5 warnings | 35.17 |
| OFF: complete `tests` | 4296 passed, 0 failed, 6 skipped, 1 xfailed, 214 warnings | 318.43 |

Earlier finalization checks also passed OFF 70 (35.34s) and ON 35 (34.76s), before
the last queue-cleanup error-preservation change and its two new assertions. They
are intermediate evidence, not a replacement for final-source results.

The final ON runner also pins tempfile.tempdir to its own temporary root (in
addition to TEMP/TMP), so parent probes cannot reuse an earlier stdlib temp-dir
cache. Inspection of that run found seven actual child logs ending at
process_exit_imminent, each with parent exitcode 0, no exit timeout and zero-byte
stack file. Two additional parent-only logs include controlled fake-process
termination outcomes; missing child records stay UNKNOWN and are not evidence
of a natural mining hang. The suite includes the original synthetic cancellation
and slow-exit tests with their -15 termination assertions unchanged. The separate
bounded stack test observes one real dump in its own isolated subprocess.

The complete run collected 4303 items; runner wall time 319.84s, exit 0. Its audit
denial count stayed at two (the initial external DNS/connect self-checks), with
no additional parent-process external network event. This is current execution
evidence, not a reuse of the previous 4278-pass suite. No historical timeout was
reproduced; synthetic -15 outcomes and the controlled stack test are separate.

For each row, the actual shell command was the uv/python runner above; internally
it invokes `pytest.main([<listed paths>, '-q', '--tb=short', '-o',
'cache_dir=<unique temporary root>/pytest-cache',
'--basetemp=<unique temporary root>/pytest-tmp'])`. ON adds only the explicit
diagnostic flag before pytest import; the complete suite uses OFF, with individual
probe tests controlling their own fixture flags. No application lifespan or real
business service is run as a deployed server.

Final review: P2-1/P2-2/P2-3 PASS within the documented Python/stdlib scope. Only
the four allowed WORKER-DIAG candidates changed; original Worker process tests
and exit assertions are untouched. Three tested Python file hashes are checked
before staging so a different source version cannot inherit these test results.
Ruff for the new probe/test files passes; all three files retain only the HEAD
worker.py BLE001. Diff/whitespace and four-file high-confidence key/private-key
pattern checks pass (not full DLP). No raw real credentials or production data
were read; no real model, voice, quote or production database call was made.

Remaining risks: best-effort synchronous diagnostic I/O can still delay the
parent after the child has exited; enabled child I/O changes timing; arbitrary
native hangs/OS resource failures are not solved. Queue pipe/pre-start argument
cleanup uses installed multiprocessing internals and needs review on Python
upgrades. Runtime diagnostic logs are retained locally, have no cross-run quota,
and must be reviewed before sharing. Python stack evidence cannot identify every
native hang. Frontend/browser/real-service validation: NOT RUN and out of scope.

Conclusion: exit diagnostics complete and pass current regression; the historical
intermittent exit timeout was not reproduced in this run. ROOT CAUSE UNKNOWN.
Real-model smoke remains NO-GO. This does not authorize REAL-MODEL-GATE work.

ROOT CAUSE UNKNOWN. Diagnostics identify observed Python stages and sometimes
Python frames; neither a successful run nor a synthetic timeout/dump establishes
the cause of the historical intermittent Worker exit timeout.
