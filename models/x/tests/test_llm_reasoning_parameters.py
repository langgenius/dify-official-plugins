from models.llm.llm import XAILargeLanguageModel


def test_reasoning_model_detection_covers_supported_aliases():
    reasoning_models = [
        "grok-4.5",
        "grok-4.3",
        "grok-4",
        "grok-4-fast",
        "grok-4-1-fast",
        "grok-4.20-beta-0309-reasoning",
        "grok-4.20-beta-latest",
        "grok-4.20-multi-agent-beta-latest",
        "grok-code-fast-1",
        "grok-build-0.1",
        "grok-3-mini",
        "grok-3-mini-fast",
    ]
    non_reasoning_models = [
        "grok-4-fast-non-reasoning",
        "grok-4-1-fast-non-reasoning",
        "grok-4.20-beta-0309-non-reasoning",
        "grok-4.20-beta-latest-non-reasoning",
        "grok-4.20-non-reasoning-gv2",
    ]

    for model in reasoning_models:
        assert XAILargeLanguageModel._is_reasoning_model(model)

    for model in non_reasoning_models:
        assert not XAILargeLanguageModel._is_reasoning_model(model)


def test_reasoning_unsupported_parameters_are_removed():
    model_parameters = {
        "frequencyPenalty": 1,
        "frequency_penalty": 1,
        "presencePenalty": 1,
        "presence_penalty": 1,
        "stop": ["done"],
        "stopSequences": ["done"],
        "stop_sequences": ["done"],
        "temperature": 1,
    }

    XAILargeLanguageModel._remove_reasoning_unsupported_parameters(model_parameters)

    assert model_parameters == {"temperature": 1}
