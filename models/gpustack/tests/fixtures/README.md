# Qwen3.5 chat template fixture

`qwen35-chat-template.jinja` is the official Qwen3.5-35B-A3B template snapshot
retrieved on 2026-11-09 from:

https://huggingface.co/Qwen/Qwen3.5-35B-A3B/raw/main/chat_template.jinja

It is kept locally so the message-order regression test runs without network
access. The test verifies the plugin's actual serialized messages against the
template, including its single-initial-System requirement. It does not execute
model inference or establish compatibility with other templates.
