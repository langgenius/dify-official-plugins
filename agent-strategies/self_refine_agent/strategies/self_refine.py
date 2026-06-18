import json
import logging
import time
from collections.abc import Generator
from typing import Any, Optional

from dify_plugin.entities.agent import AgentInvokeMessage
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.llm import LLMModelConfig, LLMResult, LLMResultChunk, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage
)
from dify_plugin.entities.tool import ToolInvokeMessage, ToolProviderType
from dify_plugin.interfaces.agent import (
    AgentModelConfig,
    AgentStrategy,
    ToolEntity,
    ToolInvokeMeta
)
from pydantic import BaseModel, Field

from prompt.templates import SELF_REFINE_TEMPLATES

logger = logging.getLogger(__name__)


class LogMetadata:
    """Metadata keys for logging"""
    STARTED_AT = "started_at"
    PROVIDER = "provider"
    FINISHED_AT = "finished_at"
    ELAPSED_TIME = "elapsed_time"
    TOTAL_PRICE = "total_price"
    CURRENCY = "currency"
    TOTAL_TOKENS = "total_tokens"


class ExecutionMetadata(BaseModel):
    """Execution metadata with default values"""
    total_price: float = 0.0
    currency: str = ""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency: float = 0.0

    @classmethod
    def from_llm_usage(cls, usage: Optional[LLMUsage]) -> "ExecutionMetadata":
        """Create ExecutionMetadata from LLMUsage, handling None case"""
        if usage is None:
            return cls()

        return cls(
            total_price=float(usage.total_price) if usage.total_price else 0.0,
            currency=usage.currency if usage.currency else "",
            total_tokens=usage.total_tokens if usage.total_tokens else 0,
            prompt_tokens=usage.prompt_tokens if usage.prompt_tokens else 0,
            completion_tokens=usage.completion_tokens if usage.completion_tokens else 0,
            latency=usage.latency if usage.latency else 0.0
        )


class ContextItem(BaseModel):
    content: str
    title: str
    metadata: dict[str, Any]


class SelfRefineParams(BaseModel):
    query: str
    instruction: str
    model: AgentModelConfig
    tools: list[ToolEntity] | None = None
    maximum_iterations: int = 5
    max_refinements: int = 2
    context: list[ContextItem] | None = None


class EvaluationResult(BaseModel):
    """Result of output evaluation"""
    is_satisfactory: bool = False
    issues: str = ""
    score: int = 0


