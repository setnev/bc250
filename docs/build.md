# Ubuntu and Vulkan build notes

This is the working configuration of one existing Ubuntu installation. It is not a tested clean-install automation script. The BIOS and GPU modifications are described separately in [firmware.md](firmware.md).

## Runtime

The tested stack is Ubuntu 24.04.5, kernel 6.8.0-142-generic and Mesa RADV 25.2.8. Verify Vulkan device enumeration before adding models:

```bash
vulkaninfo --summary
lscpu
free -h
```

The GPU should appear as AMD BC250 / RADV GFX1013, rather than relying on software-rendered llvmpipe. The live CU method can still report 24 CUs through Vulkan; see the firmware notes.

The existing llama.cpp checkout was built with Vulkan at this exact commit:

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
git checkout 4da6337767f973e2b4d0797e5b323d77d8565e4a
cmake -S . -B build -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
```

Build prerequisites include a C/C++ toolchain, CMake, Vulkan development headers and a GLSL/SPIR-V compiler. Package availability depends on the installed distribution. The live deployment uses `/opt/bc250-ai/llama.cpp` as its checkout path.

## Model files

Model weights are fetched from pinned Hugging Face repository revisions. [model-manifests.json](../benchmarks/model-manifests.json) records source, revision, filename, byte count and SHA-256. Check both size and hash before activation. Model binaries are not in this repository.

Default model: `unsloth/Qwen3.5-9B-GGUF`, Q4_K_M. Experimental Qwen and Llama-family files are listed in [models.md](models.md). They are independent model files, not adapters applied on top of the default.

## Service layout

The deployed layout uses:

```
/opt/bc250-ai/llama.cpp/          runtime checkout and build
/var/lib/bc250-ai/models/        GGUF weights
/etc/bc250-ai/models.ini        router presets
/etc/bc250-ai/api-key           private server key
/etc/bc250-ai/templates/        Llama/Dolphin tool templates
```

The service runs as a dedicated `bc250-ai` account, with `render` and `video` access. Its API key file is readable only by root and the service group. Generate your own key and arrange local client access separately; do not commit it.

[config/bc250-ai.service.example](../config/bc250-ai.service.example) is a sanitized example. It binds to loopback by default. For LAN access, replace the bind address and add the exact intended subnet to `IPAddressAllow`. Reserve the server address through DHCP or configure it explicitly so the bind address remains stable.

[config/models.ini.example](../config/models.ini.example) contains the final presets. The service uses `--models-max 1`, so switching API model IDs unloads the previous model. New models are not loaded on startup; the baseline Qwen model is.

The service is intended for a trusted LAN; this build did not configure Internet exposure or TLS termination. Application-level API authentication remains required.

## Memory and concurrency

The tested operating point is 8 GiB reserved GPU memory, about 7.5 GiB Linux RAM, one resident model and one inference slot. Qwen variants use 8192 context; Llama variants use 4096. Context counts prompt plus generated output.

A 12 GiB GPU / 4 GiB CPU allocation produced heavy swapping with this setup. Larger reserved GPU memory did not automatically translate to better Vulkan inference. The GTT budget also fell as Linux-visible RAM decreased.

## Validate before relying on it

Verify the API's model list and a real completion, not just a healthy process. Confirm a request without a key is rejected. Check swap activity, kernel logs, GPU temperature and the CU startup service result. Then run the [isolated benchmark](benchmarks.md) without concurrent inference.

This guide intentionally keeps firmware flashing, installation and benchmarking as separate operations. The supplied benchmark script performs no flash, unlock, package installation or service management.
