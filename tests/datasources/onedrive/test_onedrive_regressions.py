import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

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


def test_onedrive_empty_folder_facet():
    m = load("datasources/onedrive/datasources/onedrive.py")
    o = instance(m.OneDriveDataSource)
    with patch.object(
        m.requests,
        "get",
        return_value=NS(
            status_code=200,
            content=b"x",
            json=lambda: {
                "value": [{"id": "1", "name": "empty folder", "folder": {}, "size": 0}]
            },
        ),
    ):
        assert (
            o._browse_files(
                NS(
                    bucket="onedrive",
                    prefix="root",
                    max_keys=10,
                    next_page_parameters={},
                )
            )
            .result[0]
            .files[0]
            .type
            == "folder"
        )
