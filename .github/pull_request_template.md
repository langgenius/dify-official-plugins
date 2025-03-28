## Related Issue or Context
<!-- 
- Link related issues if applicable: #issue_number
- Or provide context about why this change is needed
-->

## Type of Change
<!-- Put an `x` in all the boxes that apply -->
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code refactoring
- [ ] Others

## Test Evidence
> [!IMPORTANT]
> Visual proof is required for Bug fixes, New features, Breaking changes:

- Screenshots or Video/GIF (if applicable):

> [!NOTE]
> For Non-LLM Plugin Changes:
> - **Bug fixes**:
>   - [ ] Show the fix working
> - **New features**:
>   - [ ] Demonstrate the functionality
> - **Breaking changes**:
>   - [ ] Show both old and new behavior
>
> For LLM Plugin Changes:
> - **Bug fixes**:
>   - [ ] Show the fix working with example inputs/outputs
> - **New features**:
>   - [ ] Demonstrate the functionality with example inputs/outputs
> - **Breaking changes** (requires comprehensive testing):
>   - **Conversation & Interaction**:
>     - Conversation sequence correctness:
>       - [ ] System message handling
>       - [ ] Proper turn-taking (user→assistant messages)
>     - Tool usage demonstrations (if applicable):
>       - [ ] Multi-round tool interactions
>       - [ ] Appropriate handling of tool outputs
>   - **Input/Output Handling**:
>     - [ ] Multimodal input handling (images, PDFs, audio, video if applicable)
>     - [ ] Multimodal output generation (images, PDFs, audio, video if applicable)
>     - [ ] Structured output format (if applicable)
>   - **Metrics**:
>     - [ ] Token consumption metrics
>   - **Others**:
>     - [ ] Reasoning process (if applicable, e.g. tool use)

### Environment Verification
> [!IMPORTANT]
> Please confirm your testing environment:
- [ ] Changes tested in a clean/isolated environment
- [ ] Test environment matches production configuration
- [ ] No cached data influenced the test results 