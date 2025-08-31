import json
import six
import os
from oci.request import Request
from oci.base_client import _sanitize_headers_for_requests,missing
from oci import constants, exceptions
from timeit import default_timer as timer


def patched_call_api(self, resource_path, method,
                     path_params=None,
                     query_params=None,
                     header_params=None,
                     body=None,
                     response_type=None,
                     enforce_content_headers=True,
                     allow_control_chars=None,
                     operation_name=None,
                     api_reference_link=None,
                     required_arguments=[]):
    """
    这是 call_api 的补丁版本。
    """
    enable_expect_header = True
    
    if header_params:
        if not enable_expect_header or method.lower() not in ["put", "post", "patch"]:
            map_lowercase_header_params_keys_to_actual_keys = {k.lower(): k for k in header_params}
            if "expect" in map_lowercase_header_params_keys_to_actual_keys:
                header_params.pop(map_lowercase_header_params_keys_to_actual_keys.get("expect"), None)

        header_params = self.sanitize_for_serialization(header_params)

    header_params = header_params or {}

    header_params = _sanitize_headers_for_requests(header_params)
    header_params[constants.HEADER_CLIENT_INFO] = "Oracle-PythonSDK/2.126.0" # 你可以根据需要更新
    header_params[constants.HEADER_USER_AGENT] = self.user_agent

    if header_params.get(constants.HEADER_REQUEST_ID, missing) is missing:
        header_params[constants.HEADER_REQUEST_ID] = self.build_request_id()

    opc_host_serial = os.environ.get('OCI_DB_OPC_HOST_SERIAL')
    if opc_host_serial:
        header_params['opc-host-serial'] = opc_host_serial

    if path_params:
        path_params = self.sanitize_for_serialization(path_params)
        for k, v in path_params.items():
            replacement = six.moves.urllib.parse.quote(str(self.to_path_value(v)))
            resource_path = resource_path.replace('{' + k + '}', replacement)

    if query_params:
        query_params = self.process_query_params(query_params)

    # ==================== 补丁核心逻辑开始 ====================
    # print("body"*20, body)
    # if body is not None and header_params.get('content-type') == 'application/json':
    #     #body = self.sanitize_for_serialization(body)
    #     body = json.dumps(body)
    # ==================== 补丁核心逻辑结束 ====================

    endpoint = self.handle_service_params_in_endpoint(path_params, query_params, required_arguments)
    url = endpoint + resource_path

    request = Request(
        method=method,
        url=url,
        query_params=query_params,
        header_params=header_params,
        body=body,
        response_type=response_type,
        enforce_content_headers=enforce_content_headers
    )

    if self.is_instance_principal_or_resource_principal_signer():
        call_attempts = 0
        while call_attempts < 2:
            try:
                return self.request(request, allow_control_chars, operation_name, api_reference_link)
            except exceptions.ServiceError as e:
                call_attempts += 1
                if e.status == 401 and call_attempts < 2:
                    self.signer.refresh_security_token()
                else:
                    raise
    else:
        start = timer()
        response = self.request(request, allow_control_chars, operation_name, api_reference_link)
        end = timer()
        self.logger.debug('time elapsed for request: {}'.format(str(end - start)))
        return response
