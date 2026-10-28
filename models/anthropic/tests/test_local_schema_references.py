from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def test_model_yaml_files_have_no_dangling_local_schema_references():
    for path in (ROOT / "models").rglob("*.yaml"):
        for reference in re.findall(r"^# yaml-language-server: \$schema=(.+)$", path.read_text(), re.MULTILINE):
            if "://" not in reference:
                assert (path.parent / reference.strip()).is_file(), path
