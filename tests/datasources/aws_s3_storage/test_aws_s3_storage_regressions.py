import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

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


def test_s3_body_closed():
    m = load("datasources/aws_s3_storage/datasources/aws_s3_storage.py")
    o = instance(m.AWSS3StorageDataSource)
    o.runtime.credentials = {"region_name": "us-east-1"}
    body = Mock()
    body.read.return_value = b"hello"
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentType": "text/plain"}
    o.create_blob_message = Mock(return_value="blob")
    with patch.object(m.boto3, "client", return_value=client):
        list(o._download_file(NS(bucket="test", id="hello.txt")))
    body.close.assert_called_once()


def test_s3_body_closed_on_read_failure():
    m = load("datasources/aws_s3_storage/datasources/aws_s3_storage.py")
    o = instance(m.AWSS3StorageDataSource)
    o.runtime.credentials = {"region_name": "us-east-1"}
    body = Mock()
    body.read.side_effect = OSError("read failure")
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentType": "text/plain"}
    with patch.object(m.boto3, "client", return_value=client), pytest.raises(OSError):
        list(o._download_file(NS(bucket="test", id="hello.txt")))
    body.close.assert_called_once()