class SelfRefineStrategy(AgentStrategy):
    """
    Self-Refine Agent Strategy

    Implements iterative refinement loop:
    1. Execute: Run agent task
    2. Evaluate: Check output quality
    3. Critique: Generate improvement suggestions
    4. Refine: Re-execute with critique context
    """

    def _invoke(
        self,
        parameters: dict[str, Any]
    ) -> Generator[AgentInvokeMessage]:
        """Main entry point for Self-Refine strategy"""
        try:
            params = SelfRefineParams(**parameters)
        except Exception as e:
            logger.error(f"Failed to parse parameters: {e}")
            yield self.create_text_message(f"Error: Invalid parameters - {str(e)}")
            return

        logger.info(f"Starting Self-Refine with max_refinements={params.max_refinements}")

        refinement_count = 0
        previous_critique: Optional[str] = None
        final_output = ""
        total_metadata = ExecutionMetadata()

        while refinement_count <= params.max_refinements:
            attempt_number = refinement_count + 1

            # === EXECUTION PHASE ===
            yield self.create_log_message(
                label=f"Attempt {attempt_number}/{params.max_refinements + 1}",
                data={},
                status=ToolInvokeMessage.LogMessage.LogStatus.START
            )

            logger.info(f"Starting execution attempt {attempt_number}")

            try:
                execution_result = yield from self._execute_agent(
                    params=params,
                    previous_output=final_output if refinement_count > 0 else None,
                    previous_critique=previous_critique,
                    attempt_number=attempt_number
                )

                final_output = execution_result["output"]
                metadata = execution_result["metadata"]

                # Accumulate metadata
                total_metadata.total_tokens += metadata.total_tokens
                total_metadata.total_price += metadata.total_price
                total_metadata.latency += metadata.latency

                yield self.create_log_message(
                    label=f"Attempt {attempt_number} Complete",
                    data={"output_length": len(final_output)},
                    status=ToolInvokeMessage.LogMessage.LogStatus.FINISH
                )

            except Exception as e:
                logger.error(f"Execution attempt {attempt_number} failed: {e}")
                yield self.create_log_message(
                    label=f"Attempt {attempt_number} Failed",
                    data={"error": str(e)},
                    status=ToolInvokeMessage.LogMessage.LogStatus.ERROR
                )

                if refinement_count >= params.max_refinements:
                    yield self.create_text_message(f"Error: Execution failed - {str(e)}")
                    return

                refinement_count += 1
                continue

            # === EVALUATION PHASE ===
            if refinement_count >= params.max_refinements:
                logger.info("Max refinements reached, skipping evaluation")
                break

            yield self.create_log_message(
                label="Evaluating Output Quality",
                data={},
                status=ToolInvokeMessage.LogMessage.LogStatus.START
            )

            try:
                evaluation = self._evaluate_output(
                    params=params,
                    output=final_output
                )

                if evaluation.is_satisfactory:
                    yield self.create_log_message(
                        label="Quality Check: PASS",
                        data={"score": evaluation.score},
                        status=ToolInvokeMessage.LogMessage.LogStatus.FINISH
                    )
                    logger.info(f"Output satisfactory (score: {evaluation.score})")
                    break
                else:
                    yield self.create_log_message(
                        label="Quality Check: NEEDS IMPROVEMENT",
                        data={
                            "score": evaluation.score,
                            "issues": evaluation.issues
                        },
                        status=ToolInvokeMessage.LogMessage.LogStatus.FINISH
                    )
                    logger.info(f"Output needs improvement: {evaluation.issues}")
                    previous_critique = evaluation.issues
                    refinement_count += 1

            except Exception as e:
                logger.error(f"Evaluation failed: {e}")
                yield self.create_log_message(
                    label="Evaluation Failed",
                    data={"error": str(e)},
                    status=ToolInvokeMessage.LogMessage.LogStatus.ERROR
                )
                break

        # === FINAL OUTPUT ===
        yield self.create_text_message(final_output)

        yield self.create_json_message({
            "refinement_count": refinement_count,
            "total_attempts": refinement_count + 1,
            "total_tokens": total_metadata.total_tokens,
            "total_price": total_metadata.total_price,
            "total_latency": total_metadata.latency
        })

    def _execute_agent(
        self,
        params: SelfRefineParams,
        previous_critique: Optional[str],
        attempt_number: int
    ) -> Generator[AgentInvokeMessage, None, dict[str, Any]]:
        """Execute agent task with optional refinement context"""

        # Build system prompt
        tools_json = json.dumps([
            tool.model_dump(mode="json") for tool in (params.tools or [])
        ])

        if previous_critique:
            system_prompt = (
                SELF_REFINE_TEMPLATES["refinement_execution"]
                .replace("{{instruction}}", params.instruction)
                .replace("{{tools}}", tools_json)
                .replace("{{critique}}", previous_critique)
            )
        else:
            system_prompt = (
                SELF_REFINE_TEMPLATES["execution_system"]
                .replace("{{instruction}}", params.instruction)
                .replace("{{tools}}", tools_json)
            )

        # Build prompt messages
        prompt_messages: list[PromptMessage] = [
            SystemPromptMessage(content=system_prompt)
        ]

        # Add context if available
        if params.context:
            context_text = "\n\n[Context]\n"
            for ctx in params.context:
                context_text += f"- {ctx.title}: {ctx.content}\n"
            prompt_messages.append(UserPromptMessage(content=context_text))

        # Add history if available
        if params.model.history_prompt_messages:
            prompt_messages.extend(params.model.history_prompt_messages)

        prompt_messages.append(UserPromptMessage(content=params.query))

        # Prepare model config
        model_config = LLMModelConfig(**params.model.model_dump(mode="json"))

        # Check if streaming is supported
        stream = (
            ModelFeature.STREAM_TOOL_CALL in params.model.entity.features
            if params.model.entity and params.model.entity.features
            else False
        )

        # Prepare tools
        prompt_tools = self._init_prompt_tools(params.tools) if params.tools else []

        # Invoke LLM
        yield self.create_log_message(
            label=f"Invoking {params.model.model}",
            data={},
            status=ToolInvokeMessage.LogMessage.LogStatus.START
        )

        started_at = time.perf_counter()

        try:
            chunks = self.session.model.llm.invoke(
                model_config=model_config,
                prompt_messages=prompt_messages,
                stream=stream,
                tools=prompt_tools,
                stop=[]
            )

            # Collect response
            response_text = ""
            tool_calls: list[tuple[str, str, dict[str, Any]]] = []
            usage: Optional[LLMUsage] = None

            if stream and isinstance(chunks, Generator):
                for chunk in chunks:
                    if chunk.delta and chunk.delta.message and chunk.delta.message.content:
                        response_text += chunk.delta.message.content

                    if chunk.delta and chunk.delta.message and chunk.delta.message.tool_calls:
                        for tool_call in chunk.delta.message.tool_calls:
                            if tool_call.function:
                                tool_calls.append((
                                    tool_call.id or "",
                                    tool_call.function.name,
                                    json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                                ))

                    if chunk.delta and chunk.delta.usage:
                        usage = chunk.delta.usage
            else:
                result = chunks if isinstance(chunks, LLMResult) else next(chunks)
                if result.message and result.message.content:
                    response_text = result.message.content

                if result.message and result.message.tool_calls:
                    for tool_call in result.message.tool_calls:
                        if tool_call.function:
                            tool_calls.append((
                                tool_call.id or "",
                                tool_call.function.name,
                                json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                            ))

                usage = result.usage

            elapsed_time = time.perf_counter() - started_at
            metadata = ExecutionMetadata.from_llm_usage(usage)
            metadata.latency = elapsed_time

            yield self.create_log_message(
                label=f"{params.model.model} Response",
                data={
                    "response": response_text[:200] + "..." if len(response_text) > 200 else response_text,
                    "tool_calls": len(tool_calls)
                },
                status=ToolInvokeMessage.LogMessage.LogStatus.FINISH
            )

            # Execute tool calls if any
            final_output = response_text

            if tool_calls and params.tools:
                tool_results = yield from self._execute_tools(
                    tool_calls=tool_calls,
                    tools=params.tools
                )

                # Append tool results to output
                if tool_results:
                    final_output += "\n\n[Tool Results]\n" + "\n".join(tool_results)

            return {
                "output": final_output,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")
            raise

    def _execute_tools(
        self,
        tool_calls: list[tuple[str, str, dict[str, Any]]],
        tools: list[ToolEntity]
    ) -> Generator[AgentInvokeMessage, None, list[str]]:
        """Execute tool calls and return results"""

        tool_instances = {tool.identity.name: tool for tool in tools}
        results = []

        for tool_call_id, tool_name, tool_params in tool_calls:
            if tool_name not in tool_instances:
                logger.warning(f"Tool {tool_name} not found")
                results.append(f"{tool_name}: Tool not found")
                continue

            tool = tool_instances[tool_name]

            yield self.create_log_message(
                label=f"Executing Tool: {tool_name}",
                data={"parameters": tool_params},
                status=ToolInvokeMessage.LogMessage.LogStatus.START
            )

            try:
                tool_result = self.session.tool.invoke(
                    provider=tool.identity.provider,
                    tool_name=tool_name,
                    parameters=tool_params
                )

                result_text = ""
                for message in tool_result:
                    if message.type == ToolInvokeMessage.MessageType.TEXT:
                        result_text += message.message
                    elif message.type == ToolInvokeMessage.MessageType.JSON:
                        result_text += json.dumps(message.message)

                results.append(f"{tool_name}: {result_text}")

                yield self.create_log_message(
                    label=f"Tool {tool_name} Complete",
                    data={"result": result_text[:100] + "..." if len(result_text) > 100 else result_text},
                    status=ToolInvokeMessage.LogMessage.LogStatus.FINISH
                )

            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                results.append(f"{tool_name}: Error - {str(e)}")

                yield self.create_log_message(
                    label=f"Tool {tool_name} Failed",
                    data={"error": str(e)},
                    status=ToolInvokeMessage.LogMessage.LogStatus.ERROR
                )

        return results

    def _evaluate_output(
        self,
        params: SelfRefineParams,
        output: str
    ) -> EvaluationResult:
        """Evaluate output quality using LLM as judge"""

        eval_prompt = (
            SELF_REFINE_TEMPLATES["evaluation"]
            .replace("{{query}}", params.query)
            .replace("{{output}}", output)
        )

        prompt_messages = [
            UserPromptMessage(content=eval_prompt)
        ]

        model_config = LLMModelConfig(**params.model.model_dump(mode="json"))

        try:
            result = self.session.model.llm.invoke(
                model_config=model_config,
                prompt_messages=prompt_messages,
                stream=False,
                tools=[],
                stop=[]
            )

            if isinstance(result, Generator):
                result = next(result)

            eval_text = result.message.content if result.message and result.message.content else ""

            # Parse JSON response
            try:
                # Try to extract JSON from response
                json_start = eval_text.find("{")
                json_end = eval_text.rfind("}") + 1

                if json_start >= 0 and json_end > json_start:
                    json_str = eval_text[json_start:json_end]
                    eval_data = json.loads(json_str)

                    return EvaluationResult(
                        is_satisfactory=eval_data.get("is_satisfactory", False),
                        issues=eval_data.get("issues", ""),
                        score=eval_data.get("score", 0)
                    )
                else:
                    raise ValueError("No JSON found in response")

            except Exception as e:
                logger.warning(f"Failed to parse evaluation JSON: {e}, using fallback")
                return EvaluationResult(
                    is_satisfactory=False,
                    issues=SELF_REFINE_TEMPLATES["fallback_critique"],
                    score=50
                )

        except Exception as e:
            logger.error(f"Evaluation LLM call failed: {e}")
            return EvaluationResult(
                is_satisfactory=False,
                issues=SELF_REFINE_TEMPLATES["fallback_critique"],
                score=50
            )

    def _init_prompt_tools(self, tools: list[ToolEntity] | None) -> list[ToolInvokeMeta]:
        """Convert ToolEntity to ToolInvokeMeta for LLM invocation"""
        if not tools:
            return []

        prompt_tools = []
        for tool in tools:
            prompt_tools.append(
                ToolInvokeMeta(
                    provider_type=tool.identity.provider_type or ToolProviderType.BUILT_IN,
                    provider=tool.identity.provider,
                    tool_name=tool.identity.name,
                    tool_parameters=tool.runtime_parameters or {}
                )
            )

        return prompt_tools
