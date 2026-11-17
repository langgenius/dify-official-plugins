"""DeepSeek model registration and request serialization regressions (no network)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError

from models.llm.llm import TongyiLargeLanguageModel

MODELS = Path(__file__).resolve().parents[1] / 'models' / 'llm'
OPTIONS = {
    'deepseek-v4.1-flash': ['low', 'high', 'max'],
    'deepseek-v4.1-flash-1017': ['low', 'high', 'max'],
    'deepseek-v4-pro': ['high', 'max'],
    'deepseek-v4-flash-0731': ['low', 'high', 'max'],
}


def instance(name):
    schema = AIModelEntity.model_validate(yaml.safe_load((MODELS / f'{name}.yaml').read_text()))
    model = TongyiLargeLanguageModel(model_schemas=[schema])
    return model, schema


@pytest.mark.parametrize('name', OPTIONS)
def test_schema_and_parameter_validation(name):
    model, schema = instance(name)
    rule = next(r for r in schema.parameter_rules if r.name == 'reasoning_effort')
    assert rule.type.value == 'string'
    assert rule.options == OPTIONS[name]
    assert rule.default == 'high'
    for effort in OPTIONS[name]:
        params = model._validate_and_filter_model_parameters(name, {'reasoning_effort': effort}, {})
        assert params['reasoning_effort'] == effort
        assert params['enable_thinking'] is True


def test_snapshot_registered_with_vision():
    name = 'deepseek-v4.1-flash-1017'
    _, schema = instance(name)
    assert name in yaml.safe_load((MODELS / '_position.yaml').read_text())
    assert ModelFeature.VISION in schema.features
    assert ModelFeature.TOOL_CALL in schema.features


@pytest.mark.parametrize('effort', [1, 50, 100, '50', 'medium', 'ultra', True, [], {}])
def test_invalid_effort_is_rejected_before_network(effort):
    name = 'deepseek-v4.1-flash-1017'
    model, _ = instance(name)
    with pytest.raises(InvokeBadRequestError, match='reselect'):
        model._validate_and_filter_model_parameters(name, {'reasoning_effort': effort}, {})


@pytest.mark.parametrize('name', OPTIONS)
def test_thinking_off_removes_stale_effort_without_mutating_input(name):
    model, _ = instance(name)
    original = {'enable_thinking': False, 'reasoning_effort': 75}
    params = model._validate_and_filter_model_parameters(name, original, {})
    # Optional schema defaults may be filled by the SDK; generation removes
    # effort again after defaults are applied.
    model._normalize_deepseek_parameters(name, params)
    assert 'reasoning_effort' not in params
    assert original == {'enable_thinking': False, 'reasoning_effort': 75}


@pytest.mark.parametrize('name', OPTIONS)
@pytest.mark.parametrize('thinking', [True, False])
def test_sdk_serializes_parameters_and_correct_endpoint(name, thinking):
    model, schema = instance(name)
    captured = {}

    def capture(url, **kwargs):
        captured['url'] = url
        captured['body'] = json.loads(kwargs['data'])
        raise RuntimeError('request captured without network')

    parameters = {'enable_thinking': thinking, 'reasoning_effort': 'max', 'max_tokens': 512}
    # Exercise the real DashScope SDK through serialization, stopping at HTTP.
    with patch('requests.Session.post', side_effect=capture):
        with pytest.raises(Exception, match='request captured without network'):
            result = model._generate(
                model=name,
                credentials={'dashscope_api_key': 'test-key', 'api_host': 'workspace.example.test'},
                prompt_messages=[UserPromptMessage(content='hello')],
                model_parameters=parameters,
                stream=False,
            )
            if thinking:
                list(result)
    route = 'multimodal-generation' if ModelFeature.VISION in schema.features else 'text-generation'
    assert captured['url'] == f'https://workspace.example.test/api/v1/services/aigc/{route}/generation'
    body = captured['body']
    assert body['model'] == name
    assert body['parameters']['enable_thinking'] is thinking
    assert 'reasoning_effort' not in body
    if thinking:
        assert body['parameters']['reasoning_effort'] == 'max'
        assert body['parameters']['incremental_output'] is True
    else:
        assert 'reasoning_effort' not in body['parameters']
    assert parameters['reasoning_effort'] == 'max'


def test_pro_rejects_unsupported_low():
    model, _ = instance('deepseek-v4-pro')
    with pytest.raises(InvokeBadRequestError):
        model._validate_and_filter_model_parameters('deepseek-v4-pro', {'reasoning_effort': 'low'}, {})


def test_other_models_are_not_normalized():
    parameters = {'reasoning_effort': 50}
    TongyiLargeLanguageModel._normalize_deepseek_parameters('other-model', parameters)
    assert parameters == {'reasoning_effort': 50}


def test_snapshot_validation_consumes_deferred_api_errors():
    model, _ = instance('deepseek-v4.1-flash-1017')

    def deferred_error(**kwargs):
        yield None
        raise InvokeBadRequestError('upstream rejected credentials')

    with patch.object(model, '_generate', side_effect=deferred_error):
        with pytest.raises(CredentialsValidateFailedError, match='upstream rejected'):
            model.validate_credentials('deepseek-v4.1-flash-1017', {'dashscope_api_key': 'test-key'})
