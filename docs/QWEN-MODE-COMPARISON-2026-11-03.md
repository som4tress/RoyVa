# Direct Qwen comparison: thinking versus non-thinking

Four completed workflows: weather and household location, one run of each in
each mode. Tested directly against local `qwen36-agent` on port 8000, bypassing
OpenCode, its gateway, routing, context cleanup, recovery checks and learning.
No production inference settings were modified. No cloud LLM was used.

## Configuration

Parameters follow the [official model guidance](https://huggingface.co/Qwen/Qwen3.6-35B-A3B#best-practices).

| Parameter | Non-thinking | Thinking |
| --- | --- | --- |
| enable_thinking | false | true |
| temperature | 0.7 | 1.0 |
| top_p | 0.8 | 0.95 |
| top_k | 20 | 20 |
| min_p | 0 | 0 |
| presence_penalty | 1.5 | 1.5 |
| repetition_penalty | 1.0 | 1.0 |
| max_tokens | 32768 | 32768 |

Verified on the running container: reasoning parser `qwen3`, tool parser
`qwen3_coder`, auto tool choice enabled, context 131072. The parser was already
configured; an initial suspicion that it was missing was incorrect. No restart
was performed. Thinking traces were generated and retained for tool continuation.

Both modes received identical tool definitions and minimal shared instructions:
public web search/fetch plus the existing read-only HA state/history adapters.
Each workflow started a new conversation with a fresh explicit timestamp.
Both location runs independently selected recorded zone history; neither used a
fresh current-person/GPS lookup. Both weather runs selected public web search.

## Results

Input/output tokens are totals across all passes. Output includes reasoning.
Execution time sums model requests and actual tool calls. It excludes external
web-broker scheduling waits; observed wall time is also provided explicitly.

| Workload | Mode | Execution seconds | Observed wall seconds | Input tokens | Output tokens | Passes | Prefix tokens reused |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Weather | Non-thinking | 43.271 | 66.935 | 11017 | 551 | 2 | 1056 (9.59%) |
| Weather | Thinking | 84.760 | 111.010 | 11067 | 1327 | 2 | 1056 (9.54%) |
| Location estimate | Non-thinking | 23.244 | 23.245 | 3548 | 399 | 2 | 1056 (29.76%) |
| Location estimate | Thinking | 41.633 | 41.633 | 3925 | 744 | 2 | 1056 (26.90%) |

KV-prefix caching stayed enabled. No cache salts, flushing, or server/cache
configuration changes were used. Reused prefix tokens were measured from vLLM
counter deltas; query deltas matched each workflow's input-token total. Different
timestamps do not eliminate common-prefix reuse. Actual web requests were made;
third-party search/provider caching was not controlled. Loaded model weights and
kernel caches remained warm.

Run order was weather/non-thinking, location/thinking, weather/thinking,
location/non-thinking. Location requests were timestamped 14:12:12 and 14:14:45
America/Los_Angeles; weather requests at 14:11:06 and 14:12:54 on November 3.

## Accuracy review

| Workload | Non-thinking | Thinking |
| --- | --- | --- |
| Weather | Real retrieval, but mixed short-range forecast, long-range outlook and historical-average material without clear source-specific separation. Partial accuracy. | Real retrieval and a long-range reliability caveat; still blended source types and used overly definite phrasing about distant rain. Partial accuracy. |
| Location | Estimate matched the recorder's ongoing named zone and included geofencing uncertainty; still characterized it as a direct observation of an ongoing visit. | Estimate matched the recorder's ongoing named zone, but claimed uncertainty was minimal and treated the query endpoint as a fresh tracking update. |

Neither location response proves physical whereabouts or a fresh GPS fix. An
ongoing recorder interval means no later recorded zone transition, not proof
that the person remains there. Query/as-of time is not GPS-fix time. Raw responses,
HA records, and personal whereabouts remain in private benchmark files outside
Git, rather than in this report.

## Interpretation

Non-thinking execution used about half the weather time and 56% of the location
time. Thinking generated more tokens without a decisive accuracy improvement in
these two examples. This is a small diagnostic, not statistical evidence that
one mode is always better. Different queries/timestamps yielded slightly
different evidence, so it is not a fixed-evidence controlled reasoning study.

The direct path completed all four workflows without the earlier invented API
attribution or capability refusal. This supports investigating our custom
pipeline, but does not prove its root cause or rule out model sampling variance.
Parameter changes alone have not established production accuracy. Production
defaults are unchanged; no broader tests or automatic tool learning were run.

Reproduction source is captured under
`components/llm-server/mode-comparison-20261103/`. Actual public tool responses
must be supplied through its broker and private HA authentication remains local.
