# Overview
Gandr is a closed-source text to speech API. This plugin adds the Gandr TTS model `gandr-1` with six voices (gandr-ava, gandr-dane, gandr-jenny, gandr-leo, gandr-lewis, gandr-mia) to Dify.

# Configure
Install Gandr from Dify Marketplace. Create an API key at gandr.ai (keys start with gnd_) and fill in the configurations in Settings -> Model Providers.

The implementation calls `POST https://tts.gandr.ai/v1/audio/speech` with Bearer auth and a JSON body `{model, input, voice, response_format}`. The response format is mp3 by default (wav and pcm are also supported by the API). Input is limited to 2000 characters; longer texts are split into sentences before requests.
