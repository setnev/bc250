# Using the API

Base URL: `http://YOUR_BC250_IP:8080/v1`.
Use your own API key as a Bearer token. [client.env.example](../config/client.env.example) shows the expected client variables without containing a real endpoint or key.

```bash
source ./client.env
curl "$BC250_BASE_URL/models" -H "Authorization: Bearer $BC250_API_KEY"
curl "$BC250_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $BC250_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.5-9b-aggressive","messages":[{"role":"user","content":"Review this systemd unit for reliability issues: ..."}],"temperature":0.2,"max_tokens":1024}'
```

| Model ID | Use in this build |
|---|---|
| `qwen3.5-9b` | Text and vision; 1,700 MHz / 912.5 mV |
| `qwen3.5-9b-aggressive` | Text/agent candidate; baseline 1,700 MHz / 925 mV |
| `qwen3.5-4b` | Text and vision; 1,700 MHz / 912.5 mV |
| `gemma-3-4b` | Text and vision; 1,800 MHz / 925 mV |

Huihui and the Llama variants were removed after evaluation. Q36 was tested through a separate loopback-only server and is not registered on this API. See [Q36 results](q36.md).

The gateway serializes requests, waits for the previous model worker to exit, and applies the requested model's hardware profile before loading it. Only one model resides in memory. Different model IDs used by concurrent clients trigger unload/load cycles. Cold requests need longer timeouts; the local test client allows 180 seconds. Use the explicit model ID in every request. After 60 seconds of inactivity, the model unloads and the GPU selects the 1,200 MHz / 925 mV idle profile. No model loads automatically at startup.

Authenticated `GET /v1/hardware` reports the current profile, clock/voltage readback and edge temperature. Responses also include `X-BC250-Profile`, `X-BC250-Clock-MHz` and `X-BC250-Voltage-mV` headers. The 85°C thermal guard stops inference and latches the fault for operator review. The image models remain staged for future API integration.

[Profile measurements, configuration and rollback](automatic-profiles.md).

The API does not establish SSH sessions by itself. A separate agent controller exposes tool schemas and executes model-requested actions. The tested controller had a dedicated SSH key restricted to the lab service. Administrator credentials were used by the fixture setup, never supplied to the model.

The Llama templates shipped inside the downloaded GGUFs did not include tool definitions. During the earlier tests, overrides were configured under `/etc/bc250-ai/templates`:

- Llama Abliterated: the pinned llama.cpp `meta-llama-Llama-3.1-8B-Instruct.jinja` template.
- Dolphin: the pinned `Qwen-Qwen2.5-7B-Instruct.jinja` ChatML tool template, with its default assistant identity changed to Dolphin.

This enabled tool-schema delivery but did not establish reliable agent behavior. Llama produced malformed native tool output; Dolphin made real calls but did not consistently finish and verify repairs. See [the evaluation](models.md).
