## Related Issues or Context
<!--
⚠️ NOTE: This repository is for Dify Official Plugins only. 
For community contributions, please submit to https://github.com/langgenius/dify-plugins instead.

- Link Related Issues if Applicable: #issue_number
- Or Provide Context about Why this Change is Needed
-->

## This PR contains Changes to *Non-Plugin* 
<!-- Put an `x` in all the boxes that apply by replacing [ ] with [x] 
For example:
- [x] Documentation -->

- [ ] Documentation
- [ ] Other

## This PR contains Changes to *Non-LLM Models Plugin*
- [ ] I have Run Comprehensive Tests Relevant to My Changes
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

## This PR contains Changes to *LLM Models Plugin*

<!-- LLM Models Test Example: -->
<!-- https://github.com/langgenius/dify-official-plugins/blob/main/.assets/test-examples/llm-plugin-tests/llm_test_example.md -->

- [ ] My Changes Affect Message Flow Handling (System Messages and User→Assistant Turn-Taking)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Tool Interaction Flow (Multi-Round Usage and Output Handling, for both Agent App and Agent Node)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Multimodal Input Handling (Images, PDFs, Audio, Video, etc.)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Multimodal Output Generation (Images, Audio, Video, etc.)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Structured Output Format (JSON, XML, etc.)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Token Consumption Metrics
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] My Changes Affect Other LLM Functionalities (Reasoning Process, Grounding, Prompt Caching, etc.)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

- [ ] Other Changes (Add New Models, Fix Model Parameters etc.)
<!-- 📷 Include Screenshots/Videos Demonstrating the Fix, New Feature, or the Behavior Before/After Breaking Changes. -->

## Version Control (Any Changes to the Plugin Will Require Bumping the Version)
- [ ] I have Bumped Up the Version in Manifest.yaml (Top-Level `Version` Field, Not in Meta Section)
<!--
⚠️ NOTE: Version Format: MAJOR.MINOR.PATCH
- MAJOR (0.x.x): Reserved for Significant architectural changes or incompatible API modifications
- MINOR (x.0.x): For New feature additions while maintaining backward compatibility
- PATCH (x.x.0): For Backward-compatible bug fixes and minor improvements
- Note: Each Version Component (MAJOR, MINOR, PATCH) Can Be 2 Digits, e.g., 10.11.22
-->

## Dify Plugin SDK Version
- [ ] I'm Using `dify_plugin>=0.3.0,<0.4.0` in requirements.txt ([SDK docs](https://github.com/langgenius/dify-plugin-sdks/blob/main/python/README.md))

## Environment Verification (If Any Code Changes)
<!-- 
⚠️ NOTE: At Least One Environment Must Be Tested. 
-->

### Local Deployment Environment
- [ ] Dify Version is: <!-- Specify Your Version (e.g., 1.2.0) -->, I have Tested My Changes on Local Deployment Dify with a Clean Environment That Matches the Production Configuration. 
<!--
- Python Virtual Env Matching Manifest.yaml & requirements.txt
- No Breaking Changes in Dify That May Affect the Testing Result
-->

### SaaS Environment
- [ ] I have Tested My Changes on cloud.dify.ai with a Clean Environment That Matches the Production Configuration
<!--
- Python Virtual Env Matching Manifest.yaml & requirements.txt
-->
