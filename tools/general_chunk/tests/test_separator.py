import pytest

from tools.splitter.fixed_text_splitter import FixedRecursiveCharacterTextSplitter


@pytest.mark.parametrize(
    "separator,text",
    [
        ("。", "first。second"),
        ("😀", "first😀second"),
        (r"\n", "first\nsecond"),
        (r"。\n", "first。\nsecond"),
    ],
)
def test_fixed_separator_preserves_unicode_and_decodes_escapes(separator, text):
    splitter = FixedRecursiveCharacterTextSplitter.from_encoder(
        fixed_separator=separator,
        chunk_size=100,
        chunk_overlap=0,
    )
    assert splitter.split_text(text) == ["first", "second"]
