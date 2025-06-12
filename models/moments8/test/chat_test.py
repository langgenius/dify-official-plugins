import requests


def send_chat_request():
    """发送 POST JSON 请求到模型服务"""

    # 1. 设置请求配置
    url = "https://masdev.intra.moments8.com/api/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-VijK5mCuACEUL8TGJG3olZZ9sYm1w4FW"
    }

    # 2. 准备请求体
    payload = {
        "model": "deepseek-r1-distill-qwen-32b",
        "max_tokens": 4096,
        "stream": True,  # 使用流式响应
        "messages": [
            {
                "role": "user",
                "content": "计算1+6"
            }
        ]
    }

    try:
        # 3. 发送请求（处理流式响应）
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True  # 启用流式读取
        )

        # 4. 处理响应
        if response.status_code == 200:
            print("请求成功！流式响应内容:")
            # 逐行读取流式响应
            for line in response.iter_lines():
                if line:  # 过滤保活空行
                    decoded_line = line.decode('utf-8')
                    print(decoded_line)
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print(f"错误详情: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")


# 调用方法执行请求
if __name__ == "__main__":
    send_chat_request()