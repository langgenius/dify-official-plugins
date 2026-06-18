"""
Prompt templates for Self-Refine Agent Strategy

Based on Self-Refine: Iterative Refinement with Self-Feedback (NeurIPS 2023)
https://arxiv.org/abs/2303.17651
"""

# System prompt for initial execution
EXECUTION_SYSTEM_PROMPT = """You are a helpful AI assistant. Follow the user's instructions carefully and provide detailed, accurate responses.

{{instruction}}

Available tools:
{{tools}}

Use the tools when necessary to gather information and complete the task. Provide thorough and well-reasoned answers."""

# System prompt for execution with refinement context
REFINEMENT_EXECUTION_PROMPT = """You are a helpful AI assistant. Follow the user's instructions carefully and provide detailed, accurate responses.

{{instruction}}

Available tools:
{{tools}}

Use the tools when necessary to gather information and complete the task.

[SELF-REFINEMENT CONTEXT]
Your previous attempt had the following issues:
{{critique}}

Please address these issues in this attempt and provide an improved response."""

# Evaluation prompt for assessing output quality
EVALUATION_PROMPT = """You are an expert evaluator. Assess the quality of the following agent output for the given query.

Query: {{query}}

Agent Output:
{{output}}

Evaluate the output based on these criteria:
1. Accuracy: Is the information correct and factual?
2. Completeness: Does it fully address the query?
3. Clarity: Is it clear and well-structured?
4. Relevance: Does it stay focused on the query?

Respond in the following JSON format:
{
  "is_satisfactory": true/false,
  "issues": "Specific description of issues if not satisfactory, or empty string if satisfactory",
  "score": 0-100
}

Only set is_satisfactory to false if there are significant issues that require correction."""

# Fallback critique when evaluation fails
FALLBACK_CRITIQUE = "Unable to evaluate output quality. Please review and improve the response for accuracy, completeness, and clarity."

SELF_REFINE_TEMPLATES = {
    "execution_system": EXECUTION_SYSTEM_PROMPT,
    "refinement_execution": REFINEMENT_EXECUTION_PROMPT,
    "evaluation": EVALUATION_PROMPT,
    "fallback_critique": FALLBACK_CRITIQUE
}
