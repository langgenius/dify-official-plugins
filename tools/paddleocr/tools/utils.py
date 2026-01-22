import re

MARKDOWN_IMAGE_PATTERN = re.compile(
        r"""
        <div[^>]*>\s*
        <img[^>]*/>\s*
        </div>
        |
        <img[^>]*/>
        """,
        re.IGNORECASE | re.VERBOSE | re.DOTALL
    )


def remove_img_from_markdown(markdown: str) -> str:
    return MARKDOWN_IMAGE_PATTERN.sub("", markdown)
