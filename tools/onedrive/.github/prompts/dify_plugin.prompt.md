# Prompt for Dify Plugin Tool Development

You are a senior developer that can help me with developing Dify Plugin Tool, which is an AI Agent Tool that can be used on AI Agent Development Tool, Dify. You are going to follow the instruction below to help me build a Plugin Tool called {     }. The author of this tool is {     }. This Tool should have the functionality of {     }. Make sure you are editing upon the existing project folder: {     } and file structure. Most importantly, the yaml file’s indentation and formatting should strictly follow the examples of yaml file. Once the plugin tool is ready, set up venv and install all the requirements under the plugin directory. You should only change the file the instruction told you to change. Don’t change anything else, for example the env.example file.

Before you applying anything, I want you to {read the documentation of the API access of the tool}/{understand what’s the functionality of the tool, what’s the input of the tool, what functionality does it have, and what output do we take}.

The scaffold of Dify Plugin Tool is listed below, and you should follow the following instruction to help me build the tool.

`your_plugin/
├── _assets/                  # Directory for visual assets used in marketplace listings
│   └── icon.svg             # Plugin icon displayed in the Dify marketplace UI
│
├── provider/                 # Authentication configuration and validation
│   ├── your_plugin.py       # Class that inherits from ToolProvider; validates credentials
│   └── your_plugin.yaml     # Configures auth UI fields, labels, and help text
│
├── tools/                    # Tool implementation files
│   ├── your_plugin.py       # Class that inherits from Tool; implements API functionality
│   └── your_plugin.yaml     # Defines tool parameters, descriptions, and UI elements
│
├── .diftyignore              # Lists files to exclude when publishing to marketplace
│
├── .env.example              # Template for environment variables needed for testing
│                            # Contains REMOTE_INSTALL_KEY placeholder
│
├── .gitignore                # Standard Git ignore file for version control
│
├── [GUIDE.md](http://guide.md/)                  # Detailed usage instructions shown to users in marketplace
│
├── [main.py](http://main.py/)                   # Entry point for local testing via python -m main test
│                            # Generally shouldn't be modified
│
├── manifest.yaml             # Core metadata for marketplace listing:
│                            # - Version number
│                            # - Compatibility info
│                            # - Plugin capabilities
│                            # - Marketplace categorization
│
├── [PRIVACY.md](http://privacy.md/)                # Privacy policy displayed in marketplace
│
├── [README.md](http://readme.md/)                 # General documentation and overview for developers
│
└── requirements.txt          # Python package dependencies required by the plugin`

# 1. How to edit manifest.yaml

You're tasked with creating the manifest.yaml file for a Dify plugin. This file is the central configuration file that describes your entire plugin for the Dify Marketplace. I'll guide you through creating this file, explaining which parts affect your plugin's appearance in the Marketplace.

## File Purpose

The manifest.yaml file serves as the main configuration file for your plugin, defining:

- Basic plugin information displayed in the Marketplace
- Version and resource requirements
- Permissions needed by your plugin
- References to your tool providers

## Example Implementation (Dropbox)

Here's how the manifest.yaml file for a Dropbox tool looks:

```yaml
version: 0.0.1
type: plugin
author: langgenius
name: dropbox
label:
  en_US: Dropbox
  ja_JP: Dropbox
  zh_Hans: Dropbox
  pt_BR: Dropbox
  zh_Hant: Dropbox
description:
  en_US: Interact with Dropbox files and folders. Allows listing, searching, uploading, downloading, and managing files.
  ja_JP: Dropbox のファイルとフォルダを操作します。ファイルの一覧表示、検索、アップロード、ダウンロード、管理が可能です。
  zh_Hans: 与 Dropbox 文件和文件夹交互。允许列出、搜索、上传、下载和管理文件。
  pt_BR: Interaja com arquivos e pastas do Dropbox. Permite listar, pesquisar, fazer upload, download e gerenciar arquivos.
  zh_Hant: 與 Dropbox 檔案和資料夾互動。可列出、搜尋、上傳、下載以及管理檔案。
icon: icon.svg
resource:
  memory: 268435456
  permission:
    tool:
      enabled: true
    model:
      enabled: true
      llm: true
      text_embedding: false
      rerank: false
      tts: false
      speech2text: false
      moderation: false
    storage:
      enabled: true
      size: 1048576
plugins:
  tools:
    - provider/dropbox.yaml
meta:
  version: 0.0.1
  arch:
    - amd64
    - arm64
  runner:
    language: python
    version: "3.12"
    entrypoint: main
created_at: 2025-04-03T17:41:08.159756+08:00
privacy: PRIVACY.md
```

## Key Components Affecting Marketplace Display

1. **Basic Information** (shown in the plugin listing):
    - `version`: Your plugin's version number
    - `author`: Your organization name shown in the Marketplace
    - `name`: Internal name for your plugin
    - `label`: Display name in different languages
    - `created_at`: Creation time in RFC3339 format (must be in the past)
    - `icon`: Path to your plugin icon
    - `description`: Full description in different languages
    - `tags`: Categories for your plugin. You can only set one tag at a time. (Now tags only have search', 'image', 'videos', 'weather', 'finance', 'design', 'travel', 'social', 'news', 'medical', 'productivity', 'education', 'business', 'entertainment', 'utilities' or 'other’)
2. **Resource Requirements** (shown in the requirements section):
    - `resource.memory`: Maximum memory usage in bytes (e.g., 1048576 = 1MB)
    - `resource.permission`: Required permissions for your plugin
3. **Plugin References**:
    - `plugins.tools`: Path to your provider YAML file(s)

## Marketplace Impact

Looking at the Marketplace screenshot you provided, you can see how these fields appear:

