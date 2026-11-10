# Dingo

A Dify toolkit for job search, resume optimization, and matching resumes to job descriptions.

## Tools

- **Dingo Scout:** Analyze an industry report and a user profile to identify target companies and job search strategies.
- **Resume Optimizer:** Improve a resume for a target position, optionally using a keyword matching report.
- **Keyword Matcher:** Compare a resume with a job description using semantic analysis or local keyword matching.

## Usage

1. Install the plugin in your Dify workspace.
2. Configure the DeepSeek provider and `deepseek-chat` model in Dify for tools that use LLM analysis.
3. Add a tool to a workflow and provide the inputs described in its parameter form.
4. For local keyword matching, disable the Keyword Matcher tool's `use_llm` option.

The registered tools use the Dify SDK and local Python logic.
They do not require the separate `dingo-python` data quality library.

## Privacy

LLM analysis sends the supplied text to the model provider through Dify.
Local keyword matching runs within the plugin.
See [privacy-policy.md](privacy-policy.md) for details.

## License

This project uses the [Apache 2.0 Open Source License](LICENSE).
