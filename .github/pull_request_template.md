### Related Issue or Context
<!--
- Link Related Issues if Applicable: #issue_number
- Or Provide Context about Why this Change is Needed
-->

### Non-Code Changes
<!-- Put an `x` in all the boxes that Apply -->
- [ ] Documentation
- [ ] Other

### Non-LLM Models Code Changes
- [ ] I have Run All Tests Relevant to My Code Changes
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

### LLM Models Code Changes

<!-- LLM Models Test Example: -->
<!-- https://github.com/langgenius/dify-official-plugins/blob/main/.assets/test-examples/llm-plugin-tests/llm_test_example.md -->

- [ ] My Changes Affect Message Flow Handling (System Messages and User→Assistant Turn-Taking)
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Tool Interaction Flow (Multi-Round Usage and Output Handling)
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Multimodal Input Handling (Images, PDFs, Audio, Video, etc.)
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Multimodal Output Generation (Images, Audio, Video, etc.)
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Structured Output Format (JSON, XML, etc.)
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Token Consumption Metrics
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Other Functionalities (e.g., Reasoning Process for Claude 3.7 Sonnet, Grounding for Gemini)
<!-- Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

### Version Control (Any Changes to the Plugin Will Require Bumping the Version)
- [ ] I have Bumped Up the Version in Manifest.yaml (Top-Level `Version` Field, Not in Meta Section)
<!-- Version Format: MAJOR.MINOR.PATCH
- MAJOR (0.x.x): Reserved for Major Releases with Widespread Breaking Changes
- MINOR (x.0.x): For New Features or Limited Breaking Changes
- PATCH (x.x.0): For Backwards-Compatible Bug Fixes and Minor Improvements
- Note: Each Version Component (MAJOR, MINOR, PATCH) Can Be 2 Digits, e.g., 10.11.22
-->

### Environment Verification (If Any Code Changes)
<!-- At Least One Environment Must Be Tested. -->

#### Local Deployment Environment
- [ ] I have Tested My Changes on Local Deployment Dify Version: <!-- Specify Your Version (e.g., 1.2.0) -->

- [ ] I have Tested My Changes in a Clean Environment That Matches the Production Configuration
<!--
- Python Virtual Env Matching Manifest.yaml & requirements.txt
- No Breaking Changes in Dify That May Affect the Testing Result
-->

#### SaaS Environment
- [ ] I have Tested My Changes on cloud.dify.ai
- [ ] I have Tested My Changes in a Clean Environment That Matches the Production Configuration
<!--
- Python Virtual Env Matching Manifest.yaml & requirements.txt
-->
