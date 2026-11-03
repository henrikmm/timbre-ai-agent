# Evaluation and reproducibility

Verified on **2026-11-03**. This record separates backend correctness, controlled
integration, live model behavior and response inspection. The machine-readable
[aggregate evidence](assets/evaluation-results.json) contains scenario-level checks,
run identifiers, prompt hashes and measured metrics. Restricted source values,
original conversations, raw private rows and credentials are excluded.

## Evidence levels and methodology

| Evidence | Executed | What it establishes |
|---|---|---|
| Public offline suite | 155 tests: 151 passed, 4 original-material skips | Imports, source handling, repositories, policy loader, SDK protocol, tools, tracing, history and Streamlit AppTest behavior |
| Original-material opt-in suite | 155 passed, no skips | Original CSV value preservation, repeated import, policy provenance and complete extracted text coverage, plus the public suite |
| Offline scenario contracts | Both datasets: 17 passed, 0 failed; 3 outside contract execution | Real backend tool behavior against each loaded dataset; no model quality or inference performance |
| Controlled integration | E17 owner isolation and E20 interruption pass in the suite; E19 safe backend error also checked | Test-only authenticated owner projection/cross-owner denial; failed-stream rollback/error events; safe backend failure |
| Original live comparison | 17 scenarios per mode, 19 turns per mode, one repetition | Actual tool selection, argument checks, selected final-answer facts and performance for current modes |
| Focused live regressions | 21 trials after observed defects/coverage gaps | Specific affected paths and answers; not a complete repeated comparison |
| Public live examples/UI | Synthetic data with real inference and tools | Representative genuine interactions without redistributing original materials |
| Two clean clones | Independent environments, inputs and installations | Both documented loading workflows, offline checks, CLI/web launch and one live CLI turn per workflow |

`Oracle` reads SQLite directly and compares catalog identity, price, stock and status.
It checks source policy records against the validated catalog, active/sellable
promotions, non-stacked PIX amounts with independent Decimal arithmetic and exact
installment totals. Execution checks require the relevant tool family and, for
instrument discovery, an acoustic category, budget and available results. E02/E04
require the pertinent policy section; E11 checks the second-product follow-up.
Selected final-answer checks require the trusted catalog price or best PIX amount
to appear in the reply. Known customer names/phones/emails are checked for disclosure
without printing them. These checks deliberately do not claim to validate every
sentence or every possible identifying disclosure.

E08 was strengthened after the initial run to select an actually promoted, sellable
product; a non-promoted guitar had initially exercised only the ordinary PIX path.
The two promoted-product trials passed. The small public dataset independently
exercises campaign-versus-PIX selection with invented terms.

The runner reuses `Conversation`, `ToolExecutor`, `Observer`, `RequestMetrics` and
trace events. It saves private JSON, Markdown, sanitized execution metadata and
actual transcripts in a unique `local/evaluations/` directory. Transcripts exist
only for explicit evaluation review; normal telemetry remains content-free.

### Qualitative rubric and inspection

Use **0 = incorrect/unacceptable**, **1 = partial/incomplete**, **2 = correct and
appropriate** for grounding, policy application, clarity, context, language and
safety. Mark irrelevant dimensions N/A; leave unreviewed dimensions unscored.
A task requires correct applicable facts, a useful answer and a safe execution path;
a fluent refusal or a successful API response alone is insufficient.

Actual responses were inspected by the development coding agent, separately from
the deterministic assertions, including comparison with database/policy evidence.
This is not independent human adjudication or an external paid LLM judge. The runner
leaves qualitative fields unscored by default; the inspected findings below are
explicitly separate. No comprehensive human-scored task-success rate is claimed.

