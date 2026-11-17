import json
import re
from decimal import Decimal
from typing import Any

from scripts.catalog_schema import CatalogError, _decimal, _positive_int, _string

DIFY_UI_LOCALES = {
    "ar-TN",
    "az-AZ",
    "de-DE",
    "en-US",
    "es-ES",
    "fa-IR",
    "fr-FR",
    "hi-IN",
    "id-ID",
    "it-IT",
    "ja-JP",
    "ko-KR",
    "lo-LA",
    "nl-NL",
    "pl-PL",
    "pt-BR",
    "ro-RO",
    "ru-RU",
    "sl-SI",
    "th-TH",
    "tr-TR",
    "uk-UA",
    "vi-VN",
    "zh-Hans",
    "zh-Hant",
}


def _validate_identity(model: dict[str, Any]) -> None:
    _string(model.get("provider"), f"{model['id']}.provider")
    if not isinstance(model.get("deprecated"), bool):
        raise CatalogError(f"{model['id']}.deprecated must be a boolean")


def _validate_embedding(model: dict[str, Any]) -> None:
    _validate_identity(model)
    _positive_int(model.get("contextSize"), f"{model['id']}.contextSize")
    pricing = model.get("pricing")
    if not isinstance(pricing, dict) or pricing.get("currency") != "USD":
        raise CatalogError(f"{model['id']}.pricing.currency must be USD")
    _decimal(pricing.get("inputPerMillion"), f"{model['id']}.pricing.inputPerMillion")


def _validate_rerank(model: dict[str, Any]) -> None:
    _validate_identity(model)


def _render_embedding(model: dict[str, Any]) -> str:
    return (
        json.dumps(
            {
                "model": model["id"],
                "label": {"en_US": model["id"], "zh_Hans": model["id"]},
                "model_type": "text-embedding",
                "model_properties": {
                    "context_size": model["contextSize"],
                    "max_chunks": 10
                    if model["id"] in {"text-embedding-v3", "text-embedding-v4"}
                    else 32,
                },
                "pricing": {
                    "input": model["pricing"]["inputPerMillion"],
                    "unit": "0.000001",
                    "currency": "USD",
                },
                "deprecated": model["deprecated"],
            },
            indent=2,
        )
        + "\n"
    )


def _render_rerank(model: dict[str, Any]) -> str:
    return (
        json.dumps(
            {
                "model": model["id"],
                "label": {"en_US": model["id"], "zh_Hans": model["id"]},
                "model_type": "rerank",
                "model_properties": {},
                "deprecated": model["deprecated"],
            },
            indent=2,
        )
        + "\n"
    )


def _validate_speech2text(model: dict[str, Any]) -> None:
    model_id = model["id"]
    _string(model.get("provider"), f"{model_id}.provider")
    if not isinstance(model.get("deprecated"), bool):
        raise CatalogError(f"{model_id}.deprecated must be a boolean")
    audio = model.get("audio")
    if not isinstance(audio, dict):
        raise CatalogError(f"{model_id}.audio must be an object")
    _positive_int(audio.get("maxUploadBytes"), f"{model_id}.audio.maxUploadBytes")
    extensions = audio.get("supportedExtensions")
    if (
        not isinstance(extensions, list)
        or not 1 <= len(extensions) <= 32
        or any(
            not isinstance(ext, str) or re.fullmatch(r"[a-z0-9]+", ext) is None
            for ext in extensions
        )
    ):
        raise CatalogError(f"{model_id}.audio.supportedExtensions must contain 1 to 32 extensions")
    _validate_audio_pricing(model, {"second", "million_tokens"})


def _validate_audio_pricing(model: dict[str, Any], allowed_units: set[str]) -> None:
    model_id = model["id"]
    pricing = model.get("pricing")
    if not isinstance(pricing, dict) or pricing.get("currency") != "USD":
        raise CatalogError(f"{model_id}.pricing.currency must be USD")
    rates = pricing.get("rates")
    if not isinstance(rates, list) or not 1 <= len(rates) <= 6:
        raise CatalogError(f"{model_id}.pricing.rates must contain 1 to 6 rates")
    for rate in rates:
        if (
            not isinstance(rate, dict)
            or rate.get("direction") not in ("input", "output")
            or rate.get("modality") not in ("text", "audio")
            or not isinstance(rate.get("unit"), str)
            or rate["unit"] not in allowed_units
            or not isinstance(rate.get("price"), str)
            or re.fullmatch(r"[0-9]+(?:\.[0-9]{1,6})?", rate["price"]) is None
        ):
            raise CatalogError(f"{model_id}.pricing.rates contains an invalid audio rate")


