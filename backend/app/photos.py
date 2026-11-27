"""사진 처리: 다시 인코딩해 EXIF(촬영 위치·기기 정보)를 지우고 크기를 줄인다."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

# 큰 이미지로 메모리를 터뜨리는 공격(압축 폭탄)을 막는다. 4000만 화소를 넘으면 거부.
Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_SIDE = 1600
ALLOWED = {"JPEG", "PNG", "WEBP"}  # HEIC는 브라우저가 촬영 시 JPEG로 바꿔 보낸다


class BadImage(ValueError):
    pass


def clean_jpeg(data: bytes) -> bytes:
    """읽을 수 있는 사진이면 회전을 반영한 JPEG로 다시 만든다. 메타데이터는 옮기지 않는다."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ALLOWED:
                raise BadImage(img.format or "unknown")
            img.load()
            upright = ImageOps.exif_transpose(img)  # 세로 사진이 눕지 않게 회전만 반영
            rgb = upright.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as e:
        raise BadImage(type(e).__name__) from e
    rgb.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=85, optimize=True)  # exif 인자를 주지 않아 빈 메타데이터
    return out.getvalue()
