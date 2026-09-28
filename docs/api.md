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
| `qwen3.5-9b` | Startup default and comparison baseline |
| `qwen3.5-9b-aggressive` | First experimental candidate for the tested SSH loop |

Huihui and the Llama variants were removed after evaluation. Q36 was tested through a separate loopback-only server and is not registered on this API. See [Q36 results](q36.md).

Only one model resides in memory. Different model IDs used by concurrent clients can trigger repeated unload/load cycles. Cold requests need longer timeouts; the local test client allows 180 seconds. Use the explicit model ID in every request.

The API does not establish SSH sessions by itself. A separate agent controller exposes tool schemas and executes model-requested actions. The tested controller had a dedicated SSH key restricted to the lab service. Administrator credentials were used by the fixture setup, never supplied to the model.

The Llama templates shipped inside the downloaded GGUFs did not include tool definitions. During the earlier tests, overrides were configured under `/etc/bc250-ai/templates`:

- Llama Abliterated: the pinned llama.cpp `meta-llama-Llama-3.1-8B-Instruct.jinja` template.
- Dolphin: the pinned `Qwen-Qwen2.5-7B-Instruct.jinja` ChatML tool template, with its default assistant identity changed to Dolphin.

This enabled tool-schema delivery but did not establish reliable agent behavior. Llama produced malformed native tool output; Dolphin made real calls but did not consistently finish and verify repairs. See [the evaluation](models.md).
