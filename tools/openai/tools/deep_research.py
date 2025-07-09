import logging
import time
from collections.abc import Generator
from typing import Any
from openai import OpenAI
from yarl import URL
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DeepResearchTool(Tool):
    """
    Tool to perform deep research using OpenAI's specialized models.
    """

    def _get_openai_client(self, tool_parameters: dict) -> OpenAI:
        """Initializes and returns an OpenAI client."""
        openai_organization = self.runtime.credentials.get("openai_organization_id")
        openai_base_url = self.runtime.credentials.get("openai_base_url")
        timeout = tool_parameters.get("timeout")
        
        return OpenAI(
            api_key=self.runtime.credentials["openai_api_key"],
            base_url=str(URL(openai_base_url) / "v1") if openai_base_url else None,
            organization=openai_organization,
            timeout=timeout if timeout is not None else 3600,
        )

    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the deep research tool.
        """
        # --- Initialize OpenAI Client ---
        client = self._get_openai_client(tool_parameters)

        # --- Parameter Extraction and Validation ---
        action = tool_parameters.get("action", "start")

        if action == "start":
            yield from self._handle_start(client, tool_parameters)
        elif action == "cancel":
            yield from self._handle_cancel(client, tool_parameters)
        elif action == "retrieve":
            yield from self._handle_retrieve(client, tool_parameters)
        else:
            yield self.create_text_message("Error: Invalid action specified.")

    def _handle_start(self, client: OpenAI, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """Handles the 'start' action."""
        prompt = tool_parameters.get("prompt")
        if not prompt or not isinstance(prompt, str):
            yield self.create_text_message("Error: Research Prompt is required for 'start' action.")
            return

        model = tool_parameters.get("model", "o3-deep-research")
        use_web_search = tool_parameters.get("use_web_search", True)
        use_code_interpreter = tool_parameters.get("use_code_interpreter", False)
        max_tool_calls = tool_parameters.get("max_tool_calls")

        if not use_web_search and not use_code_interpreter:
            yield self.create_text_message("Error: At least one data source (web search or code interpreter) must be enabled.")
            return

        tools = []
        if use_web_search:
            tools.append({"type": "web_search_preview"})
        if use_code_interpreter:
            tools.append({"type": "code_interpreter", "container": {"type": "auto"}})

        create_args: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "tools": tools,
            "background": True,  # Always run in the background for the 'start' action
        }
        
        if max_tool_calls is not None:
            try:
                create_args["max_tool_calls"] = int(max_tool_calls)
            except (ValueError, TypeError):
                yield self.create_text_message("Error: Max Tool Calls must be a valid number.")
                return

        try:
            response = client.responses.create(**create_args)
            logging.info(f"Start action raw response: {response}")
            yield self.create_text_message(f"Successfully started deep research task. Response ID: {response.id}")
            
            # Return structured JSON data for the start action
            json_data = {
                "response_id": response.id,
                "status": response.status,
                "model": response.model,
                "background": response.background,
                "max_tool_calls": response.max_tool_calls,
                "tools": [tool.type for tool in response.tools] if response.tools else []
            }
            yield self.create_json_message(json_data)
        except Exception as e:
            logging.error(f"Failed to start deep research task: {e}", exc_info=True)
            yield self.create_text_message(f"Failed to start deep research task: {e}")

    def _handle_cancel(self, client: OpenAI, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """Handles the 'cancel' action."""
        response_id = tool_parameters.get("response_id")
        if not response_id:
            yield self.create_text_message("Error: Response ID is required for 'cancel' action.")
            return

        try:
            cancelled_response = client.responses.cancel(response_id)
            logging.info(f"Cancel action raw response: {cancelled_response}")
            if cancelled_response.status == "cancelled":
                yield self.create_text_message(f"Successfully cancelled research task with ID: {response_id}")
            else:
                yield self.create_text_message(f"Could not cancel task {response_id}. Current status: {cancelled_response.status}")
            
            # Return structured JSON data for the cancel action
            json_data = {
                "response_id": cancelled_response.id,
                "status": cancelled_response.status,
                "model": cancelled_response.model,
                "tools": [tool.type for tool in cancelled_response.tools] if cancelled_response.tools else []
            }
            yield self.create_json_message(json_data)
        except Exception as e:
            logging.error(f"Failed to cancel research task {response_id}: {e}", exc_info=True)
            yield self.create_text_message(f"Failed to cancel research task {response_id}: {e}")

    def _handle_retrieve(self, client: OpenAI, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """Handles the 'retrieve' action."""
        response_id = tool_parameters.get("response_id")
        if not response_id:
            yield self.create_text_message("Error: Response ID is required for 'retrieve' action.")
            return

        try:
            response = client.responses.retrieve(response_id)
            logging.info(f"Retrieve action raw response: {response}")

            if response.status == 'completed':
                yield from self._process_completed_response(response)
            else:
                yield self.create_text_message(f"Status for task `{response_id}`: {response.status}")
                if response.status == 'failed':
                    yield self.create_text_message(f"Error: Deep research task failed. Reason: {response.error}")
                
                # Return structured JSON data for unfinished retrieve actions
                json_data = {
                    "response_id": response.id,
                    "status": response.status,
                    "model": response.model,
                    "background": response.background,
                    "tools": [tool.type for tool in response.tools] if response.tools else []
                }
                
                if response.status == 'failed' and response.error:
                    json_data["error"] = response.error
                
                yield self.create_json_message(json_data)

        except Exception as e:
            logging.error(f"Failed to retrieve research task {response_id}: {e}", exc_info=True)
            yield self.create_text_message(f"Failed to retrieve research task {response_id}: {e}")

    def _process_completed_response(self, response) -> Generator[ToolInvokeMessage, None, None]:
        """Processes a completed response object."""
        # Format and yield the final report as a text message
        formatted_report = self._format_output_with_numbered_citations(response)
        if formatted_report:
            yield self.create_text_message(formatted_report)

        structured_data = {
            "response_id": response.id,
            "status": response.status,
            "model": response.model,
            "background": response.background,
            "tools": [tool.type for tool in response.tools] if response.tools else []
        }

        # Process tool calls for structured JSON output
        if response.output:
            tool_call_details = []
            for item in response.output:
                if item.type == "web_search_call":
                    action = item.action
                    detail = {"tool": "web_search", "action": action.type}
                    if hasattr(action, 'query'):
                        detail["query"] = action.query
                    if hasattr(action, 'url') and action.url:
                        detail["url"] = action.url
                    if hasattr(action, 'pattern'):
                         detail["pattern"] = action.pattern
                    tool_call_details.append(detail)
                elif item.type == "code_interpreter_call":
                    tool_call_details.append({"tool": "code_interpreter", "action": "execute_code"})
            
            if tool_call_details:
                structured_data["research_process"] = tool_call_details

        # Process usage information for structured JSON output
        if response.usage:
            structured_data["usage"] = {
                "total_tokens": response.usage.total_tokens,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        # Yield structured data as a JSON message
        yield self.create_json_message(structured_data)

    def _format_output_with_numbered_citations(self, response) -> str:
        """
        Formats the output text with numbered citations and a reference list.
        """
        # Find the final message content
        message_content = None
        final_report_text = ""
        for item in response.output:
            if item.type == 'message' and hasattr(item, 'content'):
                for content_part in item.content:
                    if content_part.type == 'output_text':
                        message_content = content_part
                        final_report_text = content_part.text
                        break
                if message_content:
                    break

        if not message_content or not hasattr(message_content, 'annotations') or not message_content.annotations:
            return final_report_text

        text = message_content.text
        annotations = message_content.annotations

        # Create a mapping of unique URLs to reference numbers and titles
        unique_refs = {}
        ref_counter = 1
        for ann in annotations:
            if hasattr(ann, 'url') and ann.url not in unique_refs:
                unique_refs[ann.url] = {
                    "number": ref_counter,
                    "title": ann.title,
                }
                ref_counter += 1
        
        # Collect replacements to be made
        replacements = []
        for ann in annotations:
            if hasattr(ann, 'url') and ann.url:
                ref_num = unique_refs[ann.url]["number"]
                
                replacements.append({
                    "start": ann.start_index,
                    "end": ann.end_index,
                    "text": f" [[{ref_num}]]({ann.url})"
                })

        # Sort replacements by start index in reverse order to avoid index shifting issues
        sorted_replacements = sorted(replacements, key=lambda x: x['start'], reverse=True)

        # Apply replacements to the text
        for rep in sorted_replacements:
            text = text[:rep['start']] + rep['text'] + text[rep['end']:]

        # Build the reference list at the end
        if unique_refs:
            text += "\n\n---\n## References\n"
            # Sort refs by number for the final list
            sorted_ref_list = sorted(unique_refs.items(), key=lambda item: item[1]['number'])
            for url, data in sorted_ref_list:
                text += f"{data['number']}. [{data['title']}]({url})\n"
        
        return text

    def _invoke_polling(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """
        Original invoke method with polling. Kept for reference or future use.
        """
        # --- Initialize OpenAI Client ---
        client = self._get_openai_client(tool_parameters)

        # --- Parameter Extraction and Validation ---
        prompt = tool_parameters.get("prompt")
        if not prompt or not isinstance(prompt, str):
            yield self.create_text_message("Error: Research Prompt is required.")
            return

        model = tool_parameters.get("model", "o3-deep-research")
        use_web_search = tool_parameters.get("use_web_search", True)
        use_code_interpreter = tool_parameters.get("use_code_interpreter", False)
        run_in_background = True # Was a parameter, now hardcoded for this logic path
        max_tool_calls = tool_parameters.get("max_tool_calls")

        if not use_web_search and not use_code_interpreter:
            yield self.create_text_message("Error: At least one data source (web search or code interpreter) must be enabled.")
            return

        # --- Prepare API Request ---
        tools = []
        if use_web_search:
            tools.append({"type": "web_search_preview"})
        if use_code_interpreter:
            tools.append({"type": "code_interpreter", "container": {"type": "auto"}})

        create_args: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "tools": tools,
        }

        if run_in_background:
            create_args["background"] = True
        
        if max_tool_calls is not None:
            try:
                create_args["max_tool_calls"] = int(max_tool_calls)
            except (ValueError, TypeError):
                yield self.create_text_message("Error: Max Tool Calls must be a valid number.")
                return

        # --- API Call ---
        try:
            yield self.create_text_message(f"Starting deep research task with model '{model}'...")
            response = client.responses.create(**create_args)
            logging.info(f"Polling initial create raw response: {response}")

            if run_in_background:
                yield self.create_text_message(f"Task running in background. Response ID: {response.id}")
                while response.status in {"queued", "in_progress"}:
                    yield self.create_text_message(f"Current status: {response.status}. Polling again in 10 seconds...")
                    time.sleep(10)
                    response = client.responses.retrieve(response.id)
                    logging.info(f"Polling retrieval raw response: {response}")
                
                logging.info(f"Polling final raw response: {response}")
                yield self.create_text_message(f"Task finished with status: {response.status}")

            if response.status == 'completed':
                yield from self._process_completed_response(response)
            elif response.status == 'failed':
                 yield self.create_text_message(f"Error: Deep research task failed. Reason: {response.error}")
                 return
            elif response.status == 'cancelled':
                 yield self.create_text_message(f"Info: Deep research task was cancelled.")
                 return


        except Exception as e:
            logging.error(f"An unexpected error occurred during polling invocation: {e}", exc_info=True)
            yield self.create_text_message(f"An unexpected error occurred: {e}")
            return 