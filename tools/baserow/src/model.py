import inspect
from enum import Enum
from typing import Callable

from pydantic import BaseModel, Field

PROVIDER_MARKER_ATTR = "_provider_function"
TOOL_MARKER_ATTR = "_tool_function"


def short_name_field():
    return Field(
        pattern=r"^[a-z0-9_-]{1,64}$",
        description="Alphanumeric characters and underscores only.",
    )


def provider(func):
    setattr(func, PROVIDER_MARKER_ATTR, True)
    return func


class Tool(BaseModel):
    name: str = short_name_field()
    label: str = name
    description: str = ""  # Automatically generated llm_description
    required: bool = True


def tool(_func=None, *, name=None, label=None, description=None):
    def decorator(func):
        setattr(func, TOOL_MARKER_ATTR, True)
        if name:
            setattr(func, "tool_name", name)
        if label:
            setattr(func, "tool_label", label)
        if description:
            setattr(func, "tool_description", description)
        return func

    if _func is None:
        return decorator
    else:
        return decorator(_func)


class ParamType(str, Enum):
    string: str = "string"
    number: str = "number"


class FormType(str, Enum):
    llm: str = "llm"
    schema: str = "schema"


class Param(BaseModel):
    name: str = short_name_field()
    label: str = str(name)
    description: str = ""
    llm_description: str = description  # TODO: Automatically generated llm_description
    type: ParamType = ParamType.string

    required: bool = True
    form: FormType = FormType.llm


class CredentialType(str, Enum):
    secret_input: str = "secret-input"
    text_input: str = "text-input"


class Credential:
    def __init__(
        self,
        name: str,
        label: str = None,
        placeholder: str = None,
        help: str = "",
        url: str = "",
        type: CredentialType = CredentialType.secret_input,
        required: bool = True,
    ):
        self.name = name
        self.label = label or name
        self.placeholder = placeholder or name
        self.help = help
        self.url = url
        self.type = type
        self.required = required


class MetaInfo(BaseModel):
    name: str = short_name_field()
    author: str = short_name_field()
    version: str = "0.0.1"

    label: str = str(name)
    description: str

    icon: str = "icon.png"


class BasePlugin(BaseModel):

    meta: MetaInfo = None
    credentials: BaseModel = None

    def find_decorated_methods(self, marker_attr):
        decorated_methods: dict[str, Callable] = {}

        for name, member in inspect.getmembers(self):
            if callable(member):
                if getattr(member, marker_attr, False):
                    decorated_methods[name] = member

        return decorated_methods
