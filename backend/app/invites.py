import hashlib
import secrets

# 헷갈리는 글자(0/O, 1/I/L)를 뺀 31자 × 10자리 ≈ 49비트
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10


def new_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


def normalize(code: str) -> str:
    """사용자가 소문자·공백·하이픈을 섞어 입력해도 같은 코드로 본다."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def hash_code(code: str) -> str:
    # 코드가 무작위이고 7일 뒤 만료되므로 솔트 없는 SHA-256로 충분하다
    return hashlib.sha256(normalize(code).encode()).hexdigest()
