# Privacy

This plugin sends audio files and transcription parameters to the endpoint
configured in your Oruk provider or model settings:

- **Hosted Oruk Speech API (default):** `https://speech-api.oruk.ai/v1`
- **Self-hosted mode:** any custom OpenAI-compatible `Endpoint URL` that you
  supply (for example `http://localhost:8000/v1`)

Each transcription request sends the audio file payload, model identifier, and
response format (`json`) over HTTP `POST /audio/transcriptions`. Credential
validation calls `GET /models`. When an API key is configured, it is sent as a
`Bearer` token in the `Authorization` header.

This plugin does not store audio files, transcripts, credentials, analytics, or
telemetry outside Dify. When using the hosted Oruk Speech API, data processing
is governed by Oruk's [Privacy Policy](https://oruk.ai/privacy) and
[Terms of Service](https://oruk.ai/terms). When using a self-hosted endpoint,
the operator of that server controls audio handling and retention.
