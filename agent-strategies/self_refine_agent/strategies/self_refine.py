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
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import (
    AgentModelConfig,
    AgentStrategy,
    ToolEntity
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
    content: str = ""
    title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


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
                    status=ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
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
                        status=ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
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
                        status=ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
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
        prompt_tools = self._init_prompt_tools(params.tools)
        has_tools = bool(params.tools)

        # One execution attempt is itself a loop: the model may call tools, read
        # the observations and then continue. `maximum_iterations` bounds the
        # number of model calls so a model that keeps calling tools cannot spin
        # forever.
        max_rounds = max(1, params.maximum_iterations) if has_tools else 1
        metadata = ExecutionMetadata()
        final_output = ""
        observations: list[str] = []
        started_at = time.perf_counter()

        for round_number in range(1, max_rounds + 1):
            yield self.create_log_message(
                label=f"Invoking {params.model.model}",
                data={"round": round_number},
                status=ToolInvokeMessage.LogMessage.LogStatus.START
            )

            try:
                chunks = self.session.model.llm.invoke(
                    model_config=model_config,
                    prompt_messages=prompt_messages,
                    stream=stream,
                    tools=prompt_tools,
                    stop=[]
                )

                response_text, tool_calls, usage = self._collect_response(chunks, stream)

            except Exception as e:
                logger.error(f"LLM invocation failed: {e}")
                raise

            self._accumulate_usage(metadata, usage)

            yield self.create_log_message(
                label=f"{params.model.model} Response",
                data={
                    "response": response_text[:200] + "..." if len(response_text) > 200 else response_text,
                    "tool_calls": len(tool_calls)
                },
                status=ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
            )

            if response_text:
                final_output = response_text

            if not tool_calls or not has_tools:
                break

            # Same rule as the official cot_agent: on the last of several rounds
            # there is no round left to consume the observations, so stop instead
            # of running tools whose results would be discarded.
            if round_number == max_rounds and max_rounds > 1:
                logger.warning(f"Hit maximum_iterations={max_rounds} with tool calls still pending")
                yield self.create_log_message(
                    label="Maximum Iterations Reached",
                    data={"maximum_iterations": max_rounds},
                    status=ToolInvokeMessage.LogMessage.LogStatus.ERROR
                )
                break

            # Record what the model asked for, then hand the observations back to
            # it. Without this the model never sees any tool output.
            prompt_messages.append(
                AssistantPromptMessage(
                    content=response_text,
                    tool_calls=[
                        AssistantPromptMessage.ToolCall(
                            id=call_id,
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name=tool_name,
                                arguments=json.dumps(tool_params, ensure_ascii=False)
                            )
                        )
                        for call_id, tool_name, tool_params in tool_calls
                    ]
                )
            )

            observations = yield from self._execute_tools(
                tool_calls=tool_calls,
                tools=params.tools or []
            )

            for (call_id, tool_name, _), observation in zip(tool_calls, observations):
                prompt_messages.append(
                    ToolPromptMessage(
                        content=observation,
                        tool_call_id=call_id,
                        name=tool_name
                    )
                )

        # With maximum_iterations=1 the model never gets a round to summarise the
        # observations, so surface them rather than returning an empty answer.
        if not final_output and observations:
            final_output = "\n".join(observations)

        metadata.latency = time.perf_counter() - started_at

        return {
            "output": final_output,
            "metadata": metadata
        }

    def _collect_response(
        self,
        chunks: Generator[LLMResultChunk, None, None] | LLMResult,
        stream: bool
    ) -> tuple[str, list[tuple[str, str, dict[str, Any]]], Optional[LLMUsage]]:
        """Collect text, tool calls and usage from a streaming or blocking result"""

        response_text = ""
        tool_calls: list[tuple[str, str, dict[str, Any]]] = []
        usage: Optional[LLMUsage] = None

        if stream and isinstance(chunks, Generator):
            for chunk in chunks:
                if chunk.delta and chunk.delta.message and chunk.delta.message.content:
                    response_text += chunk.delta.message.get_text_content()

                if chunk.delta and chunk.delta.message and chunk.delta.message.tool_calls:
                    tool_calls.extend(self._parse_tool_calls(chunk.delta.message.tool_calls))

                if chunk.delta and chunk.delta.usage:
                    usage = chunk.delta.usage
        else:
            result = chunks if isinstance(chunks, LLMResult) else next(chunks)
            if result.message and result.message.content:
                response_text = result.message.get_text_content()

            if result.message and result.message.tool_calls:
                tool_calls.extend(self._parse_tool_calls(result.message.tool_calls))

            usage = result.usage

        return response_text, tool_calls, usage

    @staticmethod
    def _parse_tool_calls(
        raw_tool_calls: list[AssistantPromptMessage.ToolCall]
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """Flatten SDK tool calls into (call_id, tool_name, parameters) tuples"""

        return [
            (
                tool_call.id or "",
                tool_call.function.name,
                json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            )
            for tool_call in raw_tool_calls
            if tool_call.function
        ]

    @staticmethod
    def _accumulate_usage(metadata: ExecutionMetadata, usage: Optional[LLMUsage]) -> None:
        """Add one round of usage into the attempt totals"""

        round_usage = ExecutionMetadata.from_llm_usage(usage)
        metadata.total_tokens += round_usage.total_tokens
        metadata.prompt_tokens += round_usage.prompt_tokens
        metadata.completion_tokens += round_usage.completion_tokens
        metadata.total_price += round_usage.total_price
        metadata.currency = round_usage.currency or metadata.currency

    def _execute_tools(
        self,
        tool_calls: list[tuple[str, str, dict[str, Any]]],
        tools: list[ToolEntity]
    ) -> Generator[AgentInvokeMessage, None, list[str]]:
        """Execute tool calls and return one observation per call, in call order.

        The caller relies on the positional pairing with `tool_calls`, so every
        call contributes exactly one entry - failures included.
        """

        tool_instances = {tool.identity.name: tool for tool in tools}
        results = []

        for _tool_call_id, tool_name, tool_params in tool_calls:
            if tool_name not in tool_instances:
                logger.warning(f"Tool {tool_name} not found")
                results.append("Tool not found")
                continue

            tool = tool_instances[tool_name]

            yield self.create_log_message(
                label=f"Executing Tool: {tool_name}",
                data={"parameters": tool_params},
                status=ToolInvokeMessage.LogMessage.LogStatus.START
            )

            try:
                tool_result = self.session.tool.invoke(
                    provider_type=tool.provider_type,
                    provider=tool.identity.provider,
                    tool_name=tool_name,
                    parameters=tool_params,
                    credential_id=tool.credential_id
                )

                result_text = ""
                for message in tool_result:
                    if isinstance(message.message, ToolInvokeMessage.TextMessage):
                        result_text += message.message.text
                    elif isinstance(message.message, ToolInvokeMessage.JsonMessage):
                        result_text += json.dumps(message.message.json_object, ensure_ascii=False)

                results.append(result_text or "The tool returned no textual output.")

                yield self.create_log_message(
                    label=f"Tool {tool_name} Complete",
                    data={"result": result_text[:100] + "..." if len(result_text) > 100 else result_text},
                    status=ToolInvokeMessage.LogMessage.LogStatus.SUCCESS
                )

            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                results.append(f"Error - {str(e)}")

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

            eval_text = result.message.get_text_content() if result.message and result.message.content else ""

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
