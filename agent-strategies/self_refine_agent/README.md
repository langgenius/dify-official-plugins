# Self-Refine Agent Strategy

A Dify agent strategy plugin that improves output quality through iterative self-critique and refinement.

## What It Does

Self-Refine Agent Strategy implements the [Self-Refine](https://arxiv.org/abs/2303.17651) (NeurIPS 2023) algorithm, enabling agents to automatically evaluate and improve their own outputs through multiple refinement cycles.

The strategy works by having the LLM act as its own critic:
1. **Execute** - Agent generates an initial response
2. **Evaluate** - LLM judges the output quality (0-100 score)
3. **Critique** - LLM identifies specific issues and improvement opportunities
4. **Refine** - Critique is injected into context for the next iteration
5. **Repeat** - Process continues until quality threshold is met or max refinements reached

This approach is particularly effective for tasks requiring high-quality outputs such as writing, analysis, code generation, and complex reasoning.

## Key Features

- **Automatic Quality Control** - LLM evaluates its own outputs without human intervention
- **Iterative Improvement** - Each refinement cycle builds on previous critiques
- **Transparent Process** - All intermediate steps (execution, evaluation, critique) are visible
- **Configurable** - Control maximum iterations and refinement cycles

## Usage

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | model-selector | - | LLM model to use |
| `tools` | array[tools] | - | Available tools for the agent |
| `instruction` | string | - | System instructions for the agent |
| `query` | string | - | User query to process |
| `context` | array[object] | - | Optional context information |
| `maximum_iterations` | number | 5 | Max iterations per agent execution |
| `max_refinements` | number | 2 | Max refinement cycles (0-5) |

### Configuration Example

When configuring the agent in Dify:

1. Select **Self-Refine Agent** as your strategy
2. Choose your preferred LLM model
3. Set `max_refinements` to control quality vs. speed tradeoff:
   - `0` - No refinement (standard agent behavior)
   - `1-2` - Balanced (recommended for most cases)
   - `3-5` - High quality (best for critical outputs)

### Local Development

To test the plugin locally:

1. Create a `.env` file:
```bash
INSTALL_METHOD=remote
DIFY_PLUGIN_DAEMON_URL=http://localhost:5003
```

2. Ensure Dify is running locally (via Docker Compose)

3. Start the plugin:
```bash
python main.py
```

## How It Works

The refinement loop follows this pattern:

```
Initial Query → Agent Execution → Output
                        ↓
                   Evaluation (score)
                        ↓
                   [Score ≥ 80?] → Yes → Return Final Output
                        ↓ No
                   Generate Critique
                        ↓
           Inject Critique into Context
                        ↓
              Re-execute Agent → Output
                        ↓
           [Max refinements reached?] → Yes → Return Best Output
                        ↓ No
                   Repeat Cycle
```

The agent automatically stops refining when:
- Output quality score reaches 80 or above
- Maximum refinement cycles are reached
- No significant improvements are detected

## Reference

Based on the paper:

Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., ... & Clark, P. (2023).
**Self-Refine: Iterative Refinement with Self-Feedback.**
NeurIPS 2023. [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)

## License

MIT License
