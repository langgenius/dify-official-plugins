"""normalize_private_key must accept PKCS#1 (oci setup keys) and PKCS#8 (OCI Console download)
keys, with the newlines intact or collapsed to spaces by the secret input, and the result must be
loadable by the crypto library the OCI SDK uses."""

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dify_plugin.errors.model import CredentialsValidateFailedError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.oci_private_key import normalize_private_key  # noqa: E402

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PKCS1 = _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()).decode()
PKCS8 = _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


def _loads(pem: str) -> bool:
    serialization.load_pem_private_key(pem.encode(), password=None)
    return True


@pytest.mark.parametrize("pem", [PKCS1, PKCS8], ids=["pkcs1", "pkcs8"])
def test_well_formed_pem_round_trips(pem):
    out = normalize_private_key(pem)
    assert out.splitlines()[0] == pem.splitlines()[0]
    assert _loads(out)


@pytest.mark.parametrize("pem", [PKCS1, PKCS8], ids=["pkcs1", "pkcs8"])
def test_single_line_pem_from_secret_input_is_repaired(pem):
    collapsed = pem.replace("\n", " ")
    out = normalize_private_key(collapsed)
    assert out.splitlines()[0] == pem.splitlines()[0]
    assert _loads(out)


def test_bare_pkcs1_body_keeps_legacy_behaviour():
    body = "".join(line for line in PKCS1.splitlines() if not line.startswith("-----"))
    out = normalize_private_key(body)
    assert out.startswith("-----BEGIN RSA PRIVATE KEY-----")
    assert _loads(out)


@pytest.mark.parametrize("bad", ["", "   ", "not a key", "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"])
def test_garbage_is_rejected_with_credentials_error(bad):
    with pytest.raises(CredentialsValidateFailedError):
        normalize_private_key(bad)
