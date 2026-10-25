import hashlib
import hmac
import secrets

def issue_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def token_matches(token: str, digest: str) -> bool:
    return hmac.compare_digest(hash_token(token), digest)
