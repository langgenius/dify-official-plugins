import os

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

if __name__ == '__main__':
    load_dotenv()
    genai_client = genai.Client(
        api_key=os.getenv("GENAI_API_KEY"),
        http_options=types.HttpOptions(
            httpx_client=httpx.Client(proxy=os.getenv("GRPC_PROXY"))

        )
    )
    bytes = genai_client.files.download(
        file='https://generativelanguage.googleapis.com/v1beta/files/y0dfitgnqh5r:download?alt=media'
    )
    # 直接保存
    video = genai.types.Video(video_bytes=bytes, mime_type="video/mp4")
    video.save("veo3_with_image_input.mp4")
    print("Generated video saved to veo3_with_image_input.mp4")
    print(video.mime_type)
    print(video.video_bytes is not None)
