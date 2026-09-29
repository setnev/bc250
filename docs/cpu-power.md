# BC250 CPU idle and request-aware power handling

Test date: 2026-09-29. This board already exposed working CPU frequency scaling and ACPI idle states on all 16 logical CPUs. The deployed handler removes its active-performance constraint after each API request and avoids gateway polling when no model is loaded. **No wall-power meter was available, so no wattage saving or solution to the board's overall idle power draw is claimed.**

## Hardware and runtime

One AMD BC250 with eight Zen 2 cores / 16 threads and 40 routed GPU CUs, 16 GB shared GDDR6, 512 MiB GPU reservation, Linux MemTotal 15,573,720 KiB. P3.00-derived MeiMeiDXE firmware; Ubuntu 24.04.5, Linux 6.8.0-142-generic, Mesa RADV 25.2.8. GPU memory parameters: `amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290`. 400 W Apevia ITX PSU, stock heatsink and rear spreader with 120 mm fans plus one additional fan; BIOS fan control, unknown RPM and ambient temperature.

CPU driver: `acpi-cpufreq`. Available frequency steps: 800, 1271, 1600, 1820, 1960, 2325, 2550, 3200 MHz. Existing limits remain 800–3200 MHz. Idle driver: `acpi_idle`. All 16 logical CPUs expose enabled C1/C2/C3. Advertised exit latencies: 1/350/400 microseconds; target residencies: 2/700/800 microseconds. These are firmware/kernel descriptors, not measurements of silicon exit time or package power. No BIOS change, CPU voltage change, core offlining, suspend, or ACPI override was applied.

## Policies compared

- Existing: `schedutil` frequency governor and `menu` idle governor.
- Alternative: `schedutil` and `teo`.
- Experimental: `schedutil` and `menu`, with C2 temporarily disabled through each CPU's sysfs control. Original settings restored after each sample. This setting was discarded.
- Deployed: retain `schedutil`/`menu` and all original idle states between requests; select `performance` and hold a 100 µs `/dev/cpu_dma_latency` request only during model loading/inference. Release immediately after completion, including drained disconnected streams. The idle frequency ceiling stays at 3200 MHz so other server tasks can scale up without an API call.