def _validate_tts(model: dict[str, Any]) -> None:
    model_id = model["id"]
    _string(model.get("provider"), f"{model_id}.provider")
    if not isinstance(model.get("deprecated"), bool):
        raise CatalogError(f"{model_id}.deprecated must be a boolean")
    audio = model.get("audio")
    if not isinstance(audio, dict):
        raise CatalogError(f"{model_id}.audio must be an object")
    voices = audio.get("voices")
    if not isinstance(voices, list) or not 1 <= len(voices) <= 128:
        raise CatalogError(f"{model_id}.audio.voices must contain 1 to 128 voices")
    voice_ids = set()
    for voice in voices:
        if not isinstance(voice, dict):
            raise CatalogError(f"{model_id}.audio.voices must contain voice objects")
        voice_id = _string(voice.get("id"), f"{model_id}.audio.voices.id")
        voice_ids.add(voice_id)
        languages = voice.get("languages")
        if not isinstance(languages, list):
            raise CatalogError(
                f"{model_id}.audio.voices[{voice_id}].languages must be a string array"
            )
        for language in languages:
            if not isinstance(language, str) or language not in DIFY_UI_LOCALES:
                raise CatalogError(
                    f"{model_id}.audio.voices[{voice_id}].languages: "
                    f"{language!r} is not a Dify UI locale code"
                )
    default_voice = _string(audio.get("defaultVoice"), f"{model_id}.audio.defaultVoice")
    if default_voice not in voice_ids:
        raise CatalogError(f"{model_id}.audio.defaultVoice must be one of the voices")
    _positive_int(audio.get("wordLimit"), f"{model_id}.audio.wordLimit")
    if audio.get("audioFormat") not in ("mp3", "aac", "opus", "pcm"):
        raise CatalogError(f"{model_id}.audio.audioFormat is unsupported")
    _validate_audio_pricing(model, {"second", "character", "million_tokens"})


def _render_tts(model: dict[str, Any]) -> str:
    audio = model["audio"]
    lines = [
        f"model: {json.dumps(model['id'])}",
        "label:",
        f"  en_US: {json.dumps(model['id'], ensure_ascii=False)}",
        f"  zh_Hans: {json.dumps(model['id'], ensure_ascii=False)}",
        "model_type: tts",
        "model_properties:",
        f"  default_voice: {json.dumps(audio['defaultVoice'])}",
        f"  word_limit: {audio['wordLimit']}",
        f"  audio_type: {json.dumps(audio['audioFormat'])}",
        "  voices:",
    ]
    for voice in audio["voices"]:
        lines.extend(
            [
                f"    - mode: {json.dumps(voice['id'])}",
                f"      name: {json.dumps(voice['id'])}",
                f"      language: {json.dumps(voice['languages'], ensure_ascii=False)}",
            ]
        )
    lines.append(f"deprecated: {str(model['deprecated']).lower()}")
    return "\n".join(lines) + "\n"


def _render_speech2text(model: dict[str, Any]) -> str:
    audio = model["audio"]
    upload_mb = Decimal(audio["maxUploadBytes"]) / 1000000
    extensions = json.dumps(",".join(audio["supportedExtensions"]))
    return (
        "\n".join(
            [
                f"model: {json.dumps(model['id'])}",
                "label:",
                f"  en_US: {json.dumps(model['id'], ensure_ascii=False)}",
                f"  zh_Hans: {json.dumps(model['id'], ensure_ascii=False)}",
                "model_type: speech2text",
                "model_properties:",
                f"  file_upload_limit: {upload_mb:f}",
                f"  supported_file_extensions: {extensions}",
                f"deprecated: {str(model['deprecated']).lower()}",
            ]
        )
        + "\n"
    )
