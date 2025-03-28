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
-->

## Test Evidence (if applicable)
> [!IMPORTANT]
> Visual Proof is required for Bug Fixes, New Features, and Breaking Changes:

### Screenshots or Video/GIF:
<!-- Provide your evidence here -->

> [!NOTE]
> For Non-LLM Plugin Changes:
> - **Bug Fixes**:
>   - [ ] Show the Fix working
> - **New Features**:
>   - [ ] Demonstrate the Functionality
> - **Breaking Changes**:
>   - [ ] Show both Old and New Behavior
>
> For LLM Plugin Changes:
> [LLM Plugin Test Example](https://github.com/langgenius/dify-official-plugins/blob/main/.assets/test-examples/llm-plugin-tests/llm_test_example.md)
> - **Bug Fixes**:
>   - [ ] Show the Fix working with Example Inputs/Outputs
> - **New Features**:
>   - [ ] Demonstrate the Functionality with Example Inputs/Outputs
> - **Breaking Changes** (requires comprehensive Testing):
>   - **Conversation & Interaction**:
>       - [ ] Message Flow Handling (System Messages and User→Assistant Turn-taking)
>       - [ ] Tool Interaction Flow (Multi-round Usage and Output Handling if applicable)
>   - **Input/Output Handling**:
>     - [ ] Multimodal Input Handling (Images, PDFs, Audio, Video if applicable)
>     - [ ] Multimodal Output Generation (Images, Audio, Video if applicable)
>     - [ ] Structured Output Format (if applicable)
>   - **Metrics**:
>     - [ ] Token Consumption Metrics
>   - **Others**:
>     - [ ] e.g., Reasoning Process for  Claude 3.7 Sonnet, Grounding for Gemini (if applicable)

### Environment Verification
> [!IMPORTANT]
> Please confirm your Testing Environment:
- [ ] Changes tested in a Clean/Isolated Environment
- [ ] Test Environment matches Production Configuration
- [ ] No Cached Data influenced the Test Results 