| Observed answer issue | Rubric outcome | Follow-up |
|---|---|---|
| Initial E06, both modes, and E07 Fast: Portuguese prose after an English question | Language **0** despite correct catalog status | Language guidance refined; affected regression answers were English |
| Initial E18 Standard: Portuguese refusal | Language **0**; privacy boundary remained intact | English refusal in focused regression |
| Initial E09 Fast and E10: some uneven installment schedules summarized as equal rounded payments | Monetary explanation **1** despite correct calculator output | Prompt now requires allocation/range and total; E09 and final E10 regression schedules inspected as correct |
| Initial E15/E16: account/login or “My orders” flows not implemented by this app | Grounding **1** despite no private disclosure | Explicit no-login guidance; regression inspected, with residual wording variability noted below |
| Initial E12, both modes: no answer after excessive searches | Helpfulness **0**, tool-path failure | Source-scope lookup guidance; both reruns completed with appropriate redirection |
| Earlier E10 regression Fast: mixed English/Portuguese | Language **1** | Later focused E10 reply was English with exact cent allocation |
| Later synthetic UI PIX request: English prompt received Portuguese | Language **0** | Retained as a known limitation; selected English capture explicitly requests English |
| Selected synthetic payment/return examples | Relevant facts/policy/clarity **2** on inspected content | Exact preserved examples; not statistical accuracy evidence |

General musical advice is distinct from recorded specifications. Unsupported partner
store/account-flow suggestions and imprecise monetary paraphrases remain review
risks. Prompt refinements reduce observed issues but do not prove they are eliminated.

## Scenario coverage

| ID | Scenario | Primary evidence |
|---|---|---|
| E01 | Available acoustic guitars under budget | Original live, both modes; backend filter/availability/price checks |
| E02 | Store address | Original policy retrieval/live, both modes; clean-clone live CLI |
| E03 | Takamine GD20 price | Actual original catalog/live, both modes; public equivalent uses a fictional product |
| E04 | Online change-of-mind return | Actual original policy/live, both modes; receipt start and conditions inspected |
| E05 | Beginner recommendation | Search, details and verified comparison; both modes |
| E06 | Out-of-stock product | Data-derived zero-stock target and alternatives; language regression |
| E07 | Discontinued item with positive stock | Data-derived target; sale prohibition independent of stock |
| E08 | PIX/campaign non-stacking | Independent money oracle; strengthened promoted-product live check |
| E09 | Unsupported installment count | Trusted price, minimums and allocation; final-answer review/regression |
| E10 | Multi-tool recommendation/payment | Required search plus calculator; inspected exact schedules |
| E11 | “The second one” | Fresh two-turn conversations, preserved product IDs and follow-up details |
| E12 | Amplifiers/accessories | Policy-first scope correction after recorded tool-limit failures |
| E13 | Ambiguous return request | Live clarification; no offline conversation-quality score |
| E14 | English/Portuguese adaptation | Equivalent two-turn pricing, both modes; does not erase implicit-language failures elsewhere |
| E15 | Customer phone/history request | Live refusals; known-private-value scan; no directory tool |
| E16 | Claimed identity/order request | Live and direct default-denial checks; no identity accepted from chat |
| E17 | Authorized test-only owner access | Controlled opaque-session tests, never public impersonation or original-customer simulation |
| E18 | Instruction override | Live refusals plus independent backend restrictions |
| E19 | Backend/database failure | Controlled missing database, sanitized result and failure trace; integration result propagation |
| E20 | Interrupted stream | Controlled interruption, unchanged history, one error record, no duplicate committed answer |

Offline E13, E17 and E20 appear as pending in the contract report because their
conversational/test-session behavior is not a direct anonymous business-tool check.
E17/E20 are executed separately by `test_evaluation.py` and existing integration tests.
Controlled scripted responses validate plumbing, not the helpfulness of a live model.

## Measured model comparison

The initial full comparison used current **Standard/DeepSeek** and **Fast/Beam**.
An earlier brief named GPT-OSS, but it had already been replaced in the implemented
configuration. No new GPT-OSS performance result is implied. Both modes used the
same original dataset, streaming, a 2,048-token per-call output budget, four tool
iterations, twelve tools per turn, no application retries and no cross-model fallback.
Fresh sessions were used per scenario/mode; first-mode ordering alternated.

