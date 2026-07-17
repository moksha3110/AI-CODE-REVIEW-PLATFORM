"""
GitHub signs every webhook delivery with HMAC-SHA256 over the raw request
body, using a secret configured on the GitHub App. We must verify against
the RAW bytes (not the parsed/re-serialized JSON, which can differ in
whitespace and key ordering and would break the signature) before trusting
anything in the payload.
"""
import hashlib
import hmac

from app.core.config import get_settings
from app.core.exceptions import InvalidWebhookSignatureError

SIGNATURE_HEADER = "X-Hub-Signature-256"


def verify_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise InvalidWebhookSignatureError("missing or malformed signature header")

    secret = get_settings().github_webhook_secret.encode()
    expected = "sha256=" + hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    # constant-time comparison - a timing side-channel here would let an
    # attacker brute-force the signature byte by byte
    if not hmac.compare_digest(expected, signature_header):
        raise InvalidWebhookSignatureError("signature does not match payload")
