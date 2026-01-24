import io
import json
import os
from typing import Optional, Union
from urllib.parse import urlencode

from google.genai import types, _extra_utils, _common, files
from google.genai.files import _GetFileParameters_to_mldev

def upload(
        self: files.Files,
        *,
        file: Union[str, os.PathLike[str], io.IOBase],
        config: Optional[types.UploadFileConfigOrDict] = None,
        base_url:str = None,
) -> types.File:
    """Calls the API to upload a file using a supported file service.

    Args:
      file: A path to the file or an `IOBase` object to be uploaded. If it's an
        IOBase object, it must be opened in blocking (the default) mode and
        binary mode. In other words, do not use non-blocking mode or text mode.
        The given stream must be seekable, that is, it must be able to call
        `seek()` on 'path'.
      config: Optional parameters to set `diplay_name`, `mime_type`, and `name`.
      base_url: Replace upload request url.
    """
    if self._api_client.vertexai:
        raise ValueError(
            'This method is only supported in the Gemini Developer client.'
        )
    config_model = types.UploadFileConfig()
    if config:
        if isinstance(config, dict):
            config_model = types.UploadFileConfig(**config)
        else:
            config_model = config
        file_obj = types.File(
            mime_type=config_model.mime_type,
            name=config_model.name,
            display_name=config_model.display_name,
        )
    else:  # if not config
        file_obj = types.File()
    if file_obj.name is not None and not file_obj.name.startswith('files/'):
        file_obj.name = f'files/{file_obj.name}'

    http_options, size_bytes, mime_type = _extra_utils.prepare_resumable_upload(
        file,
        user_http_options=config_model.http_options,
        user_mime_type=config_model.mime_type,
    )
    file_obj.size_bytes = size_bytes
    file_obj.mime_type = mime_type
    response = self._create(
        file=file_obj,
        config=types.CreateFileConfig(
            http_options=http_options, should_return_http_response=True
        ),
    )

    if (
            response.sdk_http_response is None
            or response.sdk_http_response.headers is None
            or 'x-goog-upload-url' not in response.sdk_http_response.headers
    ):
        raise KeyError(
            'Failed to create file. Upload URL did not returned from the create'
            ' file request.'
        )
    upload_url = response.sdk_http_response.headers['x-goog-upload-url']

    # ------
    # base_url不为空时替换上传网址
    if not _is_str_empty(base_url):
        upload_url = upload_url.replace(
            "https://generativelanguage.googleapis.com", base_url
        )
    # ------

    if isinstance(file, io.IOBase):
        return_file = self._api_client.upload_file(
            file, upload_url, file_obj.size_bytes, http_options=http_options
        )
    else:
        fs_path = os.fspath(file)
        return_file = self._api_client.upload_file(
            fs_path, upload_url, file_obj.size_bytes, http_options=http_options
        )

    return types.File._from_response(
        response=return_file.json['file'],
        kwargs=config_model.model_dump() if config else {},
    )


def get(
  self, *, name: str, config: Optional[types.GetFileConfigOrDict] = None
) -> types.File:
    """Retrieves the file information from the service.

    Args:
      name (str): The name identifier for the file to retrieve.
      config (GetFileConfig): Optional, configuration for the get method.

    Returns:
      File: The file information.

    Usage:

    .. code-block:: python

      file = client.files.get(name='files/...')
      print(file.uri)
    """

    parameter_model = types._GetFileParameters(
        name=name,
        config=config,
    )

    request_url_dict: Optional[dict[str, str]]
    if self._api_client.vertexai:
      raise ValueError(
          'This method is only supported in the Gemini Developer client.'
      )
    else:
      request_dict = _GetFileParameters_to_mldev(parameter_model)
      request_url_dict = request_dict.get('_url')
      if request_url_dict:
        path = 'files/{file}'.format_map(request_url_dict)
      else:
        path = 'files/{file}'

    query_params = request_dict.get('_query')
    if query_params:
      path = f'{path}?{urlencode(query_params)}'
    # TODO: remove the hack that pops config.
    request_dict.pop('config', None)

    http_options: Optional[types.HttpOptions] = None
    if (
        parameter_model.config is not None
        and parameter_model.config.http_options is not None
    ):
      http_options = parameter_model.config.http_options

    request_dict = _common.convert_to_dict(request_dict)
    request_dict = _common.encode_unserializable_types(request_dict)

    response = self._api_client.request('get', path, request_dict, http_options)

    response_dict = {} if not response.body else json.loads(response.body)

    return_value = types.File._from_response(
        response=response_dict, kwargs=parameter_model.model_dump()
    )

    self._api_client._verify_response(return_value)
    return return_value

def _is_str_empty(value: str) -> bool:
    return value is None or len(value) == 0