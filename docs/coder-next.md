# Qwen3-Coder-Next on one BC250

Test date: September 28, 2026. This is an experiment with the full 80B-parameter model in an aggressively compressed format, using disk-backed CPU expert weights. It is not a GPU-resident deployment or a coding-quality evaluation.

## Why this needs a different configuration

[Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF) activates about 3B parameters per token, but contains about 80B parameters in total. The inactive experts still have to be stored somewhere. The smallest file in the inspected [Unsloth GGUF repository](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF) was `Qwen3-Coder-Next-UD-IQ1_S.gguf`: **21,508,749,344 bytes (21.51 GB / 20.03 GiB)**. That exceeds the BC250's entire 16 GiB shared memory pool before context, working buffers and Linux.

The quantizer recommends larger quants for best results. Successful inference with IQ1_S does not establish that its coding or tool-use quality matches published results for the original model.

The download was pinned to revision `ce09c67b53bc8739eef83fe67b2f5d293c270632` and verified against its published SHA-256. [Manifest](../benchmarks/coder-next/manifest.json).

## Repeated benchmark

| Model and configuration | Prompt processing, 128 tokens | Generation, 32 tokens |
|---|---:|---:|
| Coder-Next UD-IQ1_S, CPU experts + Vulkan | **3.98 tok/s** | **1.85 tok/s** |
| Qwen3.5-9B Q4_K_M, GPU offload | **317.96 tok/s** | **51.76 tok/s** |

These are means of three repetitions. Both models used six inference threads, batch/microbatch 128, flash attention and normal llama-bench warmup. Prompt processing and generation are separate tests; the generation test is not a response conditioned on the 128-token prompt.

The model, quantization and expert placement differ intentionally: this compares configurations that completed on this board, not equivalent model quality or pure architecture efficiency. The existing 512-prompt/128-generation chart elsewhere in this repository uses a different workload.

Coder-Next's individual repetitions:

| Repetition | Prompt tok/s | Generation tok/s |
|---|---:|---:|
| 1 | 3.82892 | 1.73662 |
| 2 | 3.96799 | 1.85223 |
| 3 | 4.13529 | 1.96169 |

Generation improved approximately 13% from the first to the third repetition. This trend alone does not establish its cause or predict continued improvement.

[Coder-Next raw results](../benchmarks/coder-next/coder-next-pp128-tg32.json) · [Qwen3.5 raw results](../benchmarks/coder-next/qwen35-pp128-tg32.json) · [Metadata](../benchmarks/coder-next/metadata.json)

## Consecutive prompts in one persistent server

A separate llama-server process stayed loaded for six sequential Chat Completions requests. It used the same Coder-Next file and expert placement, 2048 context, one slot, six CPU threads, batch/microbatch 128 and the same 6 GiB host cap with swap disabled. Prompt caching was enabled. Server warmup was disabled; readiness took about 42 seconds, excluded from the request latencies below. OS caches were not flushed, so the first request is **not** a controlled cold-disk measurement.

Each response was forced to 32 output tokens using `ignore_eos=true`, with temperature zero and seed 42. All six finished at the length limit. This keeps output counts comparable but intentionally truncates code; these responses do not evaluate coding correctness or task completion.

| Request | Cached prompt tokens | New prompt tokens | Prompt time | Generation tok/s | Total request time | Process disk reads |
|---|---:|---:|---:|---:|---:|---:|
| Identical prompt 1 | 0 | 43 | 27.59 s | **1.86** | 44.24 s | 14.54 GB |
| Identical prompt 2 | 39 | 4 | 2.44 s | **2.14** | 16.95 s | 3.05 GB |
| Identical prompt 3 | 39 | 4 | 2.01 s | **3.02** | 12.29 s | 0.23 GB |
| Conversation turn 1 | 17 | 20 | 9.81 s | **2.05** | 25.73 s | 5.53 GB |
| Conversation turn 2 | 68 | 19 | 13.34 s | **1.75** | 31.01 s | 8.83 GB |
| Conversation turn 3 | 118 | 20 | 13.17 s | **1.61** | 32.48 s | 10.54 GB |

The identical request asked for a palindrome-checking function. All three generated the same 32-token text. Between the first and third requests, reported generation throughput rose **62%** and total latency fell **72%**. Two different effects are visible: prompt-cache reuse reduced prompt work, while process disk reads fell substantially. That is consistent with beneficial weight/page-cache locality, although expert residency was not directly traced.

The conversation then asked for word-frequency code, a continuation, and a usage example, retaining the previous messages. Its first turn reused 17 system-prefix tokens from the earlier group. Across the three turns, generation slowed **2.05 → 1.75 → 1.61 tok/s**, even as cached prompt tokens increased. Prompt-cache reuse therefore did not guarantee faster decoding when the requested output changed.

