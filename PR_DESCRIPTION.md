## Related Issues or Context

This PR implements GPT-5.x parameter compatibility logic where `temperature`, `top_p`, and `logprobs` are only supported when `reasoning_effort` is set to `"none"`.

According to OpenAI's GPT-5 documentation, when reasoning is enabled (reasoning_effort != "none"), the model automatically handles temperature control, and manual temperature/top_p settings are not supported.

## This PR contains Changes to *Non-Plugin*

- [ ] Documentation
- [ ] Other

## This PR contains Changes to *Non-LLM Models Plugin*
- [ ] I have Run Comprehensive Tests Relevant to My Changes

## This PR contains Changes to *LLM Models Plugin*

- [ ] My Changes Affect Message Flow Handling (System Messages and User→Assistant Turn-Taking)
- [ ] My Changes Affect Tool Interaction Flow (Multi-Round Usage and Output Handling, for both Agent App and Agent Node)
- [ ] My Changes Affect Multimodal Input Handling (Images, PDFs, Audio, Video, etc.)
- [ ] My Changes Affect Multimodal Output Generation (Images, Audio, Video, etc.)
- [ ] My Changes Affect Structured Output Format (JSON, XML, etc.)
- [ ] My Changes Affect Token Consumption Metrics
- [ ] My Changes Affect Other LLM Functionalities (Reasoning Process, Grounding, Prompt Caching, etc.)
- [x] Other Changes (Add New Models, Fix Model Parameters etc.)

### Changes Summary

**Backend Logic Changes:**
- `models/openai/models/llm/llm.py`: Added GPT-5.x parameter compatibility logic in `_chat_generate` method
- `models/azure_openai/models/llm/llm.py`: Added same parameter compatibility logic in `_chat_generate` method

**Frontend Configuration Changes:**
- `models/openai/models/llm/gpt-5.yaml` and all GPT-5.x YAML files: Added temperature and top_p parameters with help text
- `models/azure_openai/models/constants.py`: Added temperature and top_p ParameterRule entries to all GPT-5.x model definitions with help text

**Parameter Compatibility Logic:**
- When `reasoning_effort` is not "none", temperature, top_p, and logprobs are automatically removed from the API request
- Help text in both English and Chinese explains this limitation to users

## Version Control (Any Changes to the Plugin Will Require Bumping the Version)
- [x] I have Bumped Up the Version in Manifest.yaml (Top-Level `Version` Field, Not in Meta Section)

**Version Changes:**
- OpenAI plugin: `0.3.4` → `0.3.5`
- Azure OpenAI plugin: `0.0.49` → `0.0.50`

## Dify Plugin SDK Version
- [x] I have Ensured `dify_plugin>=0.3.0,<0.6.0` is in requirements.txt ([SDK docs](https://github.com/langgenius/dify-plugin-sdks/blob/main/python/README.md))

## Environment Verification (If Any Code Changes)

### Local Deployment Environment
- [ ] Dify Version is: <!-- Specify Your Version (e.g., 1.2.0) -->, I have Tested My Changes on Local Deployment Dify with a Clean Environment That Matches the Production Configuration. 

### SaaS Environment
- [ ] I have Tested My Changes on cloud.dify.ai with a Clean Environment That Matches the Production Configuration

---

## Testing Notes

To test the parameter compatibility:
1. Set `reasoning_effort` to different values ("none", "low", "medium", "high", "xhigh")
2. Set `temperature` to a value like 0.5
3. Observe that when `reasoning_effort` is not "none", the temperature parameter is automatically removed from the API request

## Related Documentation

- OpenAI GPT-5 Documentation: https://platform.openai.com/docs/guides/reasoning
- Note: GPT-5 models with reasoning enabled do not support temperature, top_p, and logprobs parameters
