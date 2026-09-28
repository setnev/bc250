# GPU performance tuning

The retained profile raises this board from **1,500 to 1,700 MHz at the existing 925 mV**. It has a 75°C GPU edge-temperature cutoff and releases the overrides when its service stops. This is a fixed clock profile with monitoring, not an adaptive load governor.

## Hardware and method

- Eight CPU cores / sixteen threads, 40 enabled GPU CUs, P3.00-derived MeiMeiDXE firmware.
- Existing 512 MiB UMA reservation and expanded Linux GPU-memory limits from the [Q36 evaluation](q36.md).
- Owner-reported 400 W Apevia ITX PSU; exact model and rail ratings not recorded. 120 mm fans blow through the stock heatsink and rear spreader.
- SMU queries measured the baseline at 1,500 MHz / VID 100 (925 mV). The usual driver clock/voltage readouts are invalid on this firmware and were not used for tuning.
- Q36 engine, model and compiler are pinned as in the original evaluation. Six CPU helper threads, Q8 K / Q4 V cache, 128 generated tokens, default 1,024-token prefill chunks, long-context story prompt.
- Each context runs in a **fresh process**, with context allocation equal to prompt length + 129. Two runs per context per clock; these are small repeated samples, not confidence intervals or a long-duration burn-in.
- Test order: stock, 1,600, 1,600, stock, then two 1,700 passes. Model processes run sequentially with the default API stopped, memory bounded to 14 GiB, swap disabled for the test unit, runtime limits and automatic API restoration.

The original Q36 report used a progressive context sweep. Its later rows measured incremental prefill, so those prefill numbers should not be treated as the baseline for this clock comparison. Fresh processes match the upstream benchmark method more closely, although the upstream context-allocation details are not fully specified.

## Q36 results

Mean tokens/s from two runs per cell:

| Context | Stock prefill | 1,700 MHz prefill | Gain | Stock generation | 1,700 MHz generation | Gain |
|---|---:|---:|---:|---:|---:|---:|
| 2K | 534.07 | 597.12 | 11.8% | 72.61 | 77.17 | 6.3% |
| 4K | 476.25 | 529.62 | 11.2% | 69.81 | 74.36 | 6.5% |
| 8K | 379.09 | 427.87 | 12.9% | 63.77 | 68.30 | 7.1% |

The intermediate 1,600 MHz setting improved prefill by approximately 5% and generation by approximately 3%. Trying 2, 4, 6 and 8 CPU helper threads at stock clocks changed mean generation by less than 0.3%; six threads were retained.

## Default Qwen3.5-9B API model

The same Q4_K_M model and llama.cpp settings were measured at both clocks: prompt 512, generation 128, batch/ubatch 128, six threads, full GPU offload, flash attention enabled, three repetitions.

| Test | Stock tokens/s | 1,700 MHz tokens/s | Gain |
|---|---:|---:|---:|
| Prefill 512 | 316.74 | 356.15 | 12.4% |
| Generate 128 | 52.31 | 54.72 | 4.6% |

To reproduce an individual Q36 row, stop other model workers and run from the pinned Q36 source directory at the selected clock. Repeat with distinct output filenames:

```sh
./q36-bench --vulkan -m /path/to/verified-model.gguf \
  --prompt-file tests/long_context_story_prompt.txt \
  --ctx-start 2048 --ctx-max 2048 --ctx-alloc 2177 \
  --gen-tokens 128 --cache-type-k q8_0 --cache-type-v q4_0 \
  --threads 6 --csv fresh-2k.csv
```

For 4K and 8K, use matching start/max values of 4096 or 8192 and allocations of 4225 or 8321. The raw CSVs and JSON include all measured repetitions.

## Qualification and limits

The integer/floating-point compute verifier passed twice at each candidate clock, with **100,663,296 outputs checked and zero mismatches per invocation**. The highest sampled GPU edge temperature across the recorded clock/compute/Qwen runs was **67°C**. This is not a measurement of VRM or memory temperatures, or wall power.

Initial control checks rolled back before tuned benchmarks: clock readback needed a settling delay, and automatic firmware voltage selection raised VID voltage slightly at 1,600 MHz. The final controller waits for settling and explicitly holds baseline VID 100. No voltage increase is retained.

Both retained API models returned the expected arithmetic answer after enabling the profile, and unauthenticated requests remained rejected with HTTP 401. No GPU reset, timeout or fault lines appeared in the tuning-period kernel log; framebuffer workqueue warnings were recorded.

The 1,700 MHz setting is qualified only for this board and the recorded workloads. Higher clocks, a different voltage curve, memory-controller profiles and CPU overclocking remain untested. The default API remains Qwen3.5 plus HauhauCS Aggressive; Q36 remains a separate tested engine/model.

## Persistent profile and rollback

`bc250-gpu-tuning.service` starts the profile at boot, after the CU unlock service. It checks GPU temperature every second and firmware clock/voltage every 30 seconds. Overheating, missing telemetry or a readback mismatch exits the guard and releases the overrides; it does not automatically reapply them. Its systemd stop hook also releases overrides if the process is terminated.

A hot-start check prevents applying the profile if the GPU is already at the cutoff. Simulated hot-start, runtime overheating, sensor failure and clock mismatch all exercised restoration. A live service stop/start check verified stock-clock restoration and reapplication. These software checks cannot recover a completely hung machine or replace firmware thermal protection.

To return to firmware-controlled clocks permanently:

```sh
sudo systemctl disable --now bc250-gpu-tuning.service
```

The BIOS, CPU configuration and memory split are unchanged by this tuning profile. Power consumption was not measured; holding the higher clock at idle may increase idle consumption.

## Sources and artifacts

- [Raw measurements and metadata](../benchmarks/performance-tuning/)
- [Clock controller](../scripts/bc250-gpu-clock.py), [thermal guard](../scripts/bc250-gpu-guard.py), [service](../config/bc250-gpu-tuning.service)
- SMU protocol adapted from [bc250-collective governor, pinned revision](https://github.com/bc250-collective/cyan-skillfish-governor/tree/e9201068ff620743ca514264e6ca357eb40aed3e), under its [MIT license](../scripts/SMU-LICENSE). That implementation targets Robin 3.00, not Robin 5.00. Do not assume this board-specific profile is appropriate for another BIOS or BC250.
- [Original Q36 benchmark source](https://github.com/Ninnix/q36/tree/1305843c735380f912619548b121cba8601f2f85)