Linux's idle governor selects among states using residency and latency information. The active PM QoS request excludes the advertised 350/400 µs states while held; closing its file descriptor releases this controller's constraint. It does not promise a 100 µs end-to-end response time. [Linux CPU idle documentation](https://docs.kernel.org/admin-guide/pm/cpuidle.html).

The gateway renews a 90-second CPU lease every 20 seconds during a request. A lost release expires automatically; a controller process exit closes its QoS descriptor. Service shutdown restores saved CPU governors. Requests and renewals share a lock, preventing a late renewal from reactivating performance after release. Existing GPU profiles, 85 C thermal cutoff, request serialization, and 60-second model unload timeout remain in place. The gateway waits for activity rather than polling once per second when unloaded. A cold API call still pays model-loading cost.

## Idle measurements

Each sample measured 30 seconds of deltas in kernel per-state residency counters, summed over 16 logical CPUs and divided by elapsed time × 16. The model was unloaded and no inference ran during these windows. Sequence: menu, teo, menu, teo, then two C2-disabled samples. Settings were restored between experiments. Background operating-system work was not isolated. These are short screening measurements, not an energy benchmark.

| Policy | Mean C3 residency | Mean C2 residency | Timer overshoot p95, samples |
|---|---:|---:|---:|
| menu, original states | 29.53% | 68.75% | 160.21 / 160.32 µs |
| teo, original states | 22.62% | 75.06% | 160.64 / 158.72 µs |
| menu, C2 disabled | 27.71% | 70.52% | 161.50 / 159.68 µs |
| Deployed handler, one post-test idle window | 29.53% | 68.83% | 160.09 µs |

The timer probe performs 100 sequential 20 ms sleeps after each residency window and measures overshoot; it includes scheduler/timer behavior and is **not** a direct CPU wake-latency measurement. Frequency snapshots mostly reported 800 MHz, with occasional higher readings on sampling/background-work CPUs.

The post-deployment snapshot reported 800 MHz on all 16 policies and 98.36% combined C2/C3 residency. This is essentially unchanged from the original idle behavior, so the measurements do not establish an idle-energy improvement.

`menu` was retained. Disabling C2 did not increase reported C3 residency, and C2 accounting continued. An internal driver fallback is a possible explanation, not a traced diagnosis: Linux 6.8's ACPI idle code can select its safe state when bus-master activity is detected. No bus-master safety check was bypassed. [Kernel implementation](https://github.com/torvalds/linux/blob/v6.8/drivers/acpi/processor_idle.c#L644).

## API response comparison

Qwen3.5-9B Q4_K_M, matching F16 vision projector configured, llama.cpp `4da6337767f973e2b4d0797e5b323d77d8565e4a`, Vulkan; GPU 1700 MHz / 912.5 mV throughout inference. Context 8192, batch/ubatch 128, six helper threads, flash attention enabled, one slot, Jinja enabled, reasoning disabled. Prompt: `Explain how database transactions maintain consistency. Give detailed examples.` Temperature 0, seed 42, maximum 256 tokens. Three sequential requests before and after deployment; first request starts with an unloaded model, following requests reuse it and its prompt cache. Client on another LAN machine; elapsed times rounded to hundredths of a second.

| Policy | First request, including model load | Warm request mean | Mean decode speed, three requests |
|---|---:|---:|---:|
| Existing CPU policy | 13.21 s | 5.515 s | 50.98 tok/s |
| Request-aware CPU policy | 11.81 s | 5.405 s | 52.78 tok/s |

The short sequential sample showed about 3.5% higher decode throughput and 2.0% lower warm response time. No randomized order, cache flush, or repeated cold-load trials were used, so the first-request difference cannot be attributed entirely to CPU handling. CPU active mode was observed during inference; idle mode with no controller QoS request was observed immediately after the final response. The hardware guard remained unlatched. A live abandoned-request test also confirmed that an unrenewed 90-second lease returned to idle and released the latency request. Stopping the service restored all 16 original governors; restarting it restored service and a subsequent arithmetic inference returned 391, then released the CPU setting.

## Reproduction and deployment

[Raw records](../benchmarks/cpu-power/) contain idle windows, API timing/usage data, and observed CPU states. [Sampler](../scripts/auto-profiles/measure_cpu_idle.py): run `sudo python3 measure_cpu_idle.py` on the otherwise idle, unloaded 16-thread board. For governor comparison, save `/sys/devices/system/cpu/cpuidle/current_governor`, write the candidate available governor, run the sampler, and restore the original in a `finally` block. C2 experiments used the same pattern with each `cpu*/cpuidle/state*/disable` whose `name` is C2. Do not infer physical watts from the residency counters. The GPU power sensor reported zero and was not used as a power measurement.

The API comparison requires the model weights pinned in [this model manifest](../benchmarks/automatic-profiles/vision-weight-manifest.json) and the exact settings above. Send the stated prompt three times with 256 maximum tokens, preserving prompt caching. Record client elapsed time and response `timings` fields; unload before the first request of each policy. Use an API key stored locally, never in the report or shell history.

The implementation consists of [cpu_power.py](../scripts/auto-profiles/cpu_power.py), [controller.py](../scripts/auto-profiles/controller.py), [gateway.py](../scripts/auto-profiles/gateway.py), and the updated [controller service](../scripts/auto-profiles/bc250-profile-controller.service). On the existing named-profile installation, back up the two deployed Python files and controller unit under `/opt/bc250-mod-prep/cpu-power/before/` using source names `controller.py`, `gateway.py`, and `bc250-profile-controller.service`. Stop gateway, backend, and controller. Install the new controller/gateway as `/usr/local/libexec/bc250-profile-controller.py` and `/usr/local/libexec/bc250-api-gateway.py`, plus `/usr/local/libexec/cpu_power.py`, all root-owned. Install the controller unit, run `systemctl daemon-reload`, then start controller, backend, and gateway. The service requires write access to `/sys/devices/system/cpu`; its saved governor snapshot is under `/run/bc250-profile`.

Authenticated `GET /v1/hardware` exposes `cpu.mode`, governor selection, controller-owned latency request, and lease time remaining. [CPU tests](../scripts/auto-profiles/test_cpu_power.py) check release, expiry, restoration, and failed activation; [gateway tests](../scripts/auto-profiles/test_gateway.py) cover successful and failed request release, authorization, concurrent requests, streaming disconnects, router cleanup, and thermal fallback. All 11 tests passed. The event-driven 60-second idle timer was also verified live, returning the GPU and CPU to idle. Deployed source hashes match the published implementation. Run both test files with Python 3. [Rollback](../scripts/auto-profiles/rollback_cpu_power.sh) restores the backed-up pre-CPU-handling controller, gateway, and service; it preserves the original GPU profile setup.
