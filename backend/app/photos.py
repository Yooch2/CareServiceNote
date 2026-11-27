"""사진 처리: 다시 인코딩해 EXIF(촬영 위치·기기 정보)를 지우고 크기를 줄인다."""

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

# 큰 이미지로 메모리를 터뜨리는 공격(압축 폭탄)을 막는다.
# Pillow는 MAX_IMAGE_PIXELS의 2배부터 오류, 1~2배는 경고만 내므로 디코딩 전에 직접 확인한다.
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
MAX_SIDE = 1600
FORMATS = ("JPEG", "PNG", "WEBP")  # HEIC는 브라우저가 촬영 시 JPEG로 바꿔 보낸다


class BadImage(ValueError):
    pass


def clean_jpeg(data: bytes) -> bytes:
    """읽을 수 있는 사진이면 회전을 반영한 JPEG로 다시 만든다. 메타데이터는 옮기지 않는다."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # 다른 형식의 파서는 아예 돌지 않게 세 형식만 연다
            with Image.open(io.BytesIO(data), formats=FORMATS) as img:
                if img.width * img.height > MAX_PIXELS:  # 헤더만 읽은 상태에서 거른다
                    raise BadImage("too_many_pixels")
                if img.format == "JPEG":
                    img.draft("RGB", (MAX_SIDE, MAX_SIDE))  # 줄여서 디코딩해 메모리 사용을 낮춘다
                img.load()
                upright = ImageOps.exif_transpose(img)  # 세로 사진이 눕지 않게 회전만 반영
                rgb = upright.convert("RGB")
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
    ) as e:
        raise BadImage(type(e).__name__) from e
    rgb.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=85, optimize=True)  # exif 인자를 주지 않아 빈 메타데이터
    return out.getvalue()
