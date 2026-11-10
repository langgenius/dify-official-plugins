import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load(path):
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def instance(cls):
    o = object.__new__(cls)
    o.runtime = NS(credentials={"access_token": "test"})
    return o


def test_box_not_found_surfaces():
    m = load("datasources/box_datasource/datasources/box.py")
    o = instance(m.BoxDataSource)
    with patch.object(
        m.requests, "get", return_value=NS(status_code=404, text="not found")
    ), pytest.raises(ValueError, match="not found"):
        o._browse_files(
            NS(bucket="box", prefix="missing", max_keys=10, next_page_parameters={})
        )
