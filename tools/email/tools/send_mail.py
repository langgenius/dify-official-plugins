import json
import re
from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from tools.markdown_utils import convert_markdown_to_html

from tools.send import SendEmailToolParameters, send_mail


class SendMailTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]

    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        sender = self.runtime.credentials.get("email_account", "")
        # Use sender_address if provided, otherwise fall back to email_account
        raw_sender_address = self.runtime.credentials.get("sender_address", "")
        sender_address = raw_sender_address or sender
        email_rgx = re.compile("^[a-zA-Z0-9._-]+@[a-zA-Z0-9_-]+(\\.[a-zA-Z0-9_-]+)+$")
        password = self.runtime.credentials.get("email_password", "")
        smtp_server = self.runtime.credentials.get("smtp_server", "")
        if not smtp_server:
            yield self.create_text_message("please input smtp server")
            return

        smtp_port = self.runtime.credentials.get("smtp_port", "")
        try:
            smtp_port = int(smtp_port)
        except ValueError:
            yield self.create_text_message("Invalid parameter smtp_port(should be int)")
            return
        
        if raw_sender_address:
            if not email_rgx.match(raw_sender_address):
                yield self.create_text_message("Invalid parameter sender_address(not a valid mailbox address)")
                return
        else:
            if not email_rgx.match(sender):
                yield self.create_text_message("Invalid parameter email_account(not a valid mailbox address) to skip this validation, configure sender_address")
                return

        receiver_email = tool_parameters.get("send_to", "")
        if not receiver_email:
            yield self.create_text_message("please input receiver email")
            return

        # Handle receiver email - can be single email or comma-separated list
        if isinstance(receiver_email, str):
            # Check if it's already JSON format
            if receiver_email.startswith('['):
                try:
                    receivers_list = json.loads(receiver_email)
                except json.JSONDecodeError:
                    yield self.create_text_message("Invalid JSON format for 'send_to' list")
                    return

            else:
                # Split by comma for comma-separated emails
                receivers_list = [e.strip() for e in receiver_email.split(',') if e.strip()]
        else:
            receivers_list = [receiver_email]

        for receiver in receivers_list:
            if not email_rgx.match(receiver):
                yield self.create_text_message(
                    f"Invalid parameter receiver email, the receiver email({receiver}) is not a mailbox"
                )
                return

        email_content = tool_parameters.get("email_content", "")
        if not email_content:
            yield self.create_text_message("please input email content")
            return

        subject = tool_parameters.get("subject", "")
        if not subject:
            yield self.create_text_message("please input email subject")
            return

        encrypt_method = self.runtime.credentials.get("encrypt_method", "")
        if not encrypt_method:
            yield self.create_text_message("please input encrypt method")
            return
        
        # Get reply-to address
        reply_to = tool_parameters.get("reply_to", None)
            
        # Process CC recipients
        cc_email = tool_parameters.get('cc', '')
        cc_email_list = []
        if cc_email:
            try:
                if cc_email.startswith('['):
                    cc_email_list = json.loads(cc_email)
                else:
                    cc_email_list = [e.strip() for e in cc_email.split(',') if e.strip()]
                for cc_email_item in cc_email_list:
                    if not email_rgx.match(cc_email_item):
                        yield self.create_text_message(
                            f"Invalid parameter cc email, the cc email({cc_email_item}) is not a mailbox"
                        )
                        return
            except json.JSONDecodeError:
                yield self.create_text_message("Invalid JSON format for CC list")
                return
                
        # Process BCC recipients
        bcc_email = tool_parameters.get('bcc', '')
        bcc_email_list = []
        if bcc_email:
            try:
                if bcc_email.startswith('['):
                    bcc_email_list = json.loads(bcc_email)
                else:
                    bcc_email_list = [e.strip() for e in bcc_email.split(',') if e.strip()]
                for bcc_email_item in bcc_email_list:
                    if not email_rgx.match(bcc_email_item):
                        yield self.create_text_message(
                            f"Invalid parameter bcc email, the bcc email({bcc_email_item}) is not a mailbox"
                        )
                        return
            except json.JSONDecodeError:
                yield self.create_text_message("Invalid JSON format for BCC list")
                return
        
        # Check if markdown to HTML conversion is requested
        convert_to_html = tool_parameters.get("convert_to_html", False)
        
        # Store original plain text content before any conversion
        plain_text_content = email_content
        
        if convert_to_html:
            # Convert content to HTML using shared utility
            email_content, plain_text_content = convert_markdown_to_html(email_content)
        
        # Get attachments from parameters (if any)
        attachments = tool_parameters.get("attachments", None)
        
        # Convert single attachment to list if needed
        if attachments is not None and not isinstance(attachments, list):
            attachments = [attachments]


        send_email_params = SendEmailToolParameters(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            email_account=sender,
            email_password=password,
            sender_address=sender_address,
            sender_to=receivers_list,
            subject=subject,
            email_content=email_content,
            plain_text_content=plain_text_content if convert_to_html else None,
            encrypt_method=encrypt_method,
            is_html=convert_to_html,
            attachments=attachments,
            cc_recipients=cc_email_list,
            bcc_recipients=bcc_email_list,
            reply_to_address=reply_to
        )
        
        # Initialize response message for all recipients
        msg = {}
        for receiver in receivers_list + cc_email_list + bcc_email_list:
            msg[receiver] = "send email success"
            
        # Send the email and get result
        try:
            result = send_mail(send_email_params)
        except Exception as e:
            yield self.create_text_message(f"Failed to send email: {e}")
            return
        
        # Process any error results
        if result:
            for key, (integer_value, bytes_value) in result.items():
                msg[key] = f"send email failed: {integer_value} {bytes_value.decode('utf-8')}"
                
        # Add attachment information to the response
        response_text = json.dumps(msg, indent=2)
        if attachments:
            attachment_info = f"Email sent with {len(attachments)} attachment(s)"
            yield self.create_text_message(f"{attachment_info}. Details: {response_text}")
        else:
            yield self.create_text_message(response_text)


