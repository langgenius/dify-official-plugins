import logging
import requests
import sys  # 新增导入sys模块
from collections.abc import Mapping
from urllib.parse import urlparse, urlunparse

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

# 配置基础日志设置（新增部分）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # 输出到控制台
    ]
)

logger = logging.getLogger(__name__)


class Moments8ModelProvider(ModelProvider):
    TIMEOUT = 100  # 统一的超时时间设置

    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """验证 API 凭证有效性，确保健壮性和明确错误反馈"""

        # 1. 提取并验证基础凭证
        api_key = credentials.get("moments8_api_key", "").strip()
        api_base = credentials.get("moments8_api_url", "https://mas.moments8.com").strip()

        if not api_key:
            logger.error("moments8_api_key 缺失")
            print("moments8_api_key 缺失", file=sys.stderr)  # 同时打印到标准错误
            raise CredentialsValidateFailedError("API 密钥未提供")

        logger.info(f"开始验证 API 凭据: key={api_key[:5]}...{api_key[-3:]}, endpoint={api_base}")

        # 2. 规范化 API 地址
        api_endpoint = "https://mas.moments8.com"

        try:
            # 3. 创建安全的 HTTP 会话
            with requests.Session() as session:
                session.headers.update({
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                })

                # 4. 执行连通性测试 - 轻量级 API 请求
                response = session.post(
                    f"{api_endpoint}/api/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "model": "deepseek-r1-distill-qwen-32b"
                    },
                    timeout=self.TIMEOUT
                )

                # 5. 响应状态检查
                if not response.ok:
                    error_msg = f"API 响应异常: HTTP {response.status_code}, 响应: {response.text[:100]}"
                    logger.error(error_msg)
                    print(error_msg, file=sys.stderr)  # 新增打印
                    raise CredentialsValidateFailedError(f"服务端错误 ({response.status_code})")

                # 6. 响应结构验证
                response_data = response.json()
                if not isinstance(response_data, dict):
                    logger.error("API 返回无效结构")
                    print("API 返回无效结构", file=sys.stderr)  # 新增打印
                    raise CredentialsValidateFailedError("API 返回格式无效")

                if "choices" not in response_data or not isinstance(response_data["choices"], list):
                    error_msg = f"API 响应缺少必要字段: {list(response_data.keys())}"
                    logger.error(error_msg)
                    print(error_msg, file=sys.stderr)  # 新增打印
                    raise CredentialsValidateFailedError("API 响应结构不兼容")

        except requests.exceptions.Timeout:
            error_msg = f"API 连接超时 ({self.TIMEOUT}s)"
            logger.error(error_msg)
            print(error_msg, file=sys.stderr)  # 新增打印
            raise CredentialsValidateFailedError("连接超时，请检查网络和服务可用性")

        except requests.exceptions.ConnectionError as e:
            error_msg = f"网络连接错误: {str(e)}"
            logger.error(error_msg)
            print(error_msg, file=sys.stderr)  # 新增打印
            raise CredentialsValidateFailedError("无法连接到服务，请检查地址和网络设置")

        except requests.exceptions.RequestException as e:
            error_msg = f"请求异常: {str(e)}"
            logger.error(error_msg)
            print(error_msg, file=sys.stderr)  # 新增打印
            raise CredentialsValidateFailedError(f"请求处理错误: {str(e)}")

        except ValueError as e:  # JSON 解码异常
            error_msg = f"响应解析错误: {str(e)}"
            logger.error(error_msg)
            print(error_msg, file=sys.stderr)  # 新增打印
            raise CredentialsValidateFailedError("响应内容格式无效")

        success_msg = "API 凭证验证成功"
        logger.info(success_msg)
        print(success_msg)  # 新增打印