- The plugin name, icon, and description appear at the top
- The author name and version number are shown below the description
- Tags appear in the "TAGS" section
- Memory requirements show in the "REQUIREMENTS" section

## Important Notes

1. Most fields can be left as initially configured in the template, especially:
    - `type`: Keep as "plugin"
    - `meta` section: Keep the default values
    - `resource.permission`: Only change if your plugin needs specific permissions
2. Fields you should customize:
    - `version`: Your plugin's version number
    - `author`: Your organization name
    - `name`: A unique identifier for your plugin
    - `label`: The display name in different languages
    - `description`: A clear description of what your plugin does
    - `tags`: Relevant categories for your plugin
    - `plugins.tools`: Path to your provider YAML file(s)

To create your own manifest.yaml file, start with the template and customize the fields that affect how your plugin appears in the Marketplace. The key is to provide clear, concise information that helps users understand what your plugin does. However, with all these being said, you should always leave manifest file as it be, as everything is setup while initializing.

# 2. How to edit provider/your_plugin.yaml

You're tasked with creating the provider configuration YAML file for a Dify plugin. This file defines the credentials required for your service and how they're presented in the Dify UI. I'll guide you through creating this file step by step, using Google Search as an example.

## File Purpose

The provider YAML file (`your_plugin.yaml`) defines:

- What credentials users need to provide to use your service
- How these credentials are collected and displayed in the UI
- Which tools are included in your plugin
- The Python file that validates these credentials

## Required Components

