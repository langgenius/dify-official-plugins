"""Turn the credential form's "Key File Content" into a PEM the OCI SDK accepts."""

import re
import textwrap

from dify_plugin.errors.model import CredentialsValidateFailedError

_PEM_RE = re.compile(r"-----BEGIN ([A-Z0-9 ]+?)-----(.*?)-----END \1-----", re.S)
_BASE64_RE = re.compile(r"[A-Za-z0-9+/=]+")
# Legacy behaviour: a bare base64 body without PEM headers is treated as PKCS#1.
_DEFAULT_LABEL = "RSA PRIVATE KEY"


def normalize_private_key(key_content: str) -> str:
    """
    Rebuild a well-formed PEM private key from whatever was pasted into the secret input.

    Dify's secret field frequently collapses the key to a single line (newlines become
    spaces), and users paste keys in both the PKCS#1 format produced by ``oci setup keys``
    (``BEGIN RSA PRIVATE KEY``) and the PKCS#8 format downloaded from the OCI Console
    (``BEGIN PRIVATE KEY``). The original header label is preserved so the SDK can parse
    either; re-labelling a PKCS#8 body as PKCS#1 makes the SDK reject the key.
    """
    if not isinstance(key_content, str) or not key_content.strip():
        raise CredentialsValidateFailedError(
            "key_content is empty. Please paste the content of your API signing key (PEM)."
        )

    text = key_content.strip()
    match = _PEM_RE.search(text)
    if match:
        label, body = match.group(1).strip(), match.group(2)
    else:
        label, body = _DEFAULT_LABEL, text

    body = "".join(body.split())
    if len(body) < 64 or not _BASE64_RE.fullmatch(body):
        raise CredentialsValidateFailedError(
            "failed to parse API key_content. Please provide valid PEM key content."
        )

    return f"-----BEGIN {label}-----\n" + "\n".join(textwrap.wrap(body, 64)) + f"\n-----END {label}-----\n"
