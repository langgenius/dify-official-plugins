import base64
import mimetypes
import os
from collections.abc import Generator
from typing import Any

import requests
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class AddAttachmentToDraftTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Add attachments to an existing Gmail draft by:
        1) fetching the draft as raw MIME,
        2) parsing it,
        3) appending attachments,
        4) updating the draft with the new raw MIME.
        """
        try:
            # --- Inputs ---
            draft_id = (tool_parameters.get("draft_id") or "").strip()
            files_to_attach = tool_parameters.get("file_to_attach")  # expects array[file] from Dify
            attachment_name = (tool_parameters.get("attachment_name") or "").strip()

            if not draft_id:
                yield self.create_text_message("Error: Draft ID is required.")
                return

            if not files_to_attach or not isinstance(files_to_attach, (list, tuple)):
                yield self.create_text_message("Error: Files to attach are required (array[file]).")
                return

            # --- Auth ---
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            yield self.create_text_message(f"Preparing to add {len(files_to_attach)} attachment(s) to draft {draft_id}...")

            # --- 1) Fetch draft as RAW ---
            get_url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}?format=raw"
            resp = requests.get(get_url, headers=headers, timeout=60)
            if resp.status_code == 404:
                yield self.create_text_message(f"Draft with ID '{draft_id}' not found.")
                return
            if resp.status_code != 200:
                yield self.create_text_message(f"Failed to retrieve draft: HTTP {resp.status_code} {resp.text}")
                return

            draft = resp.json()
            message = draft.get("message", {})
            raw_b64 = message.get("raw")
            if not raw_b64:
                yield self.create_text_message("Draft did not contain raw content; cannot modify.")
                return

            try:
                original_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
            except Exception as e:
                yield self.create_text_message(f"Failed to decode draft raw content: {e}")
                return

            # --- 2) Parse to EmailMessage ---
            try:
                email_msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(original_bytes)
            except Exception as e:
                yield self.create_text_message(f"Failed to parse draft MIME: {e}")
                return

            results = []
            errors = []

            # --- 3) Append each attachment (read bytes from blob or URL) ---
            for file_obj in files_to_attach:
                file_bytes, mime_type, file_name_or_error = self._read_file_bytes(file_obj)
                if isinstance(file_bytes, str):
                    # We returned an error string in file_bytes
                    err_msg = file_bytes
                    errors.append(err_msg)
                    yield self.create_text_message(err_msg)
                    continue

                # Determine attachment filename precedence
                # Prefer explicit attachment_name (if provided), else file's actual name
                attach_filename = attachment_name or file_name_or_error or "attachment"

                # Split MIME type
                maintype, subtype = (mime_type.split("/", 1) if mime_type and "/" in mime_type else ("application", "octet-stream"))

                try:
                    email_msg.add_attachment(file_bytes, maintype=maintype, subtype=subtype, filename=os.path.basename(attach_filename))
                    results.append({"attachment_name": os.path.basename(attach_filename), "mime_type": mime_type, "size": len(file_bytes)})
                    yield self.create_text_message(f"Prepared attachment '{os.path.basename(attach_filename)}' ({mime_type}).")
                except Exception as e:
                    err = f"Failed to add attachment '{attach_filename}': {e}"
                    errors.append(err)
                    yield self.create_text_message(err)

            if not results:
                yield self.create_text_message("No attachments were added.")
                return

            # --- 4) Encode updated message and PUT update ---
            try:
                updated_raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode("utf-8")
            except Exception as e:
                yield self.create_text_message(f"Failed to encode updated MIME: {e}")
                return

            update_url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"
            update_body = {
                "id": draft_id,
                "message": {
                    "raw": updated_raw
                }
            }
            upd = requests.put(update_url, headers=headers, json=update_body, timeout=60)
            if upd.status_code != 200:
                yield self.create_text_message(f"Failed to update draft: HTTP {upd.status_code} {upd.text}")
                return

            # Success summary
            yield self.create_text_message(f"Total {len(results)} attachment(s) added successfully to draft {draft_id}.")
            
            # Create specific output variable for workflow referencing
            yield self.create_variable_message("draft_id", draft_id)
            
            yield self.create_json_message({
                "status": "success",
                "draft_id": draft_id,
                "attachments_added": results,
                "errors": errors,
            })

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error adding attachment(s): {str(e)}")
            return

    # ------------------------
    # Helpers
    # ------------------------

    def _read_file_bytes(self, file_obj) -> tuple[Any, str | None, str | None]:
        """
        Returns (bytes_or_error, mime_type, filename_or_error_message).

        Supports Dify file objects passed as either attribute-style objects or dicts.
        Reads from .blob when present, otherwise downloads from .url / .remote_url.
        Enforces a 25MB per-file limit (Gmail practical attachment limit).
        """
        try:
            # Support both dict-like and attribute-like access
            def _get(attr: str):
                if isinstance(file_obj, dict):
                    return file_obj.get(attr)
                return getattr(file_obj, attr, None)

            blob = _get("blob")
            url = _get("url") or _get("remote_url")
            filename = _get("filename") or "attachment"
            extension = _get("extension")

            if extension and not str(filename).endswith(str(extension)):
                filename = f"{filename}{extension}"

            # Get bytes
            if blob is not None:
                content_bytes = blob.encode("utf-8") if isinstance(blob, str) else blob
            elif url:
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                content_bytes = r.content
            else:
                return ("No file content found (missing 'blob' and 'url').", None, None)

            file_size = len(content_bytes)
            if file_size > 25 * 1024 * 1024:
                return (f"File too large: {file_size} bytes. Maximum size is 25MB.", None, None)

            mime_type, _ = mimetypes.guess_type(str(filename))
            if not mime_type:
                mime_type = "application/octet-stream"

            return (content_bytes, mime_type, filename)

        except requests.RequestException as e:
            return (f"Failed to download file content: {e}", None, None)
        except Exception as e:
            return (f"Error processing file: {e}", None, None)
