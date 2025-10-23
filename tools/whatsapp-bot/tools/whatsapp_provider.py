from dify_plugin.interfaces.tool import ToolProvider


class WhatsAppToolProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict):
        access_token = (credentials.get("access_token") or "").strip()
        phone_number_id = (credentials.get("phone_number_id") or "").strip()
        waba_id = (credentials.get("waba_id") or "").strip()

        if not access_token:
            raise ValueError("Missing access_token")
        if not phone_number_id:
            raise ValueError("Missing phone_number_id")
        if not waba_id:
            raise ValueError("Missing waba_id")

        return {
            "access_token": access_token, 
            "phone_number_id": phone_number_id,
            "waba_id": waba_id
        }


