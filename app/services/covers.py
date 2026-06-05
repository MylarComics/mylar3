import os
from io import BytesIO
from typing import Optional
import httpx
from PIL import Image, ImageFile
from app.core.config import settings
from app.core.logger import logger

# Allow loading of truncated/corrupt images safely
ImageFile.LOAD_TRUNCATED_IMAGES = True

async def download_image(url: str) -> Optional[bytes]:
    """
    Download raw bytes of an image from a URL.
    """
    headers = {"User-Agent": settings.CV_USER_AGENT}
    try:
        async with httpx.AsyncClient(verify=settings.CV_VERIFY, timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.content
            logger.warning(f"[Covers] Failed to download cover from {url}, status code: {response.status_code}")
    except Exception as e:
        logger.error(f"[Covers] Error downloading cover from {url}: {e}")
    return None

def scale_image(image_bytes: bytes, target_width: int = 600) -> Optional[bytes]:
    """
    Scale image bytes to a target width while maintaining aspect ratio,
    converting it to RGB JPEG.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        # Handle transparency/alpha channel by converting to RGB
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])  # 3 is the alpha channel
            else:
                background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        width, height = img.size
        if width > target_width:
            scale = target_width / float(width)
            new_height = int(scale * height)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format="JPEG", quality=85)
        return output.getvalue()
    except Exception as e:
        logger.error(f"[Covers] Error scaling image: {e}")
    return None

async def cache_cover(comic_id: str, image_url: str) -> Optional[str]:
    """
    Download, process, and save cover art to the cache directory as {comic_id}.jpg.
    Returns the cache file path if successful.
    """
    if not image_url or image_url.lower() == "none":
        return None

    os.makedirs(settings.CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(settings.CACHE_DIR, f"{comic_id}.jpg")

    # If already cached, just return the path
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        logger.fdebug(f"[Covers] Cover for {comic_id} is already cached.")
        return cache_path

    logger.info(f"[Covers] Downloading and caching cover for {comic_id} from {image_url}")
    raw_data = await download_image(image_url)
    if not raw_data:
        return None

    processed_data = scale_image(raw_data, target_width=600)
    if not processed_data:
        return None

    try:
        with open(cache_path, "wb") as f:
            f.write(processed_data)
        logger.info(f"[Covers] Successfully cached cover to {cache_path}")
        return cache_path
    except Exception as e:
        logger.error(f"[Covers] Failed to write cached cover for {comic_id}: {e}")
    return None

async def save_local_cover(comic_id: str, dest_dir: str, cache_path: Optional[str] = None, image_url: Optional[str] = None):
    """
    Save cover.jpg to the series directory.
    Uses cached cover if available, otherwise downloads/caches first.
    """
    if not settings.COMIC_COVER_LOCAL or not dest_dir:
        return

    os.makedirs(dest_dir, exist_ok=True)
    local_cover_path = os.path.join(dest_dir, "cover.jpg")

    if os.path.exists(local_cover_path) and os.path.getsize(local_cover_path) > 0:
        return

    # Ensure cache exists
    if not cache_path and image_url:
        cache_path = await cache_cover(comic_id, image_url)

    if not cache_path or not os.path.exists(cache_path):
        return

    try:
        import shutil
        shutil.copyfile(cache_path, local_cover_path)
        logger.info(f"[Covers] Saved local cover.jpg to {local_cover_path}")
    except Exception as e:
        logger.error(f"[Covers] Failed to copy local cover to {dest_dir}: {e}")

async def save_local_folder_thumbnail(comic_id: str, dest_dir: str, thumbnail_url: str):
    """
    Download and save folder.jpg to the series directory as folder thumbnail.
    """
    if not settings.COVER_FOLDER_LOCAL or not dest_dir or not thumbnail_url or thumbnail_url.lower() == "none":
        return

    os.makedirs(dest_dir, exist_ok=True)
    local_folder_path = os.path.join(dest_dir, "folder.jpg")

    if os.path.exists(local_folder_path) and os.path.getsize(local_folder_path) > 0:
        return

    logger.info(f"[Covers] Saving folder.jpg thumbnail to {local_folder_path}")
    raw_data = await download_image(thumbnail_url)
    if not raw_data:
        return

    processed_data = scale_image(raw_data, target_width=300)  # smaller for folder.jpg
    if not processed_data:
        return

    try:
        with open(local_folder_path, "wb") as f:
            f.write(processed_data)
        logger.info(f"[Covers] Successfully saved local folder.jpg to {local_folder_path}")
    except Exception as e:
        logger.error(f"[Covers] Failed to write folder.jpg to {dest_dir}: {e}")
