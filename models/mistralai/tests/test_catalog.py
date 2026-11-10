"""Catalog registration and multimodal regression checks (no vendor calls)."""
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model.schema import AIModelEntity
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)

from models.llm.llm import MistralAILargeLanguageModel

ROOT = Path(__file__).resolve().parents[1]
LLM = ROOT / 'models' / 'llm'


def test_all_catalogs_register_each_definition_once():
    for directory in (ROOT / 'models').iterdir():
        if not directory.is_dir() or not (directory / '_position.yaml').exists():
            continue
        order = yaml.safe_load((directory / '_position.yaml').read_text())
        definitions = list(directory.glob('*.yaml'))
        definitions = [p for p in definitions if p.name != '_position.yaml']
        assert len(order) == len(set(order))
        assert set(order) == {p.stem for p in definitions}
        for path in definitions:
            raw = yaml.safe_load(path.read_text())
            assert raw['model'] == path.stem
            AIModelEntity.model_validate(raw)
            for rule in raw.get('parameter_rules', []):
                if rule['name'] == 'max_tokens':
                    assert 0 < rule['default'] <= rule['max'] <= raw['model_properties']['context_size']


@pytest.mark.parametrize('model', [
    'mistral-medium-3-5', 'mistral-medium-latest',
    'mistral-large-2512', 'mistral-large-latest',
    'mistral-large-4', 'mistral-large-4-0',
    'mistral-small-2603', 'mistral-small-latest',
    'ministral-3b-2512', 'ministral-3b-latest',
    'ministral-8b-2512', 'ministral-8b-latest',
    'ministral-14b-2512', 'ministral-14b-latest',
])
def test_current_multimodal_models_expose_vision(model):
    definition = yaml.safe_load((LLM / f'{model}.yaml').read_text())
    assert 'vision' in definition['features']


def test_retired_models_are_not_discoverable():
    retired = {
        'codestral-2501', 'devstral-small-2505', 'magistral-medium-2506',
        'magistral-small-2506', 'mistral-small-2503', 'mistral-saba-2502',
        'mistral-saba-latest', 'open-codestral-mamba', 'mathstral',
    }
    assert not retired.intersection(p.stem for p in LLM.glob('*.yaml'))


@pytest.mark.parametrize('image', [
    {'url': 'https://example.com/image.png'},
    {'base64_data': 'aW1hZ2U='},
])
def test_image_input_survives_mistral_message_conversion(image):
    content = ImagePromptMessageContent(format='png', mime_type='image/png', **image)
    message = UserPromptMessage(content=[TextPromptMessageContent(data='Describe'), content])
    llm = object.__new__(MistralAILargeLanguageModel)
    request = llm._convert_prompt_message_to_dict(message)
    assert request['content'] == [
        {'type': 'text', 'text': 'Describe'},
        {'type': 'image_url', 'image_url': {'url': content.data, 'detail': 'low'}},
    ]