Disk reads are deltas of the server process's Linux `/proc/PID/io` `read_bytes` counter over each whole request, in decimal GB. They include prompt and generation work; they are not model size, filesystem logical reads, or isolated expert-transfer measurements. Generation rates are the server's own `predicted_per_second` values; they are not output tokens divided by whole-request wall time.

These are short, ordered observations from one session, not a steady-state throughput guarantee. The 3.02 tok/s result applies to the third identical request, not arbitrary later conversation turns.

[Raw per-request results and generated snippets](../benchmarks/coder-next/consecutive-results.json) · [Reproduction client](../scripts/consecutive-prompts.py)

## Practical outcome

The full model can execute on this BC250 with disk-backed CPU experts, but the tested configuration is much slower than the existing Qwen3.5-9B service. Repeated identical work benefits from caching; changing tasks continues to trigger substantial disk reads. No quality advantage was established by these timing tests.

The production API was restored and verified with a real Qwen3.5 completion after testing. Coder-Next remains a staged experiment and was not added to the production model router. Its temporary benchmark services were removed after collecting evidence.

## Configuration and limits

- Existing eight-core / sixteen-thread CPU configuration, 40 routed GPU CUs and 8/8 memory allocation.
- Existing llama.cpp commit `4da6337767f973e2b4d0797e5b323d77d8565e4a`; Vulkan/RADV.
- `-ngl 99 -ncmoe 48`: request GPU layers but keep experts from all 48 layers on the CPU. This does **not** mean the whole model runs on the GPU.
- Memory-mapped model, lazy loading enabled, CPU weight repacking disabled. Expert pages can be reread from the SSD as the host page cache is reclaimed.
- Host cgroup limit 6 GiB, no cgroup swap, no soft memory limit for the repeated test. Linux had about 7.5 GiB usable host RAM. This cap reserves host headroom but also constrains caching, so these are results for this limit, not the maximum attainable throughput.
- Production inference was stopped during testing. Both benchmarks exited successfully. The recorded benchmark telemetry showed a peak sampled GPU edge temperature of 62°C, memory-limit pressure, and no cgroup OOM kills.
- No GPU clock, voltage, memory split or firmware changes were made for this experiment.

An earlier smoke test used 32 prompt tokens, eight generation tokens, one repetition, no warmup and a 5 GiB soft memory limit. It produced approximately 1.30 tok/s in both tests. Those settings differ, so it should not be used to quantify a cold-to-warm speedup. [Smoke results](../benchmarks/coder-next/coder-next-smoke.json).

## Reproduce the repeated benchmark

Stop competing inference workloads before testing. Use your own verified model paths. The resource limits above were imposed externally with systemd; the command alone does not enforce them.

```bash
llama-bench -m /path/to/Qwen3-Coder-Next-UD-IQ1_S.gguf \
  -p 128 -n 32 -b 128 -ub 128 -t 6 \
  -ngl 99 -ncmoe 48 -lm mmap -lzm on --repack 0 \
  -fa on -r 3 -o json

llama-bench -m /path/to/Qwen3.5-9B-Q4_K_M.gguf \
  -p 128 -n 32 -b 128 -ub 128 -t 6 -ngl 99 -fa on -r 3 -o json
```

The Coder-Next process had a 480-second limit; the baseline had 90 seconds. Neither timed out. Both ran in the same 6 GiB host-memory-limited service, sequentially, Coder-Next first. OS caches were not explicitly flushed between models or repetitions.

For the consecutive-request experiment, keep one instance of this server running for all six requests, under the same external memory limits:

```bash
llama-server -m /path/to/Qwen3-Coder-Next-UD-IQ1_S.gguf \
  --alias qwen3-coder-next-test --host 127.0.0.1 --port 18082 \
  --api-key-file /path/to/private-api-key \
  -c 2048 -np 1 -b 128 -ub 128 -t 6 -ngl 99 -ncmoe 48 \
  -lm mmap -lzm on --no-repack -fa on --no-warmup

# Set BC250_API_KEY in your environment to match the server's key.
python3 scripts/consecutive-prompts.py \
  --base-url http://127.0.0.1:18082 --model qwen3-coder-next-test \
  --output consecutive-results.json
```

To collect disk-read deltas, run the client on the server machine with permission to read the server process's `/proc/PID/io`, and add `--pid PID`. Otherwise the client still captures API timings but leaves the I/O dictionary empty. In the recorded run, the persistent test service had a 900-second ceiling and each request had a 180-second timeout; all completed successfully.
