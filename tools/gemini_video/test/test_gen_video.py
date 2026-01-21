import os
import time

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
    source = types.GenerateVideosSource(
        prompt="The frame focuses on a hand holding a champagne flute: its lines are sleek and relaxed, adorned with bright red glitter nail polish that boasts a rich luster and distinct fine glitter particles. The transparent tall flute contains half a glass of golden, crystal-clear champagne, with its walls reflecting the surrounding light and the liquid’s surface shimmering with a subtle glow. The background features a blurred cluster of warm yellow vintage light bulbs (appearing as hazy light spots), paired with a dark red curtain. The entire scene is wrapped in soft warm light, exuding a lazy, retro, and exquisite atmosphere.",
        image=types.Image(
            image_bytes=open("test.jpg", "rb").read(),
            mime_type="image/jpg",
        )
    )
    config = types.GenerateVideosConfig(
        duration_seconds=4,
        aspect_ratio="16:9",
        resolution="720p",
        negative_prompt="nsfw",
    )

    operation: types.GenerateVideosOperation = genai_client.models.generate_videos(
        model="veo-3.1-fast-generate-preview",
        source=source,
        config=config
    )

    # Poll the operation status until the video is ready.
    while not operation.done:
        print("Waiting for video generation to complete...")
        time.sleep(10)
        operation = genai_client.operations.get(operation)

    # Download the video.
    video = operation.response.generated_videos[0]
    genai_client.files.download(file=video.video)
    video.video.save("veo3_with_image_input.mp4")
    print("Generated video saved to veo3_with_image_input.mp4")
