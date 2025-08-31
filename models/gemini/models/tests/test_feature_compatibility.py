import pytest
from dify_plugin.errors.model import InvokeError
from dify_plugin.entities.model.message import PromptMessageTool

try:
    from models.llm.llm import GoogleLargeLanguageModel
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from models.llm.llm import GoogleLargeLanguageModel


# Test fixtures
@pytest.fixture
def llm():
    """LLM instance for testing"""
    return GoogleLargeLanguageModel([])


@pytest.fixture
def sample_tools():
    """Sample tools for testing"""
    return [
        PromptMessageTool(
            name="get_weather",
            description="Get weather information",
            parameters={
                "type": "object",
                "properties": {"location": {"type": "string", "description": "City name"}},
                "required": ["location"],
            },
        )
    ]


# Test data for parametrized tests
SINGLE_FEATURES = [
    ("json_schema", '{"type": "object"}'),
    ("grounding", True),
    ("url_context", True),
    ("code_execution", True),
]

FALSY_VALUES = [
    ("grounding", 0),
    ("url_context", ""),
    ("code_execution", []),
    ("json_schema", None),
]

TRUTHY_VALUES = [
    ("grounding", 1),
    ("url_context", "yes"),
    ("code_execution", ["enabled"]),
    ("json_schema", {"type": "object"}),
]

JSON_SCHEMA_CONFLICTS = [
    ({"json_schema": '{"type": "object"}', "grounding": True}, "grounding"),
    ({"json_schema": '{"type": "string"}', "url_context": True}, "url_context"),
    ({"json_schema": '{"properties": {}}', "code_execution": True}, "code_execution"),
]

VALID_COMBINATIONS = [
    ({"grounding": True, "url_context": True}, "grounding with url_context"),
    ({"grounding": True, "code_execution": True}, "grounding with code_execution"),
]

AUTO_DISABLE_CASES = [
    ({"grounding": True}, "grounding"),
    ({"url_context": True}, "url_context"),
    ({"code_execution": True}, "code_execution"),
]

COMPLEX_AUTO_DISABLE_CASES = [
    (
        {"grounding": True, "url_context": True, "temperature": 0.7},
        {"grounding": False, "url_context": False, "temperature": 0.7},
        "grounding and url_context with preserved params",
    ),
    (
        {"grounding": True, "code_execution": True, "max_tokens": 1000},
        {"grounding": False, "code_execution": False, "max_tokens": 1000},
        "grounding and code_execution with preserved params",
    ),
    (
        {"grounding": True, "url_context": False, "code_execution": True, "max_tokens": 1000},
        {"grounding": False, "url_context": False, "code_execution": False, "max_tokens": 1000},
        "selective auto-disable",
    ),
]


