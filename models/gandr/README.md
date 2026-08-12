# Gandr TTS

Text-to-speech models provided by Gandr, an OpenAI-compatible speech API with 23 languages and six stock voices.

## Configure

Install Gandr TTS from Dify Marketplace. Get an API key from Gandr and fill in the configurations in **Settings → Model Providers**.

| Field | Required | Description |
|-------|----------|-------------|
| API Key | Yes | Your Gandr API key (gnd_… key from tts.gandr.ai). |
| API Base URL | No | Defaults to `https://tts.gandr.ai`. Also try `tts-nyc.gandr.ai` or `tts-eu.gandr.ai` for regional doors. |

## Contract

Gandr exposes an OpenAI-compatible speech endpoint at `POST /v1/audio/speech`. The request shape is OpenAI's:

- `model`: pass `tts-1`
- `input`: the text to speak
- `voice`: OpenAI voice names (alloy, echo, fable, onyx, nova, shimmer, ash, ballad, coral, sage, verse) are mapped to Gandr engine voices; native `gandr-*` ids pass through.
- `response_format`: `wav` (RIFF header) or `pcm` (headerless). There is no mp3 encoder on the doors; an mp3 request returns a deliberate 400.
- `speed`: optional, clamped to 0.6 … 1.5 by the Gandr shim.

### Voice aliases (server-side)

| OpenAI name | Gandr engine voice |
|-------------|-------------------|
| alloy | gandr-mia |
| ash | gandr-dane |
| ballad | gandr-lewis |
| coral | gandr-ava |
| echo | gandr-leo |
| fable | gandr-lewis |
| nova | gandr-jenny |
| onyx | gandr-dane |
| sage | gandr-ava |
| shimmer | gandr-ava |
| verse | gandr-leo |

The native Gandr engine voices are also available directly: `gandr-mia`, `gandr-ava`, `gandr-jenny`, `gandr-dane`, `gandr-leo`, `gandr-lewis`.

### Supported languages (23)

English, Spanish, French, German, Portuguese, Italian, Dutch, Polish, Turkish, Swedish, Danish, Norwegian, Finnish, Czech, Romanian, Russian, Ukrainian, Greek, Arabic, Hindi, Chinese, Japanese, Korean.

## Usage

In a Dify workflow or chatflow, add a **Text-to-Speech** node and select **Gandr → tts-1**. Pick any voice from the list above; the OpenAI names map automatically.

```python
from openai import OpenAI

client = OpenAI(base_url="https://tts.gandr.ai/v1", api_key="gnd_...")
audio = client.audio.speech.create(
    model="tts-1",
    voice="alloy",      # or "gandr-mia", "gandr-ava", etc.
    input="Hello from Gandr!",
    response_format="wav",
)
with open("output.wav", "wb") as f:
    f.write(audio.content)
```