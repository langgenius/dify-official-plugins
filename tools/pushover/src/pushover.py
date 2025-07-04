from typing import Annotated, Generator

from chump import Application as PushoverApplication
from dify_easy.model import (
    BasePlugin,
    Credential,
    CredentialType,
    FormType,
    MetaInfo,
    Param,
    ParamType,
    provider,
    tool,
)
from pydantic import BaseModel


class PushoverCredentials(BaseModel):
    api_token: Annotated[
        str,
        Credential(
            name="api_token",
            label="API Token",
            help="Your Pushover API Token",
            placeholder="Enter your Pushover API Token",
            url="https://pushover.net/apps",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""
    user_key: Annotated[
        str,
        Credential(
            name="user_key",
            label="User Key",
            help="Your Pushover User Key",
            placeholder="Enter your Pushover User Key",
            url="https://pushover.net/",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""


class PushoverPlugin(BasePlugin):

    credentials: PushoverCredentials = PushoverCredentials()

    @provider
    def verify(self):
        try:
            app = PushoverApplication(self.credentials.api_token)
            assert app.is_authenticated, "API Token is not valid"
            user = app.get_user(self.credentials.user_key)
            assert user.is_authenticated, "User Key is not valid"

        except Exception as e:
            raise ValueError(f"Verification failed: {str(e)}")

    @tool(
        name="get_devices",
        label="Get Devices",
        description="Get the list of devices associated with the Pushover user key",
    )
    def get_devices(self) -> Generator:

        app = PushoverApplication(self.credentials.api_token)
        user = app.get_user(self.credentials.user_key)
        devices: set[str] = user.devices

        yield list(devices)
        yield str(len(devices)) + " devices found: " + ", ".join(devices)

    @tool(
        name="send_message",
        label="Send Message",
        description="Send a message to the Pushover user key",
    )
    def send_message(
        self,
        message: Annotated[
            str,
            Param(
                name="message",
                label="Message",
                description="The message to send",
                llm_description="Message to send to the Pushover user",
                placeholder="Enter your message here",
                type=ParamType.string,
                required=True,
            ),
        ] = "Hello World!",
        title: Annotated[
            str,
            Param(
                name="title",
                label="Title",
                description="The title of the message",
                llm_description="Title of the message to send to the Pushover user",
                placeholder="Enter the title of the message",
                type=ParamType.string,
                required=True,
            ),
        ] = "Notification",
        device: Annotated[
            str,
            Param(
                name="device",
                label="Device",
                description="The device to send the message to (optional)",
                llm_description="Device to send the message to, if not specified, it will be sent to all devices",
                placeholder="Enter the device name (optional)",
                type=ParamType.string,
                required=False,
                form=FormType.llm,
            ),
        ] = "",
    ) -> Generator:

        app = PushoverApplication(self.credentials.api_token)
        user = app.get_user(self.credentials.user_key)

        if device:
            if device not in user.devices:
                raise ValueError(f"Device '{device}' not found in user's devices.")

            msg = user.send_message(message, title=title, device=device)
        else:
            msg = user.send_message(message, title=title)

        yield f"Successfully sent message: {str(msg)}"


plugin = PushoverPlugin(
    meta=MetaInfo(
        name="pushover",
        author="langgenius",
        description="Pushover plugin for sending notifications",
        version="0.0.1",
        label="Pushover",
        icon="icon.png",
    )
)