# Legacy function kept for backward compatibility
def send_email_with_attachments(to, subject, body, attachment_paths=None, cc=None, bcc=None, smtp_config=None):
    """
    Send an email with attachments using SMTP (Legacy function - deprecated)
    
    Args:
        to (str or list): Recipient email address(es)
        subject (str): Email subject
        body (str): Email body content (HTML supported)
        attachment_paths (list): List of file paths to attach
        cc (str or list, optional): Carbon copy recipients
        bcc (str or list, optional): Blind carbon copy recipients
        smtp_config (dict, optional): SMTP configuration override
        
    Returns:
        dict: Status and message information
    """
    import os
    import smtplib
    import mimetypes
    import logging
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    from email.mime.audio import MIMEAudio
    from email.mime.base import MIMEBase
    from email import encoders
    from email.utils import formataddr
    
    try:
        # Create message
        message = MIMEMultipart()
        message['Subject'] = subject
        
        # Handle multiple recipients
        if isinstance(to, list):
            message['To'] = ', '.join(to)
        else:
            message['To'] = to
            
        # Add CC if provided    
        if cc:
            if isinstance(cc, list):
                message['Cc'] = ', '.join(cc)
            else:
                message['Cc'] = cc
                
        # Add BCC if provided
        if bcc:
            if isinstance(bcc, list):
                message['Bcc'] = ', '.join(bcc)
            else:
                message['Bcc'] = bcc
        
        # Add From with proper formatting
        if smtp_config and smtp_config.get('from_name') and smtp_config.get('from_email'):
            message['From'] = formataddr((smtp_config['from_name'], smtp_config['from_email']))
        elif smtp_config and smtp_config.get('from_email'):
            message['From'] = smtp_config['from_email']
        
        # Attach the body
        message.attach(MIMEText(body, 'html'))
        
        # Process attachments if provided
        successful_attachments = []
        failed_attachments = []
        
        if attachment_paths and isinstance(attachment_paths, list):
            for file_path in attachment_paths:
                try:
                    # Verify file exists
                    if not os.path.exists(file_path):
                        logging.warning(f"File not found: {file_path}")
                        failed_attachments.append({
                            "path": file_path,
                            "error": "File not found"
                        })
                        continue
                    
                    # Check file size (limit to 25MB)
                    file_size = os.path.getsize(file_path)
                    if file_size > 25 * 1024 * 1024:  # 25MB in bytes
                        logging.warning(f"File too large: {file_path} ({file_size / (1024*1024):.2f} MB)")
                        failed_attachments.append({
                            "path": file_path,
                            "error": f"File too large: {file_size / (1024*1024):.2f} MB"
                        })
                        continue
                    
                    # Get filename and determine content type
                    filename = os.path.basename(file_path)
                    content_type, encoding = mimetypes.guess_type(file_path)
                    
                    if content_type is None or encoding is not None:
                        # Default to binary if type can't be guessed
                        content_type = 'application/octet-stream'
                    
                    main_type, sub_type = content_type.split('/', 1)
                    
                    # Handle different file types appropriately
                    if main_type == 'text':
                        with open(file_path, 'r', encoding='utf-8') as fp:
                            attach = MIMEText(fp.read(), _subtype=sub_type)
                            
                    elif main_type == 'image':
                        with open(file_path, 'rb') as fp:
                            attach = MIMEImage(fp.read(), _subtype=sub_type)
                            
                    elif main_type == 'audio':
                        with open(file_path, 'rb') as fp:
                            attach = MIMEAudio(fp.read(), _subtype=sub_type)
                            
                    else:
                        # Default handling for other file types
                        with open(file_path, 'rb') as fp:
                            attach = MIMEBase(main_type, sub_type)
                            attach.set_payload(fp.read())
                        encoders.encode_base64(attach)
                    
                    # Add header for attachment with filename
                    attach.add_header('Content-Disposition', 'attachment', filename=filename)
                    message.attach(attach)
                    successful_attachments.append(filename)
                    logging.info(f"Successfully attached: {filename}")
                    
                except Exception as attachment_error:
                    logging.error(f"Error attaching file {file_path}: {str(attachment_error)}")
                    failed_attachments.append({
                        "path": file_path,
                        "error": str(attachment_error)
                    })
        
        # Connect to SMTP server and send
        if not smtp_config:
            return {
                "status": "error",
                "message": "SMTP configuration is required"
            }
        
        # Get SMTP server details
        smtp_host = smtp_config.get('host')
        smtp_port = int(smtp_config.get('port', 587))
        smtp_username = smtp_config.get('username')
        smtp_password = smtp_config.get('password')
        use_tls = smtp_config.get('use_tls', True)
        
        # Connect to server
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            
            # Login if credentials provided
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            
            # Get all recipients
            all_recipients = []
            if isinstance(to, list):
                all_recipients.extend(to)
            else:
                all_recipients.append(to)
                
            if cc:
                if isinstance(cc, list):
                    all_recipients.extend(cc)
                else:
                    all_recipients.append(cc)
                    
            if bcc:
                if isinstance(bcc, list):
                    all_recipients.extend(bcc)
                else:
                    all_recipients.append(bcc)
            
            # Send email
            from_email = smtp_config.get('from_email', smtp_username)
            server.sendmail(from_email, all_recipients, message.as_string())
        
        # Return success with status on attachments
        result = {
            "status": "success",
            "message": "Email sent successfully"
        }
        
        if successful_attachments:
            result["attachments"] = {
                "successful": successful_attachments
            }
            
        if failed_attachments:
            if "attachments" not in result:
                result["attachments"] = {}
            result["attachments"]["failed"] = failed_attachments
            
        return result
        
    except Exception as e:
        import traceback
        logging.error(f"Failed to send email: {str(e)}")
        logging.error(traceback.format_exc())
        
        return {
            "status": "error",
            "message": f"Failed to send email: {str(e)}"
        }
