# Model inventory and agent experiments

The five historical candidates below used GGUF Q4_K_M files. Their [source revisions and SHA-256 values](../benchmarks/model-manifests.json) were pinned and verified before activation. Only one model is loaded at a time. The current router retains **Qwen3.5-9B and HauhauCS Aggressive only**. Huihui, both Llama variants and the separate Coder-Next trial weights were removed after evaluation; their results remain below. [Q36 / Qwen3.6 findings](q36.md) describe a separate staged candidate.

| Model | API ID | Configured context | Publisher |
|---|---|---:|---|
| Qwen3.5-9B | `qwen3.5-9b` | 8192 | [Unsloth quant](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) |
| HauhauCS Aggressive | `qwen3.5-9b-aggressive` | 8192 | [HauhauCS](https://huggingface.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive) |
| Huihui Abliterated | `qwen3.5-9b-abliterated` | 8192 | [Huihui](https://huggingface.co/huihui-ai/Huihui-Qwen3.5-9B-abliterated), [quant](https://huggingface.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF) |
| Llama 3.1 8B Abliterated | `llama3.1-8b-abliterated` | 4096 | [mlabonne](https://huggingface.co/mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF) |
| Dolphin 3.0 Llama 3.1 8B | `dolphin3-llama3.1-8b` | 4096 | [Dolphin](https://huggingface.co/dphn/Dolphin3.0-Llama3.1-8B-GGUF) |

The Qwen variants declare Apache 2.0; the Llama variants use the Llama 3.1 license. “Uncensored,” “aggressive” and “abliterated” describe the publishers' variants. These tests do not measure a universal refusal rate or establish that capabilities were preserved.

The earlier Qwen3-8B and heavily quantized Qwen3.8-27B trial models were removed; they are not part of the current inventory. No vision projector was installed. Reasoning is disabled in the serving presets.

## Real SSH tool-use test

A small controller exposes five operations through a restricted SSH identity: service status, reading lab configuration/logs, writing lab configuration, restarting that service, and requesting its loopback health endpoint. It has no general shell or port-forwarding capability.

The fixture introduces one fault at a time: invalid port, stale response message, or invalid bind address. The model must inspect evidence, repair the configuration and verify both systemd status and HTTP health. The evaluator independently checks recovery. Each case has 12 turns, temperature zero and a maximum of 384 generated tokens per turn.

| Model | Full passes | What happened |
|---|---:|---|
| Original Qwen3.5 | 3/3 | Repaired and verified all cases |
| HauhauCS Aggressive | 3/3 | Repaired and verified all cases |
| Huihui Abliterated | 2/3 | Wrong replacement port initially; eventual repair but turn budget expired before verification/report |
| Llama Abliterated | 0/3 | Native tool output did not match the server parser format |
| Dolphin | 0/3 | One actual recovery without complete verification; two cases stopped before completing repair |

The downloaded Llama GGUF templates originally omitted tool schemas. Tool-aware overrides were installed before the final results above. Dolphin then made real tool calls; Llama still produced malformed tool output. This distinguishes model/runtime integration failures from actual service repairs.

[Machine-readable case summaries](../benchmarks/agent-summary.json) include actual health, verification, call count and latency. Raw conversations are not published because this repository is a public build guide rather than an export of the private controller environment. The controller and fixture are not bundled here, so those agent results are descriptive, not a fully reproducible public benchmark.

This is one small suite, one run per case, with 8K Qwen and 4K Llama contexts. Cold loading and competing model requests affected some timings. It is not a statistical ranking. HauhauCS was the best-performing newly added candidate for this particular SSH loop; the original Qwen remains the startup default.

## Static security-review fixture

The supplied code intentionally included three issues: missing project-owner authorization, shell command injection and arbitrary Origin reflection with credentialed CORS. Model output was reviewed as text and was not executed against real applications.

- All Qwen variants made unsupported SQL-injection claims. The original model suggested an owner check under the wrong label.
- HauhauCS identified shell injection and CORS but missed the owner check and provided an example that still reflected an untrusted origin.
- Huihui supplied misleading SQL/CORS remediation.
- Llama Abliterated identified authorization, command-injection and CORS concerns, but also invented SQL injection/XSS and incorrectly claimed `check=True` would prevent command injection.
- Dolphin identified IDOR/CORS broadly but mislabeled the diagnostics flaw and offered vague fixes.

None passed a strict finding-quality review. Fewer refusals did not imply trustworthy security analysis.

Single-response generation speeds on this fixture were approximately 49 tok/s for both experimental Qwen variants and 57 tok/s for the Llama variants. Those prompts and output lengths differ, so these numbers are not a matched model-speed benchmark.

## Use in an application

Choose the API ID explicitly. Keep tool execution in the application/controller, with its own target inventory and credentials. A model's claim that it fixed something is not evidence that any command ran or that a service recovered—the Llama trials demonstrated this directly.

Dungeon and Anthos-AI are intended clients for future internal testing. The deployment made these models available through the API; it did not connect them to those applications' target servers or establish an autonomous production operator.
