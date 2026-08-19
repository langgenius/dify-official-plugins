import sys
from pathlib import Path

# Make the plugin root importable so `models.llm.llm` (namespace package),
# `provider.*`, and `utils.*` resolve exactly as they do at plugin runtime.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