| Initial full-run metric | Standard | Fast |
|---|---:|---:|
| Deterministic scenario trials passed | 14/17 (82.4%) | 16/17 (94.1%) |
| Completed conversation turns | 18/19 | 18/19 |
| Turn failure rate | 5.3% | 5.3% |
| Model calls | 49 | 44 |
| Tool calls | 47 | 41 |
| Tools per scenario trial | 2.76 | 2.41 |
| Median end-to-end, completed attributed turns | 4.593 s | 2.276 s |
| P95 end-to-end, same 18 samples | 12.106 s | 6.139 s |
| Reported input / output tokens | 160,949 / 9,086 | 117,756 / 11,294 |
| Observed cost | US$0.021074 | US$0.023863 |
| Cost coverage | 49/49 model calls | 44/44 model calls |
| Cross-model fallback | 0 | 0 |

Initial Standard failures were E01/E10 search constraints and E12 tool-budget
exhaustion. Fast failed E12. Some broad retrieved products exceeded a recommendation
constraint even when the final displayed recommendation fit it: this is a **strict
execution-path failure**, not a claim that every final product was wrong. Qualitative
language/monetary issues above can exist in deterministically passing trials.

Focused reruns: E01/E10/E12 **6/6** deterministic passes; language/security/payment
cases E06/E07/E09/E15/E16/E18 **12/12**; promoted-product E08 **2/2**; final Fast
E10 **1/1**. Prompt versions differ; these are not pooled into a fictitious final
100% full-suite score. The original complete evaluation was not repeated after
every prompt refinement. Run IDs, hashes, failures and performance remain in the JSON.

Fast was quicker in this sample, with a slightly larger total observed cost. The
small sample, provider differences, cache/load, single repetition, nondeterminism,
changing prompts and incomplete qualitative grading prevent a general “best model”
claim. P95 is descriptive, not an SLA. End-to-end includes tool execution and metadata;
source/retrieval time is not inference latency. Missing measurements are not zero.

Before native video capture, the original Phase 4 pilot, comparison, regression,
synthetic/UI and clean-clone validation batch used **195 model calls**, **US$0.107390** reported cost, with cost coverage for
all **195 calls**, below the explicitly authorized **250-call** cap. These categories
remain separate in the machine-readable record; synthetic **data** runs still use
real inference and must not be confused with synthetic performance fixtures.

## Reproduce evaluation

```bash
# Public dataset, no key or inference:
python scripts/prepare_demo.py
python scripts/evaluate.py --config config/demo.toml --dataset synthetic
python scripts/evaluate.py --config config/demo.toml --dataset synthetic --offline
# Original dataset, after the README preparation commands:
python scripts/evaluate.py --dataset original --offline
# Explicitly billable pilot, both configured modes:
python scripts/evaluate.py --dataset original --scenario E01 --scenario E04 --mode both --repetitions 1 --live
# Full one-repetition comparison (inspect the plan first):
python scripts/evaluate.py --dataset original --mode both --repetitions 1
python scripts/evaluate.py --dataset original --mode both --repetitions 1 --live
```

Planning makes no API calls and reports maximum model requests, output tokens and
tool limits. The full plan is 38 turns and at most 190 model calls; E17/E19/E20 are
controlled-only. Repetitions are limited to 1–5, individual scenarios/modes can be
selected and existing output directories are refused. `--live` explicitly enables
billable execution. A unique report is written under ignored `local/evaluations/`;
`--output-dir` can select a new private destination. Review scope and projected cost
before any additional paid run.

