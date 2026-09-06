# Chat settings and supported model behavior

## Model information, not a synthetic MoE switch

Chat requests read `/api/show` on a background worker. The response is reduced
to architecture, size, quantization, context limit, capabilities and expert
counts; templates, system prompts and saved messages are not sent to the UI.
Rapid selection changes are coalesced, and the UI ignores replies for an old
request/model. This request neither generates text nor loads a model for inference.

`<architecture>.expert_count > 1` is evidence of MoE. Missing expert metadata
means **unknown**, not Dense and not “unsupported.” MoE models use their own
architecture through Ollama; Chat does not claim it can convert a Dense model,
change expert routing, or change the number of active experts. Model selection
is the supported way to select a different architecture.

Thinking is independent of MoE. If `/api/show` advertises `thinking`, Chat exposes
the supported control. GPT-OSS architecture uses `low`, `medium`, `high` and has
no OFF option; other thinking-capable models retain the boolean control. Unknown
or absent capability leaves `think` out of the request. Explicit level errors
are shown, not silently retried without the user's selected level. Boolean
compatibility fallback applies only when the server explicitly says the model
does not support thinking, not when it requires a different thinking value.

Sources checked 2026-09-05:

- [Ollama Show API and metadata example](https://github.com/ollama/ollama/blob/main/docs/api.md#show-model-information)
- [Ollama thinking controls and GPT-OSS limitations](https://docs.ollama.com/capabilities/thinking)
- [Ollama chat request fields](https://docs.ollama.com/api/chat)
- [Ollama generation parameters including temperature](https://docs.ollama.com/modelfile#valid-parameters-and-values)

Only `/api/version` and `/api/show` were inspected on the installed local Ollama.
No test downloaded weights or requested real inference. Automated coverage uses
synthetic `/api/show` and streaming responses; runtime output quality is not
established by these tests.

## Temperature and instructions

The temperature help describes diversity, not an accuracy guarantee. The existing
saved temperature and system instruction stay unchanged on upgrade. The improved
tag/caption preset is an explicit choice: one English Danbooru/Gelbooru tag line,
at least two accurate English sentences, then a short Korean explanation below
the prompt. Counts appear only in the Korean explanation; the prompt excludes
count/quality tags and unsolicited negative prompts. Applying it retains a personal
instruction backup; selecting the restore option brings that backup back.
Instructions guide the LLM; responses are not regex-deleted or claimed to be
guaranteed tag-database matches.

## Clipboard and deletion

Desktop Qt uses `VueBridge.copyTextToClipboard(text)` with a confirmed result.
Web clients use their own browser clipboard, never the host PC clipboard.
The fallback checks `execCommand`'s result and restores focus/selection; a false
result shows an error instead of a success toast. The shared helper is used by
Chat, PNG Info and Comfy metadata details.

Chat uses a themed HTML dialog, with an accessible title/description, native
modal focus containment, initial focus on Cancel, Escape cancellation and focus
restoration. The deletion target is captured when opening; another thread cannot
be accidentally cleared while the dialog is open. A thread's delete control is
an independent keyboard-focusable button, not a button nested in another button.
