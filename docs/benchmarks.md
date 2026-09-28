# Measurements and methodology

The chart and README table describe one BC250. They are local measurements, not vendor results or a claim about all boards.

## Paired GPU comparison

Date: 2026-09-28. Eight CPU cores / 16 threads online. An 8 GiB GPU reservation leaves approximately 7.5 GiB usable Linux RAM. CPU inference threads were held at six for the 24/40-CU pair, then separately tested at eight with 40 CUs.

- Ubuntu 24.04.5, kernel 6.8.0-142-generic, Mesa RADV 25.2.8.
- llama.cpp `4da6337767f973e2b4d0797e5b323d77d8565e4a`.
- Qwen3.5-9B Q4_K_M; source and hash in [the manifest](../benchmarks/model-manifests.json).
- All layers requested on GPU, flash attention on, batch and microbatch 128.
- Prompt processing: 512 tokens. Generation: 128 tokens. Three repetitions each; normal llama-bench warmup enabled.
- API stopped during benchmarking; stock routing restored for the 24-CU run, then 40-CU routing reapplied.
- GPU edge temperature sampled once per second. Test harness stopped at 85°C or a 240-second per-command limit; neither limit was reached.

| Configuration | Prefill tok/s | Decode tok/s | Sampled peak |
|---|---:|---:|---:|
| 24 CUs, 6 threads | 204.412712 | 36.369226 | 61°C |
| 40 CUs, 6 threads | 316.972931 | 52.172359 | 63°C |
| 40 CUs, 8 threads | 317.083081 | 52.257012 | 65°C |

[Raw samples](../benchmarks/) retain per-repetition timings and standard deviations. Model file paths have been reduced to basenames for publication. No samples or measured performance fields were altered.

The three-run standard deviations describe these samples, not confidence about other boards, temperatures, prompts or longer runs. The configurations were tested in sequence, not a randomized experimental design. Sustained performance, wall power and energy per token were not measured.

## Serving measurement

The production service uses 8192 context, one inference slot and six CPU threads. A separate LAN request produced 192 output tokens in 4.55 seconds end-to-end, with the server reporting 48.75 generated tokens/sec. It is not directly interchangeable with llama-bench's 128-token generation test.

Do not divide 192 by 4.55 and label the result decode speed: end-to-end latency also includes prompt processing and request overhead. Neither measurement is time-to-first-token.

## Eight CPU cores versus six

The earlier six-core / 40-CU run measured 317.05 prompt tok/s and 52.45 decode tok/s, also with six inference threads. With eight CPU cores available, the results were essentially unchanged. The extra CPU cores add general-purpose capacity; this workload did not demonstrate an inference gain from them.

## Compute correctness

The upstream duggasco Vulkan verifier compared FP32 arithmetic chains, integer arithmetic and shared-memory results against a CPU reference. At 40 CUs, 16,777,216 elements × 3 passes × 2 output types = **100,663,296 comparisons**, with zero mismatches. The initial smaller test passed at both 24 and 40 CUs.

This test was not a per-WGP isolation campaign and is not exhaustive hardware qualification. The unlocked eight-core CPU also passed a one-minute, 16-worker stress-ng verification run; longer combined CPU/GPU testing remains future work.

## Memory split regression

A 12 GiB GPU reservation left about 3.5 GiB usable host RAM. Approximately 2 GiB was swapped, with heavy continuing swap I/O. A four-output-token reply took 43.14 seconds after the CPU stress test had ended. That request is a symptom of the observed memory problem, not a comparable decode benchmark.

The final 8/8 configuration completed the paired benchmarks and LAN test with zero swap in use at inspection. Other allocation strategies, GTT tuning, longer context and larger models were not compared here.

## Re-running

[benchmark.sh](../scripts/benchmark.sh) runs the same model benchmark without changing CU masks or stopping services. Quiesce competing workloads yourself and record the actual routing state. It supports a `THREADS` environment override for the six/eight-thread comparison.
