from __future__ import annotations

import io
import math
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps

from ..config import Settings
from ..models import Creative
from ..utils.logging import get_logger


log = get_logger(__name__)


def _fetch_image(uri: str, settings: Settings) -> Optional[Image.Image]:
    if not uri:
        return None
    try:
        if uri.startswith("http://") or uri.startswith("https://"):
            try:
                import requests  # type: ignore
            except Exception:
                log.warning("requests not installed; cannot fetch remote image: %s", uri)
                return None
            try:
                headers = {"User-Agent": "ad-optimizer/1.0"}
                r = requests.get(uri, headers=headers, timeout=10)
                r.raise_for_status()
                return Image.open(io.BytesIO(r.content)).convert("RGB")
            except Exception as e:
                log.warning("Failed to fetch image %s: %s", uri, e)
                return None
        elif uri.startswith("gs://"):
            # Optionally resolve via signed URL if storage configured
            try:
                from ..assets.storage import GCSStorage
                store = GCSStorage(settings)
                if store._client and settings.gcs_bucket:
                    # Try to parse bucket/object
                    # Format: gs://bucket/path/to/blob
                    parts = uri.replace("gs://", "").split("/", 1)
                    if len(parts) == 2 and parts[0] == settings.gcs_bucket:
                        signed = store.generate_signed_url(parts[1])
                        if signed:
                            return _fetch_image(signed, settings)
            except Exception as e:
                log.info("GCS fetch skipped: %s", e)
            return None
        else:
            # Local path
            return Image.open(uri).convert("RGB")
    except Exception as e:
        log.warning("Image load failed for %s: %s", uri, e)
        return None


def _to_grayscale(img: Image.Image) -> Image.Image:
    return ImageOps.grayscale(img)


def compute_ahash(img: Image.Image, hash_size: int = 8) -> str:
    gray = _to_grayscale(img).resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float32)
    avg = pixels.mean()
    bits = pixels > avg
    # Pack bits into hex
    bitstr = ''.join('1' if b else '0' for b in bits.flatten())
    return f"{int(bitstr, 2):0{hash_size*hash_size//4}x}"


def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    gray = _to_grayscale(img).resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.int16)
    diff = pixels[:, 1:] > pixels[:, :-1]
    bitstr = ''.join('1' if b else '0' for b in diff.flatten())
    return f"{int(bitstr, 2):0{hash_size*hash_size//4}x}"


def dominant_colors(img: Image.Image, k: int = 5) -> List[str]:
    # Use PIL quantize to approximate dominant colors
    thumb = img.copy()
    thumb.thumbnail((200, 200))
    pal = thumb.convert('P', palette=Image.Palette.ADAPTIVE, colors=k)
    palette = pal.getpalette()[: k * 3]
    color_counts = pal.getcolors()
    if not color_counts:
        return []
    # Sort by count desc
    color_counts.sort(reverse=True)
    colors_hex: List[str] = []
    for count, idx in color_counts[:k]:
        r = palette[idx * 3 + 0]
        g = palette[idx * 3 + 1]
        b = palette[idx * 3 + 2]
        colors_hex.append(f"#{r:02x}{g:02x}{b:02x}")
    return colors_hex


def average_brightness(img: Image.Image) -> float:
    gray = _to_grayscale(img)
    arr = np.asarray(gray, dtype=np.float32)
    return float(arr.mean() / 255.0)


def shannon_entropy(img: Image.Image) -> float:
    gray = _to_grayscale(img)
    hist = gray.histogram()  # 256 bins
    total = float(sum(hist))
    if total == 0:
        return 0.0
    probs = [h / total for h in hist if h > 0]
    return float(-sum(p * math.log2(p) for p in probs))


def ocr_overlay_text(img: Image.Image) -> Tuple[str, float]:
    """Return extracted text and approximate density (0..1).

    If pytesseract or Tesseract binary are missing, returns ("", 0.0).
    If available, density is total text bounding-box area / image area.
    """
    try:
        import pytesseract  # type: ignore
        from pytesseract import Output  # type: ignore
    except Exception:
        return "", 0.0
    try:
        data = pytesseract.image_to_data(img, output_type=Output.DICT)
        text = []
        area = 0
        W, H = img.size
        img_area = max(1, W * H)
        n = len(data.get("text", []))
        for i in range(n):
            s = (data["text"][i] or "").strip()
            if not s:
                continue
            text.append(s)
            w = int(data.get("width", [0])[i] or 0)
            h = int(data.get("height", [0])[i] or 0)
            area += w * h
        density = min(1.0, area / img_area)
        return (" ".join(text), float(density))
    except Exception as e:
        log.info("OCR failed: %s", e)
        return "", 0.0


def hamming_distance_hex(h1: str, h2: str) -> int:
    # Normalize lengths
    n = max(len(h1), len(h2))
    a = int(h1.ljust(n, '0'), 16)
    b = int(h2.ljust(n, '0'), 16)
    return int(bin(a ^ b).count('1'))


@dataclass
class VisualFeatures:
    creative_id: str
    width: int
    height: int
    ahash: str
    dhash: str
    dominant_colors: List[str]
    avg_brightness: float
    entropy: float
    overlay_text: str
    overlay_density: float


def compute_visual_features(settings: Settings, creative: Creative) -> Optional[VisualFeatures]:
    if not creative.asset_uri:
        return None
    img = _fetch_image(creative.asset_uri, settings)
    if img is None:
        return None
    try:
        ah = compute_ahash(img)
        dh = compute_dhash(img)
        cols = dominant_colors(img, k=5)
        ab = average_brightness(img)
        ent = shannon_entropy(img)
        txt, dens = ocr_overlay_text(img)
        W, H = img.size
        return VisualFeatures(
            creative_id=creative.creative_id,
            width=W,
            height=H,
            ahash=ah,
            dhash=dh,
            dominant_colors=cols,
            avg_brightness=ab,
            entropy=ent,
            overlay_text=txt,
            overlay_density=dens,
        )
    except Exception as e:
        log.warning("Failed computing visual features for %s: %s", creative.creative_id, e)
        return None


def novelty_score(current_hash: str, other_hashes: List[str], hash_bits: int = 64) -> float:
    if not other_hashes:
        return 1.0
    dists = [hamming_distance_hex(current_hash, h) for h in other_hashes]
    # Normalize by number of bits (approx from hex length)
    bits = max(1, len(current_hash) * 4)
    min_norm = min(d / bits for d in dists)
    return float(min_norm)

