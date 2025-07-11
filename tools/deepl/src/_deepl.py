from typing import Annotated, Generator

import deepl
from deepl import TextResult
from dify_easy.model import (
    BasePlugin,
    Credential,
    CredentialType,
    FormType,
    MetaInfo,
    Param,
    ParamType,
    provider,
    tool,
)
from pydantic import BaseModel


class DeepLCredentials(BaseModel):
    auth_key: Annotated[
        str,
        Credential(
            name="auth_key",
            label="Auth Key",
            help="Your DeepL Auth Key",
            placeholder="Enter your DeepL Auth Key",
            url="https://www.deepl.com/en/your-account/keys",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""


class DeepLPlugin(BasePlugin):
    credentials: DeepLCredentials = DeepLCredentials()

    @provider
    def verify(self):
        try:
            client = deepl.DeepLClient(self.credentials.auth_key)
            assert client.get_usage() is not None, "Auth Key is not valid"
        except Exception as e:
            raise e

    @tool(
        name="translate_text",
        label="Translate Text",
        description="Translate text from one language to another",
    )
    def translate_text(
        self,
        text: Annotated[
            str,
            Param(
                name="text",
                label="Text",
                description="The text to translate",
                llm_description="The text to translate",
                type=ParamType.string,
                required=True,
            ),
        ],
        source_lang: Annotated[
            str,
            Param(
                name="source_lang",
                label="Source Language",
                description="The source language of the text. Follow the ISO 639-1 language codes. For example, 'EN' for English, 'DE' for German, 'FR' for French, etc.",
                llm_description="The source language of the text. If not provided, DeepL will detect the source language automatically. Follow the ISO 639-1 language codes. For example, 'EN' for English, 'DE' for German, 'FR' for French, etc.",
                type=ParamType.string,
                required=False,
            ),
        ] = "",
        target_lang: Annotated[
            str,
            Param(
                name="target_lang",
                label="Target Language",
                description="The target language of the text. Follow the ISO 639-1 language codes. For example, 'EN' for English, 'DE' for German, 'FR' for French, etc.",
                llm_description="The target language of the text. Follow the ISO 639-1 language codes. Required. For example, 'EN' for English, 'DE' for German, 'FR' for French, etc.",
                type=ParamType.string,
                required=True,
            ),
        ] = "EN",
    ) -> Generator:
        client = deepl.DeepLClient(self.credentials.auth_key)
        result = client.translate_text(
            text=text, source_lang=source_lang, target_lang=target_lang
        )
        assert isinstance(result, TextResult), "Translation failed"
        yield {
            "text": result.text,
            "detected_source_lang": result.detected_source_lang,
            "billed_characters": result.billed_characters,
        }
        yield result.text

    @tool(
        name="rephrase_text",
        label="Rephrase Text",
        description="Rephrase text to make it more natural",
    )
    def rephrase_text(
        self,
        text: Annotated[
            str,
            Param(
                name="text",
                label="Text",
                description="The text to rephrase",
                type=ParamType.string,
                required=True,
            ),
        ],
        target_lang: Annotated[
            str,
            Param(
                name="target_lang",
                label="Target Language",
                description="The target language of the text. Follow the ISO 639-1 language codes. For example, 'EN' for English, 'DE' for German, 'FR' for French, etc.",
                llm_description="The target language of the text. Follow the ISO 639-1 language codes. Required. For example, 'EN' for English, 'DE' for German, 'FR' for French, etc.",
                type=ParamType.string,
                required=True,
            ),
        ],
    ) -> Generator:
        client = deepl.DeepLClient(self.credentials.auth_key)
        result = client.rephrase_text(text=text, target_lang=target_lang)
        assert isinstance(result, TextResult), "Rephrasing failed"
        yield {
            "text": result.text,
            "detected_source_lang": result.detected_source_lang,
            "billed_characters": result.billed_characters,
        }
        yield result.text


plugin = DeepLPlugin(
    meta=MetaInfo(
        name="deepl",
        author="langgenius",
        description="Translate texts or rephrase text using DeepL",
        version="0.1.0",
        label="DeepL",
        icon="icon.svg",
    )
)