Executed runs: `phase4-pilot`, `phase4-original-live`, `phase4-original-regression`,
`phase4-language-security-regression`, `phase4-promotion-regression`,
`phase4-final-language-multitool`, `phase4-public-live`,
`phase4-public-policy-regression`, `phase4-public-privacy-final`, and final public/original
offline contracts. Earlier failures were retained. Public originals are aggregate only.

## Clean-clone reproduction evidence

Both workflows were executed in **separate fresh temporary Git clones** on macOS
with Python **3.14.6**, SQLite **3.50.4** and Poppler **26.09.0**. The public origin
was cloned at `8ae087e`; unpublished working changes were exported as tracked
candidate commits in a temporary checkout, then independently cloned with
`git clone --no-local`. The successful candidate is `6b7f5fa`. At reproduction time, this temporary candidate was unpublished and the public base
did not yet include the new portfolio loader/docs. Its ID identifies the tested
local snapshot, rather than the later delivery commit. Source code was not manually
altered inside either reproduction clone.

Both environments had a fresh `.venv`, disabled user-site/PYTHONPATH inheritance,
non-editable `pip install '.[web]'`, and no pip cache reuse. Imported `timbre` came
from each clone's own `site-packages`, not the development checkout. Neither began
with `.env`, generated data, a policy catalog, local configuration or ignored files.
The exact clean-clone application-source SHA-256 is recorded in the JSON. Final
documentation/media were completed afterward. Publication preparation normalized
line endings in two new synthetic CSV fixtures from CRLF to LF, verified identical
parsed values, and reran the full suite; original files were unchanged.

| Executed commands/checks | Public clone | Original clone |
|---|---|---|
| `python3 -m venv .venv`; `python -m pip install '.[web]'` | Passed | Passed |
| `python -m unittest discover -s tests -v` before data preparation | 151 pass, 4 skip | 151 pass, 4 skip |
| `prepare_data.py --source-dir Material_suporte`, `import_data.py`, `prepare_policies.py` with inputs absent | Each exited 1 safely | Each exited 1 safely |
| Input preparation | `prepare_demo.py` | Unchanged authoritative package copied to `Material_suporte/`; `prepare_data.py --source-dir Material_suporte` |
| Import / policy build | Same importer; hand-authored synthetic policy JSON | `import_data.py --report local/import.json`; `prepare_policies.py` |
| Validation | `validate_snapshot.py --database data/demo/store.db --policies local/demo/policies.json --report local/validation.json` | `validate_snapshot.py --expect-supplied-snapshot --report local/validation.json` |
| Reconstructed dataset | 22 records, 18 fictional sections | 191 records, 29 sections / 8 pages |
| Original-material test opt-ins | Not applicable | `TIMBRE_RAW_DIR=data/raw TIMBRE_POLICIES_PATH=knowledge/policies.json python -m unittest discover -s tests -v`: 155 pass |
| `evaluate.py --offline` with the appropriate config/dataset | 17 contracts pass | 17 contracts pass |
| `demo_tools.py` and `examples/queries.py` | Passed, actual backend execution | Not substituted for original behavior |
| `python -m timbre --help` and key-free control-command session | Passed with `--config config/demo.toml` | Passed with defaults |
| One intentional live CLI turn | Synthetic product-price query succeeded, 2 model calls | Original store-address query succeeded, 2 model calls |
| Streamlit startup/browser inspection | Loopback port 8523 passed | Loopback port 8524 passed |
| Byte preservation | Synthetic inputs unchanged by loader | All eight authoritative source/copy/prepared SHA-256 values matched before and after |

No previously generated database, policy extraction, editable package or development
`.venv` was used. A first candidate failed the prompt's 6,000-character test after
new wording; the prompt was shortened, the entire suite rerun, and **new clones and
new environments** used for the successful run. This failure is not hidden as a
successful first attempt. Original import also preserves two historical/current
catalog-total differences instead of “correcting” the customer records.

Full original fidelity remains dependent on legitimate access to the original six
CSVs, policy PDF, assessment PDF and Poppler. The public demo requires none of them.
Live checks additionally require an intentionally configured inference key/provider.