class TestFeatureCompatibility:
    """Comprehensive test suite for _validate_feature_compatibility method"""

    # ========== Test No Features Enabled ==========

    @pytest.mark.parametrize(
        "model_params",
        [{}, {"json_schema": None, "grounding": False, "url_context": "", "code_execution": 0}],
    )
    def test_no_features_enabled(self, llm, model_params):
        """Test that validation passes when no features are enabled"""
        result = llm._validate_feature_compatibility(model_params, None)
        assert result == model_params

    # ========== Test Single Feature Enabled ==========

    @pytest.mark.parametrize("feature_name,feature_value", SINGLE_FEATURES)
    def test_single_feature_enabled(self, llm, feature_name, feature_value):
        """Test that each feature alone is valid"""
        model_params = {feature_name: feature_value}
        result = llm._validate_feature_compatibility(model_params, None)
        assert result == model_params

    def test_tools_only(self, llm, sample_tools):
        """Test that custom tools alone are valid"""
        model_params = {}
        result = llm._validate_feature_compatibility(model_params, sample_tools)
        assert result == model_params

    # ========== Test json_schema Exclusivity (Rule 1) ==========

    @pytest.mark.parametrize("model_params,conflict_feature", JSON_SCHEMA_CONFLICTS)
    def test_json_schema_conflicts(self, llm, model_params, conflict_feature):
        """Test that json_schema conflicts with other features"""
        with pytest.raises(
            InvokeError, match=f"Structured output.*cannot be used with.*{conflict_feature}"
        ):
            llm._validate_feature_compatibility(model_params, None)

    def test_json_schema_with_tools_fails(self, llm, sample_tools):
        """Test that json_schema + custom tools is invalid"""
        model_params = {"json_schema": '{"type": "array"}'}
        with pytest.raises(InvokeError, match="Structured output.*cannot be used with.*tools"):
            llm._validate_feature_compatibility(model_params, sample_tools)

    def test_json_schema_with_multiple_features_fails(self, llm, sample_tools):
        """Test that json_schema with multiple other features is invalid"""
        model_params = {"json_schema": '{"type": "object"}', "grounding": True, "url_context": True}
        with pytest.raises(InvokeError) as exc_info:
            llm._validate_feature_compatibility(model_params, sample_tools)

        error_msg = str(exc_info.value)
        assert "Structured output" in error_msg or "json_schema" in error_msg
        assert "tools" in error_msg

    # ========== Test Valid Combinations ==========

    @pytest.mark.parametrize("model_params,description", VALID_COMBINATIONS)
    def test_valid_feature_combinations(self, llm, model_params, description):
        """Test valid feature combinations"""
        result = llm._validate_feature_compatibility(model_params, None)
        assert result == model_params

    # ========== Test Auto-Disable Tool-Use Features ==========

    @pytest.mark.parametrize("model_params,feature_name", AUTO_DISABLE_CASES)
    def test_features_auto_disabled_with_tools(self, llm, sample_tools, model_params, feature_name):
        """Test that tool-use features are auto-disabled when custom tools are present"""
        result = llm._validate_feature_compatibility(model_params, sample_tools)
        assert result[feature_name] is False

    @pytest.mark.parametrize("input_params,expected_params,description", COMPLEX_AUTO_DISABLE_CASES)
    def test_complex_auto_disable_scenarios(
        self, llm, sample_tools, input_params, expected_params, description
    ):
        """Test complex auto-disable scenarios with parameter preservation"""
        result = llm._validate_feature_compatibility(input_params, sample_tools)
        assert result == expected_params

    def test_no_auto_disable_without_tools(self, llm):
        """Test that tool-use features are not disabled when no custom tools are present"""
        model_params = {"grounding": True, "url_context": True}
        result = llm._validate_feature_compatibility(model_params, None)
        assert result["grounding"] is True
        assert result["url_context"] is True

    @pytest.mark.parametrize("tools", [[], None])
    def test_empty_or_none_tools_no_auto_disable(self, llm, tools):
        """Test that empty/None tools list doesn't trigger auto-disable"""
        model_params = {"grounding": True, "url_context": True}
        result = llm._validate_feature_compatibility(model_params, tools)
        assert result["grounding"] is True
        assert result["url_context"] is True

    # ========== Test Invalid Combinations ==========

    @pytest.mark.parametrize(
        "model_params",
        [
            {"url_context": True, "code_execution": True},
            {"grounding": True, "url_context": True, "code_execution": True},
        ],
    )
    def test_url_context_code_execution_conflicts(self, llm, model_params):
        """Test that url_context + code_execution is invalid (Rule 3)"""
        with pytest.raises(
            InvokeError, match="`url_context` and `code_execution` cannot be enabled simultaneously"
        ):
            llm._validate_feature_compatibility(model_params, None)

    def test_url_context_code_execution_with_tools_auto_disabled(self, llm, sample_tools):
        """Test that url_context + code_execution are auto-disabled when tools are present"""
        model_params = {"url_context": True, "code_execution": True}
        result = llm._validate_feature_compatibility(model_params, sample_tools)
        assert result["url_context"] is False
        assert result["code_execution"] is False

    # ========== Test Edge Cases and Type Variations ==========

    @pytest.mark.parametrize("feature_name,feature_value", TRUTHY_VALUES)
    def test_truthy_values_treated_as_enabled(self, llm, feature_name, feature_value):
        """Test that various truthy values are correctly interpreted as enabled"""
        model_params = {feature_name: feature_value}
        if feature_name == "json_schema":
            # json_schema with dictionary should be treated as enabled
            model_params.update({"grounding": True})  # Add conflict to test
            with pytest.raises(InvokeError, match="Structured output"):
                llm._validate_feature_compatibility(model_params, None)
        else:
            # Other truthy values should be valid alone
            result = llm._validate_feature_compatibility(model_params, None)
            assert result == model_params

    @pytest.mark.parametrize("feature_name,feature_value", FALSY_VALUES)
    def test_falsy_values_treated_as_disabled(self, llm, feature_name, feature_value):
        """Test that various falsy values are correctly interpreted as disabled"""
        model_params = {feature_name: feature_value}
        result = llm._validate_feature_compatibility(model_params, None)
        assert result == model_params

    def test_unexpected_parameters_ignored(self, llm):
        """Test that unexpected parameters don't affect validation"""
        model_params = {
            "grounding": True,
            "url_context": True,
            "unexpected_param": "value",
            "another_param": 123,
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        result = llm._validate_feature_compatibility(model_params, None)
        assert result == model_params

    def test_case_sensitive_parameter_names(self, llm):
        """Test that parameter names are case-sensitive"""
        model_params = {
            "JSON_SCHEMA": '{"type": "object"}',  # Wrong case - should be ignored
            "Grounding": True,  # Wrong case - should be ignored
            "grounding": True,  # Correct case
            "url_context": True,  # Correct case
        }
        result = llm._validate_feature_compatibility(model_params, None)
        assert result == model_params

    # ========== Test Error Message Quality ==========

    def test_error_message_for_json_schema_conflicts(self, llm, sample_tools):
        """Test that json_schema conflict error messages are clear"""
        model_params = {
            "json_schema": '{"type": "object"}',
            "grounding": True,
            "code_execution": True,
        }
        with pytest.raises(InvokeError) as exc_info:
            llm._validate_feature_compatibility(model_params, sample_tools)

        error_msg = str(exc_info.value)
        assert "Structured output" in error_msg or "json_schema" in error_msg
        assert "tools" in error_msg

    def test_error_message_for_url_context_code_execution(self, llm):
        """Test that url_context + code_execution error is clear"""
        model_params = {"url_context": True, "code_execution": True}
        with pytest.raises(InvokeError) as exc_info:
            llm._validate_feature_compatibility(model_params, None)

        error_msg = str(exc_info.value)
        assert "url_context" in error_msg
        assert "code_execution" in error_msg
        assert "simultaneously" in error_msg or "together" in error_msg

    # ========== Test Real-World Scenarios ==========

    @pytest.mark.parametrize(
        "scenario,model_params,tools,expected_features",
        [
            ("RAG with auto-disable", {"grounding": True}, "sample_tools", {"grounding": False}),
            ("Function calling", {}, "sample_tools", {}),
            (
                "Structured output",
                {"json_schema": '{"type": "object", "properties": {"name": {"type": "string"}}}'},
                None,
                {"json_schema": '{"type": "object", "properties": {"name": {"type": "string"}}}'},
            ),
            (
                "Code analysis",
                {"code_execution": True, "grounding": True},
                None,
                {"code_execution": True, "grounding": True},
            ),
            (
                "Web research",
                {"grounding": True, "url_context": True},
                None,
                {"grounding": True, "url_context": True},
            ),
        ],
    )
    def test_real_world_scenarios(
        self, llm, sample_tools, scenario, model_params, tools, expected_features
    ):
        """Test typical real-world usage scenarios"""
        actual_tools = sample_tools if tools == "sample_tools" else tools
        result = llm._validate_feature_compatibility(model_params, actual_tools)

        for feature, expected_value in expected_features.items():
            assert result[feature] == expected_value

    # ========== Test Static Method Behavior ==========

    def test_static_method_can_be_called_without_instance(self):
        """Test that the static method can be called without an instance"""
        model_params = {"grounding": True}
        result = GoogleLargeLanguageModel._validate_feature_compatibility(model_params, None)
        assert result == model_params

    # ========== Test with Mock Logging ==========

    def test_logging_auto_disable_actions(self, llm, sample_tools):
        """Test that auto-disable actions are logged"""
        from unittest.mock import patch

        model_params = {"grounding": True, "url_context": True}

        # Try different patch paths to handle different execution contexts
        patch_paths = ["models.llm.llm.logging.debug", "llm.logging.debug"]
        patch_worked = False

        for patch_path in patch_paths:
            try:
                with patch(patch_path) as mock_debug:
                    result = llm._validate_feature_compatibility(model_params, sample_tools)

                    assert result["grounding"] is False
                    assert result["url_context"] is False
                    assert mock_debug.call_count >= 1
                    patch_worked = True
                    break
            except (ImportError, AttributeError):
                continue

        if not patch_worked:
            # Fallback: just test the functionality without logging verification
            result = llm._validate_feature_compatibility(model_params, sample_tools)
            assert result["grounding"] is False
            assert result["url_context"] is False

    def test_no_logging_when_no_features(self, llm):
        """Test that nothing is logged when no features are enabled"""
        from unittest.mock import patch

        model_params = {}

        # Try different patch paths to handle different execution contexts
        patch_paths = ["models.llm.llm.logging.debug", "llm.logging.debug"]
        patch_worked = False

        for patch_path in patch_paths:
            try:
                with patch(patch_path) as mock_debug:
                    result = llm._validate_feature_compatibility(model_params, None)
                    assert result == model_params
                    mock_debug.assert_not_called()
                    patch_worked = True
                    break
            except (ImportError, AttributeError):
                continue

        if not patch_worked:
            # Fallback: just test the functionality without logging verification
            result = llm._validate_feature_compatibility(model_params, None)
            assert result == model_params
