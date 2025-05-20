from dify_plugin import Plugin, DifyPluginEnv

# Define the email plugin class that will extend the Plugin class
class EmailPlugin(Plugin):
    def __init__(self, env):
        super().__init__(env)
        
    def send_email(self, to, subject, body, cc=None, bcc=None):
        """
        Send an email without attachments (existing method)
        """
        # Existing implementation stays the same
        try:
            # Validate inputs
            if not to or not subject or not body:
                return {
                    "status": "error",
                    "message": "Recipients, subject, and body are required"
                }
                
            # Process recipients
            recipients = [r.strip() for r in to.split(',')] if isinstance(to, str) else to
            
            # Process CC recipients if provided
            cc_recipients = None
            if cc:
                cc_recipients = [r.strip() for r in cc.split(',')] if isinstance(cc, str) else cc
                
            # Process BCC recipients if provided
            bcc_recipients = None
            if bcc:
                bcc_recipients = [r.strip() for r in bcc.split(',')] if isinstance(bcc, str) else bcc
            
            # Get SMTP configuration
            smtp_config = self._get_smtp_config()
            
            # Import the send_mail module
            from .tools.send_mail import send_email
            
            # Call the implementation function
            result = send_email(
                to=recipients,
                subject=subject,
                body=body,
                cc=cc_recipients,
                bcc=bcc_recipients,
                smtp_config=smtp_config
            )
            
            return result
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": f"Failed to send email: {str(e)}",
                "details": traceback.format_exc()
            }
            
    def send_email_with_attachments(self, to, subject, body, attachments=None, cc=None, bcc=None):
        """
        Send an email with file attachments
        
        Args:
            to (str): Recipient email address(es), separated by commas for multiple recipients
            subject (str): Email subject
            body (str): Email body content (HTML supported)
            attachments (list, optional): List of file paths to attach
            cc (str, optional): Carbon copy recipients, separated by commas
            bcc (str, optional): Blind carbon copy recipients, separated by commas
            
        Returns:
            dict: Response containing status and message
        """
        try:
            # Validate inputs
            if not to or not subject or not body:
                return {
                    "status": "error",
                    "message": "Recipients, subject, and body are required"
                }
                
            # Process recipients
            recipients = [r.strip() for r in to.split(',')] if isinstance(to, str) else to
            
            # Process CC recipients if provided
            cc_recipients = None
            if cc:
                cc_recipients = [r.strip() for r in cc.split(',')] if isinstance(cc, str) else cc
                
            # Process BCC recipients if provided
            bcc_recipients = None
            if bcc:
                bcc_recipients = [r.strip() for r in bcc.split(',')] if isinstance(bcc, str) else bcc
            
            # Get SMTP configuration
            smtp_config = self._get_smtp_config()
            
            # Import the send_mail module
            from .tools.send_mail import send_email_with_attachments
            
            # Call the implementation function
            result = send_email_with_attachments(
                to=recipients,
                subject=subject,
                body=body,
                attachment_paths=attachments,
                cc=cc_recipients,
                bcc=bcc_recipients,
                smtp_config=smtp_config
            )
            
            return result
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": f"Failed to send email with attachments: {str(e)}",
                "details": traceback.format_exc()
            }
    
    def _get_smtp_config(self):
        """
        Get SMTP configuration from environment variables or settings
        """
        # This method likely already exists, but if not, implement it to get SMTP settings
        # Example implementation:
        return {
            'host': self.env.get('SMTP_HOST'),
            'port': self.env.get('SMTP_PORT'),
            'username': self.env.get('SMTP_USERNAME'),
            'password': self.env.get('SMTP_PASSWORD'),
            'use_tls': self.env.get('SMTP_USE_TLS', True),
            'from_email': self.env.get('SMTP_FROM_EMAIL'),
            'from_name': self.env.get('SMTP_FROM_NAME')
        }

# Create the plugin instance
plugin = EmailPlugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

# Run the plugin if this file is executed directly
if __name__ == '__main__':
    plugin.run()
