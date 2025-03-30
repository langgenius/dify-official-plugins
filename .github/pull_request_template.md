## Related Issue or Context
<!-- 
- Link related Issues if applicable: #issue_number
- Or provide Context about why this Change is needed
-->

## Type of Change
<!-- Put an `x` in all the boxes that apply -->
- [ ] Bug Fix (non-breaking change which fixes an Issue)
- [ ] New Feature (non-breaking change which adds Functionality)
- [ ] Breaking Change (fix or feature that may cause existing Functionality to not work as expected)
- [ ] Documentation Update
- [ ] Code Refactoring
- [ ] Other

## Version Control (if applicable)
- [ ] Version bumped in Manifest.yaml (top-level `Version` field, not in Meta section)
<!-- Version format: MAJOR.MINOR.PATCH
- MAJOR (0.x.x): Reserved for Major Releases with widespread Breaking Changes
- MINOR (x.0.x): For New Features or limited Breaking Changes
- PATCH (x.x.0): For backwards-compatible Bug Fixes and minor Improvements
- Note: Each version component (MAJOR, MINOR, PATCH) can be 2 digits, e.g., 10.11.22
-->

## Test Evidence (if applicable)
> [!IMPORTANT]
> Visual Proof is required for Bug Fixes, New Features, and Breaking Changes:

### Screenshots or Video/GIF:
<!-- Provide your evidence here -->

> [!NOTE]
> For Non-LLM Models Changes:
> - **Bug Fixes**:
>   - [ ] Show the Fix working
> - **New Features**:
>   - [ ] Demonstrate the Functionality
> - **Breaking Changes**:
>   - [ ] Show both Old and New Behavior
>
> For LLM Models Changes:
> - **Bug Fixes**:
>   - [ ] Show the Fix working with Example Inputs/Outputs
> - **New Features**:
>   - [ ] Demonstrate the Functionality with Example Inputs/Outputs
> - **Breaking Changes** (requires comprehensive Testing):
>   - **Conversation & Interaction**:
>     - [ ] Message Flow Handling (System Messages and User→Assistant Turn-taking)
>     - [ ] Tool Interaction Flow (Multi-round Usage and Output Handling if applicable)
>   - **Input/Output Handling**:
>     - [ ] Multimodal Input Handling (Images, PDFs, Audio, Video if applicable)
>     - [ ] Multimodal Output Generation (Images, Audio, Video if applicable)
>     - [ ] Structured Output Format (if applicable)
>   - **Metrics**:
>     - [ ] Token Consumption Metrics
>   - **Others**:
>     - [ ] e.g., Reasoning Process for Claude 3.7 Sonnet, Grounding for Gemini (if applicable)
<!-- LLM Models Test Example: -->
<!-- https://github.com/langgenius/dify-official-plugins/blob/main/.assets/test-examples/llm-plugin-tests/llm_test_example.md -->

### Environment Verification
> [!IMPORTANT]
> At least one environment must be tested.

#### Local Deployment Environment
Local Deployment Dify Version: <!-- Specify your version (e.g., 1.1.3) -->
- [ ] Changes tested in a Clean Environment that matches Production Configuration
<!--
- Python virtual env matching Manifest.yaml & requirements.txt
- No breaking changes in Dify that may affect the testing result
-->

#### SaaS Environment
- [ ] Testing performed on cloud.dify.ai
- [ ] Changes tested in a Clean Environment that matches Production Configuration
<!--
- Python virtual env matching Manifest.yaml & requirements.txt
-->