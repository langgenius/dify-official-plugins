def send_email_with_attachments(to, subject, body, attachment_paths=None, cc=None, bcc=None, smtp_config=None):
    """
    Send an email with attachments using SMTP
    
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