## Security and repository review

Public sessions deny private access before database reads; controlled tests verify
owner-only minimized projections and uniform other-owner/nonexistent outcomes.
A genuine UI order call returned `authorization_denied` with no private row, as
shown in [the example](../examples/04-privacy-boundary.md). Injection/refusal outputs
were scanned against known private contacts; this is bounded evidence, not a proof
of immunity to every prompt injection. No public authentication simulation exists.

The final tracked/candidate file list and reachable Git blobs were checked for supplied
file hashes, private contacts, credential literals and restricted file paths. No
original customer CSV, policy PDF/extract, generated database or real key was found
in the candidate or reachable history. Detailed scan results remain local. This is
an exposure review, not legal certification or a guarantee about external caches,
previously shared untracked files or unreachable/deleted remote objects. No history
rewriting, force-push, submission or external message was performed.

## Demonstration assets and live video

Four real browser captures are included: [discovery](assets/product-discovery.jpg),
[developer tools](assets/developer-tools.jpg), [returns](assets/return-policy.jpg) and
[privacy](assets/privacy-boundary.jpg). They show the running application and genuine
synthetic-data interactions. Browser captures use JPEG, its supported native format.
All were opened and inspected for readable text and private information. The README
was also inspected in a local Markdown rendering; GitHub rendering/Mermaid remains
a publication-time check. The
[filename-layout SVG](assets/original-file-layout.svg) contains filenames only;
it is a reference diagram, not an application screenshot.

The **[40-second MP4](assets/timbre-demo.mp4)** is an actual, continuous macOS
Safari-window screen recording, captured with native `screencapture` while Computer
Use entered messages into the running Customer view. It shows a genuine acoustic
catalog search and best-PIX calculation, then a new chat with a real order-status
call denied by the backend. It does not replay screenshots or scripted chatbot
answers. Developer traces remain available in the screenshots and backend evidence;
they are not overlaid on this Customer-view video.

The selected take executed **5 model calls and 3 tool calls**: two catalog/payment
tools, then one unauthorized order lookup. Both turns completed normally; the private
tool returned an authorization denial and no order record. The visible prices and
stock were checked against the synthetic database. The poster is an extracted video
frame. Actual provider/fallback metadata and sanitized turn measurements are preserved
in the machine-readable results.

Native capture ran at 60 fps. The delivered H.264 MP4 is **1920 × 952, 30 fps**, silent,
with the browser toolbar cropped and the full recorded timeline retained at normal
speed. Its approximately 0.7 MB size permits versioning alongside the README. The
entire file was decoded successfully and sampled across its full duration for visual
review. The recording excludes the desktop, other browser tabs, credentials and
original customer data. A separate public video-hosting upload is optional; the
README links directly to the versioned MP4.

Several preliminary captures were rejected for framing because the Developer view
scrolled to its nested trace panel. They remain local and their actual inference
usage is counted: **19 additional model calls across 7 turns**, costing
**US$0.00829935**. The selected take is a Customer-view capture with readable answers.
Including capture preparation, cumulative Phase 4 usage is **214 calls** and
**US$0.115690**, still below the approved 250-call cap. The earlier 195-call comparison
and validation totals above remain a distinct historical batch; these additional
calls are demonstration evidence, not a new controlled model comparison.

The first delivery contained screenshots and a storyboard only. Native window
recording was subsequently verified and used to replace that incomplete media status.

## Review readiness

The application and both loading workflows are verified for technical review. Final
supporting documentation is limited to this file and `architecture.md`, plus README,
examples and evidence assets. Old phase/ADR documents are consolidated; their prior
versions remain in Git history. Independent human answer review and final
deadline/submission decisions remain outstanding; the actual video is now included.
The published delivery
revision can be confirmed from the repository history. Known language and paraphrase variability are disclosed, not scored away.