1. **identity section**: Basic metadata for your plugin (required but won't affect Marketplace appearance)
2. **credentials_for_provider section**: Defines what authentication credentials users need to provide
3. **tools section**: Lists which tool configuration files are included
4. **extra section**: Specifies the Python file used for credential validation

## Example Implementation

Here's how the provider YAML file for Dropbox tool looks:

```yaml
identity:
  author: lcandy
  name: dropbox
  label:
    en_US: Dropbox
    zh_Hans: Dropbox
    pt_BR: Dropbox
    ja_JP: Dropbox
    zh_Hant: Dropbox
  description:
    en_US: Interact with Dropbox files and folders
    zh_Hans: 与 Dropbox 文件和文件夹交互
    pt_BR: Interaja com arquivos e pastas do Dropbox
    ja_JP: Dropbox のファイルとフォルダを操作します
    zh_Hant: 與 Dropbox 檔案和資料夾互動
  icon: icon.svg
credentials_for_provider:
  access_token:
    type: secret-input
    required: true
    label:
      en_US: Access Token
      zh_Hans: 访问令牌
      pt_BR: Token de Acesso
      ja_JP: アクセストークン
      zh_Hant: 存取權杖
    placeholder:
      en_US: Please input your Dropbox access token
      zh_Hans: 请输入您的 Dropbox 访问令牌
      pt_BR: Por favor, insira seu token de acesso do Dropbox
      ja_JP: Dropbox アクセストークンを入力してください
      zh_Hant: 請輸入您的 Dropbox 存取權杖
    help:
      en_US: Get your access token from Dropbox App Console
      zh_Hans: 从 Dropbox 应用控制台获取您的访问令牌
      pt_BR: Obtenha seu token de acesso no Console de Aplicativos do Dropbox
      ja_JP: Dropbox アプリコンソールからアクセストークンを取得してください
      zh_Hant: 請從 Dropbox 應用程式主控台取得您的存取權杖
    url: https://www.dropbox.com/developers/apps
tools:
  - tools/list_files.yaml
  - tools/search_files.yaml
  - tools/upload_file.yaml
  - tools/download_file.yaml
  - tools/create_folder.yaml
  - tools/delete_file.yaml
extra:
  python:
    source: provider/dropbox.py

```

## Key Points to Remember

1. **Identity Section**: Though it doesn't affect the Marketplace, it's still required in the file structure. Include basic information like name, author, and description. The tags should inherit from the manifest.yaml file.
2. **Credentials Section**:
    - Each credential needs a unique identifier (like dropbox access token)
    - `type` options:
        - `secret-input`: For sensitive information that will be encrypted
        - `text-input`: For regular text information
        - `select`: For dropdown selection
        - `boolean`: For toggle switches
        - `tool-selector`: For tool configuration objects
    - Include `required: true/false` to indicate if the credential is mandatory
    - Provide user-friendly labels, placeholders, and help text in different languages
    - The `url` field links to documentation for obtaining credentials
3. **Tools Section**:
    - Lists the YAML files for each tool in your plugin
    - Paths should be relative to the plugin root
4. **Extra Section**:
    - Specifies the Python file that validates the credentials
    - This file should match the one created in your "provider/your_plugin.py"

## Creating Your YAML File

To adapt this for your own service:

1. Modify the identity section with your basic plugin information
2. Define what credentials your service requires in the credentials_for_provider section
3. List your tool YAML files in the tools section
4. Specify your Python validation file in the extra section

Remember that this YAML file works in conjunction with your Python validation file, which will use these credentials to authenticate with your service.

# 3. How to edit provider/your_plugin.py

You're tasked with creating the provider authentication file for a Dify plugin. This file will validate the credentials needed to access a third-party service. I'll guide you through creating this file, using Google Search API integration as an example.

## File Purpose

The provider Python file (`provider_name.py`) serves as the authentication testing module for your Dify plugin. Its primary responsibility is to test whether the credentials provided by users are valid by making a simple API call to the service.

## Required Components

1. Your provider class **must** inherit from `dify_plugin.ToolProvider`
2. You **must** implement the `_validate_credentials` method
3. You **must** use `ToolProviderCredentialValidationError` for error handling

## How It Works

The authentication flow follows these steps:

1. User enters their credentials in the Dify UI
2. Dify passes these credentials to your `_validate_credentials` method
3. Your code attempts a simple API call using the provided credentials
4. If successful, authentication is valid; if not, you raise an error

## Example Implementation

Here's how you would implement a provider file for Dropbox tool

```python
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
import dropbox
from dropbox.exceptions import AuthError

from dropbox_utils import DropboxUtils

class DropboxProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check if access_token is provided in credentials
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("Dropbox access token is required.")

            # Try to authenticate with Dropbox using the access token
            try:
                # Use the utility function to get a client
                DropboxUtils.get_client(credentials.get("access_token"))
            except AuthError as e:
                raise ToolProviderCredentialValidationError(f"Invalid Dropbox access token: {str(e)}")
            except Exception as e:
                raise ToolProviderCredentialValidationError(f"Failed to connect to Dropbox: {str(e)}")

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
```

## Key Points to Remember

1. **Always use the tool class**: The provider doesn't make API calls directly. Instead, it uses the tool class through the `from_credentials` method.
2. **Use a minimal test query**: Keep your validation test simple - just enough to confirm the credentials work.
3. **Proper error handling**: Always wrap your validation in a try/except block and convert any exceptions to the standard `ToolProviderCredentialValidationError`.
4. **Generic credentials dictionary**: The `credentials` parameter contains all the authentication parameters defined in your `provider_name.yaml` file.
5. **Generator handling**: Note the `for _ in ...` syntax used to handle the generator returned by the `invoke` method.

# 4. How to edit tools/your_plugin.yaml

You're tasked with creating the tool configuration YAML file for a Dify plugin. This file defines how your tool appears in the Dify interface, what parameters it accepts, and how these parameters are presented to both users and the AI agent. I'll guide you through creating this file, using Google Search as an example.

**Yaml Schema of tools/your_plugin.yaml:**

```python
import base64
import contextlib
import uuid
from collections.abc import Mapping
from enum import Enum, StrEnum
from typing import Any, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from dify_plugin.core.utils.yaml_loader import load_yaml_file
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model.message import PromptMessageTool

class LogMetadata(str, Enum):
    STARTED_AT = "started_at"
    FINISHED_AT = "finished_at"
    ELAPSED_TIME = "elapsed_time"
    TOTAL_PRICE = "total_price"
    TOTAL_TOKENS = "total_tokens"
    PROVIDER = "provider"
    CURRENCY = "currency"

class CommonParameterType(Enum):
    SECRET_INPUT = "secret-input"
    TEXT_INPUT = "text-input"
    SELECT = "select"
    STRING = "string"
    NUMBER = "number"
    FILE = "file"
    FILES = "files"
    BOOLEAN = "boolean"
    APP_SELECTOR = "app-selector"
    MODEL_SELECTOR = "model-selector"
    # TOOL_SELECTOR = "tool-selector"
    TOOLS_SELECTOR = "array[tools]"

class AppSelectorScope(Enum):
    ALL = "all"
    CHAT = "chat"
    WORKFLOW = "workflow"
    COMPLETION = "completion"

class ModelConfigScope(Enum):
    LLM = "llm"
    TEXT_EMBEDDING = "text-embedding"
    RERANK = "rerank"
    TTS = "tts"
    SPEECH2TEXT = "speech2text"
    MODERATION = "moderation"
    VISION = "vision"

class ToolSelectorScope(Enum):
    ALL = "all"
    PLUGIN = "plugin"
    API = "api"
    WORKFLOW = "workflow"

class ToolRuntime(BaseModel):
    credentials: dict[str, Any]
    user_id: Optional[str]
    session_id: Optional[str]

class ToolInvokeMessage(BaseModel):
    class TextMessage(BaseModel):
        text: str

        def to_dict(self):
            return {"text": self.text}

    class JsonMessage(BaseModel):
        json_object: dict

        def to_dict(self):
            return {"json_object": self.json_object}

    class BlobMessage(BaseModel):
        blob: bytes

    class BlobChunkMessage(BaseModel):
        id: str = Field(..., description="The id of the blob")
        sequence: int = Field(..., description="The sequence of the chunk")
        total_length: int = Field(..., description="The total length of the blob")
        blob: bytes = Field(..., description="The blob data of the chunk")
        end: bool = Field(..., description="Whether the chunk is the last chunk")

    class VariableMessage(BaseModel):
        variable_name: str = Field(
            ...,
            description="The name of the variable, only supports root-level variables",
        )
        variable_value: Any = Field(..., description="The value of the variable")
        stream: bool = Field(default=False, description="Whether the variable is streamed")

        @model_validator(mode="before")
        @classmethod
        def validate_variable_value_and_stream(cls, values):
            # skip validation if values is not a dict
            if not isinstance(values, dict):
                return values

            if values.get("stream") and not isinstance(values.get("variable_value"), str):
                raise ValueError("When 'stream' is True, 'variable_value' must be a string.")
            return values

    class LogMessage(BaseModel):
        class LogStatus(Enum):
            START = "start"
            ERROR = "error"
            SUCCESS = "success"

        id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="The id of the log")
        label: str = Field(..., description="The label of the log")
        parent_id: Optional[str] = Field(default=None, description="Leave empty for root log")
        error: Optional[str] = Field(default=None, description="The error message")
        status: LogStatus = Field(..., description="The status of the log")
        data: Mapping[str, Any] = Field(..., description="Detailed log data")
        metadata: Optional[Mapping[LogMetadata, Any]] = Field(default=None, description="The metadata of the log")

    class MessageType(Enum):
        TEXT = "text"
        FILE = "file"
        BLOB = "blob"
        JSON = "json"
        LINK = "link"
        IMAGE = "image"
        IMAGE_LINK = "image_link"
        VARIABLE = "variable"
        BLOB_CHUNK = "blob_chunk"
        LOG = "log"

    type: MessageType
    # TODO: pydantic will validate and construct the message one by one, until it encounters a correct type
    # we need to optimize the construction process
    message: TextMessage | JsonMessage | VariableMessage | BlobMessage | BlobChunkMessage | LogMessage | None
    meta: Optional[dict] = None

    @field_validator("message", mode="before")
    @classmethod
    def decode_blob_message(cls, v):
        if isinstance(v, dict) and "blob" in v:
            with contextlib.suppress(Exception):
                v["blob"] = base64.b64decode(v["blob"])
        return v

    @field_serializer("message")
    def serialize_message(self, v):
        if isinstance(v, self.BlobMessage):
            return {"blob": base64.b64encode(v.blob).decode("utf-8")}
        elif isinstance(v, self.BlobChunkMessage):
            return {
                "id": v.id,
                "sequence": v.sequence,
                "total_length": v.total_length,
                "blob": base64.b64encode(v.blob).decode("utf-8"),
                "end": v.end,
            }
        return v

class ToolIdentity(BaseModel):
    author: str = Field(..., description="The author of the tool")
    name: str = Field(..., description="The name of the tool")
    label: I18nObject = Field(..., description="The label of the tool")

class ToolParameterOption(BaseModel):
    value: str = Field(..., description="The value of the option")
    label: I18nObject = Field(..., description="The label of the option")

    @field_validator("value", mode="before")
    @classmethod
    def transform_id_to_str(cls, value) -> str:
        if not isinstance(value, str):
            return str(value)
        else:
            return value

class ParameterAutoGenerate(BaseModel):
    class Type(StrEnum):
        PROMPT_INSTRUCTION = "prompt_instruction"

    type: Type

class ParameterTemplate(BaseModel):
    enabled: bool = Field(..., description="Whether the parameter is jinja enabled")

class ToolParameter(BaseModel):
    class ToolParameterType(str, Enum):
        STRING = CommonParameterType.STRING.value
        NUMBER = CommonParameterType.NUMBER.value
        BOOLEAN = CommonParameterType.BOOLEAN.value
        SELECT = CommonParameterType.SELECT.value
        SECRET_INPUT = CommonParameterType.SECRET_INPUT.value
        FILE = CommonParameterType.FILE.value
        FILES = CommonParameterType.FILES.value
        MODEL_SELECTOR = CommonParameterType.MODEL_SELECTOR.value
        APP_SELECTOR = CommonParameterType.APP_SELECTOR.value
        # TOOL_SELECTOR = CommonParameterType.TOOL_SELECTOR.value

    class ToolParameterForm(Enum):
        SCHEMA = "schema"  # should be set while adding tool
        FORM = "form"  # should be set before invoking tool
        LLM = "llm"  # will be set by LLM

    name: str = Field(..., description="The name of the parameter")
    label: I18nObject = Field(..., description="The label presented to the user")
    human_description: I18nObject = Field(..., description="The description presented to the user")
    type: ToolParameterType = Field(..., description="The type of the parameter")
    auto_generate: Optional[ParameterAutoGenerate] = Field(
        default=None, description="The auto generate of the parameter"
    )
    template: Optional[ParameterTemplate] = Field(default=None, description="The template of the parameter")
    scope: str | None = None
    form: ToolParameterForm = Field(..., description="The form of the parameter, schema/form/llm")
    llm_description: Optional[str] = None
    required: Optional[bool] = False
    default: Optional[Union[int, float, str]] = None
    min: Optional[Union[float, int]] = None
    max: Optional[Union[float, int]] = None
    precision: Optional[int] = None
    options: Optional[list[ToolParameterOption]] = None

class ToolDescription(BaseModel):
    human: I18nObject = Field(..., description="The description presented to the user")
    llm: str = Field(..., description="The description presented to the LLM")

class ToolConfigurationExtra(BaseModel):
    class Python(BaseModel):
        source: str

    python: Python

class ToolConfiguration(BaseModel):
    identity: ToolIdentity
    parameters: list[ToolParameter] = Field(default=[], description="The parameters of the tool")
    description: ToolDescription
    extra: ToolConfigurationExtra
    has_runtime_parameters: bool = Field(default=False, description="Whether the tool has runtime parameters")
    output_schema: Optional[Mapping[str, Any]] = None

class ToolLabelEnum(Enum):
    SEARCH = "search"
    IMAGE = "image"
    VIDEOS = "videos"
    WEATHER = "weather"
    FINANCE = "finance"
    DESIGN = "design"
    TRAVEL = "travel"
    SOCIAL = "social"
    NEWS = "news"
    MEDICAL = "medical"
    PRODUCTIVITY = "productivity"
    EDUCATION = "education"
    BUSINESS = "business"
    ENTERTAINMENT = "entertainment"
    UTILITIES = "utilities"
    OTHER = "other"

class ToolCredentialsOption(BaseModel):
    value: str = Field(..., description="The value of the option")
    label: I18nObject = Field(..., description="The label of the option")

class ProviderConfig(BaseModel):
    class Config(Enum):
        SECRET_INPUT = CommonParameterType.SECRET_INPUT.value
        TEXT_INPUT = CommonParameterType.TEXT_INPUT.value
        SELECT = CommonParameterType.SELECT.value
        BOOLEAN = CommonParameterType.BOOLEAN.value
        MODEL_SELECTOR = CommonParameterType.MODEL_SELECTOR.value
        APP_SELECTOR = CommonParameterType.APP_SELECTOR.value
        # TOOL_SELECTOR = CommonParameterType.TOOL_SELECTOR.value
        TOOLS_SELECTOR = CommonParameterType.TOOLS_SELECTOR.value

        @classmethod
        def value_of(cls, value: str) -> "ProviderConfig.Config":
            """
            Get value of given mode.

            :param value: mode value
            :return: mode
            """
            for mode in cls:
                if mode.value == value:
                    return mode
            raise ValueError(f"invalid mode value {value}")

    name: str = Field(..., description="The name of the credentials")
    type: Config = Field(..., description="The type of the credentials")
    scope: str | None = None
    required: bool = False
    default: Optional[Union[int, float, str]] = None
    options: Optional[list[ToolCredentialsOption]] = None
    label: I18nObject
    help: Optional[I18nObject] = None
    url: Optional[str] = None
    placeholder: Optional[I18nObject] = None

class ToolProviderIdentity(BaseModel):
    author: str = Field(..., description="The author of the tool")
    name: str = Field(..., description="The name of the tool")
    description: I18nObject = Field(..., description="The description of the tool")
    icon: str = Field(..., description="The icon of the tool")
    label: I18nObject = Field(..., description="The label of the tool")
    tags: list[ToolLabelEnum] = Field(
        default=[],
        description="The tags of the tool",
    )

class ToolProviderConfigurationExtra(BaseModel):
    class Python(BaseModel):
        source: str

    python: Python

class ToolProviderConfiguration(BaseModel):
    identity: ToolProviderIdentity
    credentials_schema: list[ProviderConfig] = Field(
        default_factory=list,
        alias="credentials_for_provider",
        description="The credentials schema of the tool provider",
    )
    tools: list[ToolConfiguration] = Field(default=[], description="The tools of the tool provider")
    extra: ToolProviderConfigurationExtra

    @model_validator(mode="before")
    @classmethod
    def validate_credentials_schema(cls, data: dict) -> dict:
        original_credentials_for_provider: dict[str, dict] = data.get("credentials_for_provider", {})

        credentials_for_provider: list[dict[str, Any]] = []
        for name, credential in original_credentials_for_provider.items():
            credential["name"] = name
            credentials_for_provider.append(credential)

        data["credentials_for_provider"] = credentials_for_provider
        return data

    @field_validator("tools", mode="before")
    @classmethod
    def validate_tools(cls, value) -> list[ToolConfiguration]:
        if not isinstance(value, list):
            raise ValueError("tools should be a list")

        tools: list[ToolConfiguration] = []

        for tool in value:
            # read from yaml
            if not isinstance(tool, str):
                raise ValueError("tool path should be a string")
            try:
                file = load_yaml_file(tool)
                tools.append(
                    ToolConfiguration(
                        identity=ToolIdentity(**file["identity"]),
                        parameters=[ToolParameter(**param) for param in file.get("parameters", []) or []],
                        description=ToolDescription(**file["description"]),
                        extra=ToolConfigurationExtra(**file.get("extra", {})),
                        output_schema=file.get("output_schema", None),
                    )
                )
            except Exception as e:
                raise ValueError(f"Error loading tool configuration: {str(e)}") from e

        return tools

class ToolProviderType(Enum):
    """
    Enum class for tool provider
    """

    BUILT_IN = "builtin"
    WORKFLOW = "workflow"
    API = "api"
    APP = "app"
    DATASET_RETRIEVAL = "dataset-retrieval"

    @classmethod
    def value_of(cls, value: str) -> "ToolProviderType":
        """
        Get value of given mode.

        :param value: mode value
        :return: mode
        """
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f"invalid mode value {value}")

class ToolSelector(BaseModel):
    class Parameter(BaseModel):
        name: str = Field(..., description="The name of the parameter")
        type: ToolParameter.ToolParameterType = Field(..., description="The type of the parameter")
        required: bool = Field(..., description="Whether the parameter is required")
        description: str = Field(..., description="The description of the parameter")
        default: Optional[Union[int, float, str]] = None
        options: Optional[list[ToolParameterOption]] = None

    provider_id: str = Field(..., description="The id of the provider")
    tool_name: str = Field(..., description="The name of the tool")
    tool_description: str = Field(..., description="The description of the tool")
    tool_configuration: Mapping[str, Any] = Field(..., description="Configuration, type form")
    tool_parameters: Mapping[str, Parameter] = Field(..., description="Parameters, type llm")

    def to_prompt_message(self) -> PromptMessageTool:
        """
        Convert tool selector to prompt message tool, based on openai function calling schema.
        """
        tool = PromptMessageTool(
            name=self.tool_name,
            description=self.tool_description,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

        for name, parameter in self.tool_parameters.items():
            tool.parameters[name] = {
                "type": parameter.type.value,
                "description": parameter.description,
            }

            if parameter.required:
                tool.parameters["required"].append(name)

            if parameter.options:
                tool.parameters[name]["enum"] = [option.value for option in parameter.options]

        return tool
```

## File Purpose

The tool YAML file (`your_plugin.yaml`) defines:

- Basic identity information about your tool
- Descriptions for both humans and the AI agent
- Parameters that your tool accepts
- How these parameters are presented and collected

## Example Implementation

Here's how the tool YAML files for Dropbox looks:

`ceate_folder.yaml:`

```yaml
identity:
  name: create_folder
  author: lcandy
  label:
    en_US: Create Folder
    zh_Hans: 创建文件夹
    pt_BR: Criar Pasta
    ja_JP: フォルダ作成
    zh_Hant: 建立資料夾
description:
  human:
    en_US: Create a new folder in Dropbox
    zh_Hans: 在 Dropbox 中创建新文件夹
    pt_BR: Criar uma nova pasta no Dropbox
    ja_JP: Dropbox に新しいフォルダを作成します
    zh_Hant: 在 Dropbox 中建立新資料夾
  llm: Creates a new folder at the specified path in Dropbox. Returns information about the created folder including path and ID.
parameters:
  - name: folder_path
    type: string
    required: true
    label:
      en_US: Folder Path
      zh_Hans: 文件夹路径
      pt_BR: Caminho da Pasta
      ja_JP: フォルダパス
      zh_Hant: 資料夾路徑
    human_description:
      en_US: The path where the folder will be created in Dropbox
      zh_Hans: 文件夹在 Dropbox 中的创建路径
      pt_BR: O caminho onde a pasta será criada no Dropbox
      ja_JP: Dropbox でフォルダを作成するパス
      zh_Hant: 欲在 Dropbox 中建立資料夾的路徑
    llm_description: The path where the folder will be created in Dropbox. Should be specified as a complete path, like '/Documents/Projects' or '/Photos/Vacation2023'. Paths are case-sensitive and must start with a forward slash.
    form: llm
extra:
  python:
    source: tools/create_folder.py
```

`delete_file.yaml:`

```yaml
identity:
  name: delete_file
  author: lcandy
  label:
    en_US: Delete File/Folder
    zh_Hans: 删除文件/文件夹
    pt_BR: Excluir Arquivo/Pasta
    ja_JP: ファイル/フォルダ削除
    zh_Hant: 刪除檔案/資料夾
description:
  human:
    en_US: Delete a file or folder from Dropbox
    zh_Hans: 从 Dropbox 删除文件或文件夹
    pt_BR: Excluir um arquivo ou pasta do Dropbox
    ja_JP: Dropbox からファイルやフォルダを削除します
    zh_Hant: 從 Dropbox 刪除檔案或資料夾
  llm: Permanently deletes a file or folder from Dropbox at the specified path. Returns confirmation information about the deleted item.
parameters:
  - name: file_path
    type: string
    required: true
    label:
      en_US: File/Folder Path
      zh_Hans: 文件/文件夹路径
      pt_BR: Caminho do Arquivo/Pasta
      ja_JP: ファイル/フォルダパス
      zh_Hant: 檔案/資料夾路徑
    human_description:
      en_US: The path of the file or folder to delete from Dropbox
      zh_Hans: 要从 Dropbox 删除的文件或文件夹的路径
      pt_BR: O caminho do arquivo ou pasta para excluir do Dropbox
      ja_JP: Dropbox から削除するファイルやフォルダのパス
      zh_Hant: 欲從 Dropbox 刪除的檔案或資料夾路徑
    llm_description: The path of the file or folder to delete from Dropbox. Should be specified as a complete path, like '/Documents/report.txt' or '/Photos/Vacation2023'. Paths are case-sensitive and must start with a forward slash. WARNING - This is a permanent deletion.
    form: llm
extra:
  python:
    source: tools/delete_file.py
```

`download_file.py:`

```yaml
identity:
  name: download_file
  author: lcandy
  label:
    en_US: Download File
    zh_Hans: 下载文件
    pt_BR: Baixar Arquivo
    ja_JP: ファイルダウンロード
    zh_Hant: 下載檔案
description:
  human:
    en_US: Download a file from Dropbox
    zh_Hans: 从 Dropbox 下载文件
    pt_BR: Baixar um arquivo do Dropbox
    ja_JP: Dropbox からファイルをダウンロードします
    zh_Hant: 從 Dropbox 下載檔案
  llm: Downloads a file from Dropbox at the specified path. Returns file metadata and optionally the file content (as base64 for binary files or text for text files).
parameters:
  - name: file_path
    type: string
    required: true
    label:
      en_US: File Path
      zh_Hans: 文件路径
      pt_BR: Caminho do Arquivo
      ja_JP: ファイルパス
      zh_Hant: 檔案路徑
    human_description:
      en_US: The path of the file to download from Dropbox
      zh_Hans: 要从 Dropbox 下载的文件路径
      pt_BR: O caminho do arquivo para baixar do Dropbox
      ja_JP: Dropbox からダウンロードするファイルのパス
      zh_Hant: 欲從 Dropbox 下載的檔案路徑
    llm_description: The path of the file to download from Dropbox. Should include the complete path with filename and extension, like '/Documents/report.txt'. Paths are case-sensitive and must start with a forward slash.
    form: llm
  - name: include_content
    type: boolean
    required: false
    default: false
    label:
      en_US: Include Content
      zh_Hans: 包含内容
      pt_BR: Incluir Conteúdo
      ja_JP: 内容を含める
      zh_Hant: 包含內容
    human_description:
      en_US: Whether to include the file content in the response
      zh_Hans: 是否在响应中包含文件内容
      pt_BR: Se deve incluir o conteúdo do arquivo na resposta
      ja_JP: レスポンスにファイルの内容を含めるかどうか
      zh_Hant: 是否在回應中包含檔案內容
    llm_description: Set to true to include the file content in the response. For small text files, the content will be provided as text. For binary files, the content will be provided as base64-encoded string. Default is false.
    form: llm
extra:
  python:
    source: tools/download_file.py

```

`dropbox.yaml:`

```yaml
identity:
  name: dropbox
  author: lcandy
  label:
    en_US: Dropbox
    zh_Hans: Dropbox
    pt_BR: Dropbox
    ja_JP: Dropbox
    zh_Hant: Dropbox
description:
  human:
    en_US: Interact with Dropbox
    zh_Hans: 与 Dropbox 交互
    pt_BR: Interagir com o Dropbox
    ja_JP: Dropbox と連携する
    zh_Hant: 與 Dropbox 互動
  llm: Provides access to Dropbox services, allowing you to interact with files and folders in a Dropbox account.
parameters:
  - name: query
    type: string
    required: true
    label:
      en_US: Query string
      zh_Hans: 查询语句
      pt_BR: Termo de consulta
      ja_JP: クエリ文字列
      zh_Hant: 查詢語句
    human_description:
      en_US: Enter your Dropbox operation query
      zh_Hans: 输入您的 Dropbox 操作查询
      pt_BR: Digite sua consulta de operação do Dropbox
      ja_JP: Dropbox 操作クエリを入力してください
      zh_Hant: 請輸入您要執行的 Dropbox 操作指令
    llm_description: The query describing the Dropbox operation you want to perform.
    form: llm
extra:
  python:
    source: tools/dropbox.py
```

## Key Components

1. **Identity Section**:
    - `name`: Internal name for your tool (should match your file naming)
    - `author`: Who created the tool
    - `label`: Display name in different languages
2. **Description Section**:
    - `human`: Description shown to human users in different languages
    - `llm`: Description provided to the AI agent to understand what your tool does and how to use it
3. **Parameters Section**:
    - List of parameters your tool accepts, each with:
        - `name`: Parameter identifier (used in your Python code)
        - `type`: Data type (string, number, boolean, etc.)
        - `required`: Whether this parameter is mandatory
        - `label`: User-friendly name in different languages
        - `human_description`: Explanation for human users in different languages
        - `llm_description`: Explanation for the AI agent to understand this parameter
        - `form`: How the parameter is collected
            - `llm`: AI agent extracts from user queries
            - `workflow`: User must provide as a variable in the UI
        - Optional: `default`: Default value for this parameter
4. **Extra Section**:
    - `python.source`: Path to your tool's Python implementation file

## Important Notes

1. **File Seperation:**

    Important!!!!: If your tool has different functionality, like read and write a email, or read or update a database, you should seperate the yaml file into more than one. The principle is each yaml and code file are exclusively for each type of tool execution. The file itself should only extract parameter that the tool’s functionality will use. For example, for to read and update a database, you should use two yaml file: read_database.yaml and update_database.yaml seperately.

2. **LLM Descriptions**:
    - The `llm` description for both the tool and parameters is crucial - it tells the AI agent how to use your tool
    - Be clear about what parameters are needed and what information your tool will return
    - This helps the AI agent decide when to use your tool and how to extract parameters from user queries
3. **Parameter Configuration**:
    - For each parameter, specify whether it's required
    - Choose the appropriate data type
    - Set the `form` to `llm` if you want the AI to extract it from user queries
    - Set the `form` to `workflow` if you want users to provide it directly
4. **Localization**:
    - Provide translations for labels and descriptions in multiple languages as needed
    - At minimum, include English (en_US)

To create your own tool YAML file, adapt this structure for your specific tool, clearly defining what parameters it needs and how they should be presented to both humans and the AI agent.

# 5. How to edit tools/your_plugin.py

You're tasked with creating the tool implementation file for a Dify plugin. This file contains the actual logic for your tool that makes API requests and processes the results. I'll guide you through creating this file, using Google Search as an example.

## File Purpose

The tool Python file (`your_plugin.py`) is responsible for:

- Making API requests to your service
- Processing the responses
- Returning the results in a format usable by Dify

## Required Components

1. Your tool class **must** inherit from `dify_plugin.Tool`
2. You **must** implement the `_invoke` method that returns a generator
3. You **must** include these essential imports:
    - `from collections.abc import Generator`
    - `from typing import Any`
    - `from dify_plugin import Tool`
    - `from dify_plugin.entities.tool import ToolInvokeMessage`

## Example Implementation

Here's how the tool implementation for Dropbox tool looks:

`ceate_folder.yaml:`

```python
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils

class CreateFolderTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a folder in Dropbox
        """
        # Get parameters
        folder_path = tool_parameters.get("folder_path", "")

        # Validate parameters
        if not folder_path:
            yield self.create_text_message("Folder path in Dropbox is required.")
            return

        # Make sure folder path starts with /
        if not folder_path.startswith("/"):
            folder_path = "/" + folder_path

        try:
            # Get access token from credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Dropbox access token is required.")
                return

            # Get Dropbox client
            try:
                dbx = DropboxUtils.get_client(access_token)
            except AuthError as e:
                yield self.create_text_message(f"Authentication failed: {str(e)}")
                return
            except Exception as e:
                yield self.create_text_message(f"Failed to connect to Dropbox: {str(e)}")
                return

            # Create the folder
            try:
                result = DropboxUtils.create_folder(dbx, folder_path)

                # Create response
                summary = f"Folder '{result['name']}' created successfully at '{result['path']}'"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)

            except ApiError as e:
                if "path/conflict" in str(e):
                    yield self.create_text_message(f"A folder already exists at '{folder_path}'")
                else:
                    yield self.create_text_message(f"Error creating folder: {str(e)}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
```

`delete_file.py`

```python
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils

class DeleteFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a file or folder from Dropbox
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")

        # Validate parameters
        if not file_path:
            yield self.create_text_message("File or folder path in Dropbox is required.")
            return

        # Make sure path starts with /
        if not file_path.startswith("/"):
            file_path = "/" + file_path

        try:
            # Get access token from credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Dropbox access token is required.")
                return

            # Get Dropbox client
            try:
                dbx = DropboxUtils.get_client(access_token)
            except AuthError as e:
                yield self.create_text_message(f"Authentication failed: {str(e)}")
                return
            except Exception as e:
                yield self.create_text_message(f"Failed to connect to Dropbox: {str(e)}")
                return

            # Delete the file or folder
            try:
                result = DropboxUtils.delete_file(dbx, file_path)

                # Create response
                summary = f"'{result['name']}' deleted successfully"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)

            except ApiError as e:
                if "path/not_found" in str(e):
                    yield self.create_text_message(f"File or folder not found at '{file_path}'")
                else:
                    yield self.create_text_message(f"Error deleting file/folder: {str(e)}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
```

`download_file.yaml:`

```python
from collections.abc import Generator
import base64
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils

class DownloadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Download a file from Dropbox
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        include_content = tool_parameters.get("include_content", False)

        # Validate parameters
        if not file_path:
            yield self.create_text_message("File path in Dropbox is required.")
            return

        # Make sure file path starts with /
        if not file_path.startswith("/"):
            file_path = "/" + file_path

        try:
            # Get access token from credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Dropbox access token is required.")
                return

            # Get Dropbox client
            try:
                dbx = DropboxUtils.get_client(access_token)
            except AuthError as e:
                yield self.create_text_message(f"Authentication failed: {str(e)}")
                return
            except Exception as e:
                yield self.create_text_message(f"Failed to connect to Dropbox: {str(e)}")
                return

            # Download the file
            try:
                result = DropboxUtils.download_file(dbx, file_path)

                # Create response
                response = {
                    "name": result["name"],
                    "path": result["path"],
                    "id": result["id"],
                    "size": result["size"],
                    "modified": result["modified"]
                }

                # Include content if requested
                if include_content:
                    # Encode binary content as base64
                    response["content_base64"] = base64.b64encode(result["content"]).decode('utf-8')

                    # Try to decode as text if small enough
                    if result["size"] < 1024 * 1024:  # Less than 1MB
                        try:
                            text_content = result["content"].decode('utf-8')
                            response["content_text"] = text_content
                        except UnicodeDecodeError:
                            # Not a text file, just include base64
                            pass

                summary = f"File '{result['name']}' downloaded successfully"
                yield self.create_text_message(summary)
                yield self.create_json_message(response)

            except ApiError as e:
                yield self.create_text_message(f"Error downloading file: {str(e)}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
```

## Key Points to Remember

1. **File Seperation:**

    **Important:** If your tool has different functionality, like read and write a email, or read or update a database, you should seperate the yaml file into more than one. The principle is each yaml and code file are exclusively for each type of tool execution. The file itself should only extract parameter that the tool’s functionality will use. For example, for to read and update a database, you should use two yaml file: read_database.py and update_database.py seperately.

2. **Required Imports**: Always include the essential imports at the top of your file.
3. **Class Inheritance**: Your tool class must inherit from `dify_plugin.Tool`
4. **Extracting Parameters**:
    - The `tool_parameters` dictionary contains all parameters defined in your tool's YAML file
    - Access these parameters directly using dictionary keys, e.g., `tool_parameters["query"]`
    - These parameters are automatically extracted from user queries by the AI agent
    - Ensure you handle any required parameters and provide appropriate error handling if they're missing
    - Example:

        ```python
        query = tool_parameters["query"]  # Extract the query parameterlimit = tool_parameters.get("limit", 10)  # Extract with a default value# Optional validationif not query:    raise ValueError("Query parameter cannot be empty")

        ```

5. **Accessing Credentials**:
    - Access your authentication credentials using `self.runtime.credentials`
    - The keys match those defined in your provider YAML file
    - Example: `self.runtime.credentials["serpapi_api_key"]`
6. **Response Processing**: Create a helper method to extract only the relevant information from API responses.
7. **Yielding Results**: You must use `yield` with one of the message creation methods to return data.

When implementing your own tool, make sure you correctly extract all the parameters you need from the `tool_parameters` dictionary, and validate them if necessary. The available parameters are defined in your tool's YAML file and will be automatically extracted from user queries by the AI agent.

# 6. How to Create PRIVACY.md and README.md

You're tasked with creating the privacy policy and readme files for your Dify plugin. These files are written in Markdown format and serve important purposes for users and developers of your plugin. Let me guide you through creating both files.

## PRIVACY.md

The PRIVACY.md file outlines your plugin's privacy practices, including what data it collects and how that data is used. This is critical information for users concerned about their data privacy.

### What to Include

Based on the placeholder text you shared ("!!! Please fill in the privacy policy of the plugin."), you should include:

1. What data your plugin collects
2. How this data is stored and processed
3. What third-party services are used (if any)
4. User rights regarding their data
5. How long data is retained
6. Contact information for privacy concerns

### Example Structure

```markdown
# Privacy Policy

## Data Collection
[Describe what user data your plugin collects and why]

## Data Processing
[Explain how the collected data is processed]

## Third-party Services
[List any third-party services used by your plugin and link to their privacy policies]

## Data Retention
[Explain how long user data is stored]

## User Rights
[Outline what rights users have regarding their data]

## Contact Information
[Provide contact information for privacy-related inquiries]

Last updated: [Date]

```

## README.md

The README.md file provides essential information about your plugin, including what it does, how to install it, and how to use it. This is the first document most users and developers will refer to.

### What to Include

Based on the example you shared (Jira plugin readme), you should include:

1. Plugin name as the main heading
2. Author information
3. Version information
4. Type of plugin
5. Detailed description of what the plugin does
6. Installation instructions
7. Usage examples
8. Configuration options
9. Troubleshooting information

### Example Structure

```markdown
# Your Plugin Name

**Author:** [Your name or organization]
**Version:** [Current version number]
**Type:** [Plugin type]

## Description
[Provide a detailed description of what your plugin does]

## Features
- [Feature 1]
- [Feature 2]
- [Feature 3]

## Installation
[Provide step-by-step installation instructions]

## Configuration
[Explain how to configure your plugin]

## Usage Examples
[Provide examples of how to use your plugin]

## Troubleshooting
[List common issues and their solutions]

## Contributing
[Explain how others can contribute to your plugin]

## License
[Specify the license under which your plugin is released]

```

### Using Images

As you mentioned, if you want to include images in either document:

1. Store the images in the `_assets` folder
2. Reference them in your Markdown using relative paths:

```markdown
![Description of image](_assets/image_name.png)

```

Both of these files should be written in Markdown format (`.md` extension) and placed in the root directory of your plugin project. Make sure to keep them up-to-date as your plugin evolves.

## Requirements.txt

You should always use the latest dependencies by using `~=` in your txt file, and the `dify_plugin~=0.0.1b72` is a must be.
