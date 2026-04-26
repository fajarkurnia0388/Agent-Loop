#!/usr/bin/env python3
"""
Module to handle images pasted from the clipboard and their description with AI
"""
from typing import List, Tuple
from PIL import Image, ImageGrab
import threading

try:
    # Optional dependency for deduplication; fallback if unavailable
    import imagehash  # type: ignore
    HAS_IMAGEHASH = True
except Exception:
    HAS_IMAGEHASH = False

class ImageDescriptionManager:
    """Handles the queue of images and their descriptions"""
    
    def __init__(self):
        self.image_descriptions: List[str] = []
        self.pending_images: List[Image.Image] = []
        self.processed_images: List[Image.Image] = []  # Store processed images for preview
        self._thumb_cache: List[Tuple[Image.Image, Image.Image]] = []  # (full, thumb)
        self._hashes: set = set()
        self._lock = threading.Lock()
        self._max_images = 5
        self._max_total_bytes = 20 * 1024 * 1024  # ~20MB cap across all images
        
    def add_image_from_clipboard(self) -> bool:
        """
        Intenta obtener una imagen del portapapeles y la añade a la cola
        Returns: True si se añadió una imagen, False si no había imagen
        """
        try:
            # Intentar obtener imagen del portapapeles
            image = ImageGrab.grabclipboard()
            if image is not None and isinstance(image, Image.Image):
                with self._lock:
                    if not self._can_accept_more(image):
                        return False
                    if self._is_duplicate(image):
                        return True  # Silently ignore duplicates
                    self.pending_images.append(image)
                    self._add_to_thumb_cache(image)
                return True
            return False
        except Exception as e:
            print(f"Error al obtener imagen del portapapeles: {e}")
            return False
    
    
    
    def clear_descriptions(self) -> None:
        """Limpia todas las descripciones pendientes"""
        with self._lock:
            self.image_descriptions.clear()
            self.pending_images.clear()
            self.processed_images.clear()
            self._thumb_cache.clear()
            self._hashes.clear()

    # --- Helpers ---
    def _add_to_thumb_cache(self, img: Image.Image) -> None:
        try:
            thumb = img.copy()
            thumb.thumbnail((320, 320), Image.Resampling.LANCZOS)
            self._thumb_cache.append((img, thumb))
        except Exception:
            pass

    def _is_duplicate(self, img: Image.Image) -> bool:
        if not HAS_IMAGEHASH:
            return False
        try:
            h = imagehash.phash(img)
            if str(h) in self._hashes:
                return True
            self._hashes.add(str(h))
            return False
        except Exception:
            return False

    def add_pil_image(self, img: Image.Image) -> bool:
        """Adds a provided PIL image to the queue with dedup and caps.
        Returns True if added, False if rejected (cap/duplicate/error).
        """
        try:
            if img is None or not isinstance(img, Image.Image):
                return False
            with self._lock:
                if not self._can_accept_more(img):
                    return False
                if self._is_duplicate(img):
                    return True
                self.pending_images.append(img)
                self._add_to_thumb_cache(img)
            return True
        except Exception:
            return False

    def get_thumbnails(self) -> List[Image.Image]:
        """Returns thumbnail images for UI preview in FIFO order."""
        try:
            return [thumb for _full, thumb in self._thumb_cache]
        except Exception:
            return []

    def _can_accept_more(self, new_img: Image.Image) -> bool:
        if len(self.pending_images) + len(self.processed_images) >= self._max_images:
            return False
        try:
            # Rough size estimate via JPEG in-memory encoding
            from io import BytesIO
            buf = BytesIO()
            ni = new_img
            if ni.mode != 'RGB':
                ni = ni.convert('RGB')
            ni.save(buf, format='JPEG', quality=85, optimize=True)
            new_bytes = buf.tell()
        except Exception:
            new_bytes = 500000  # heuristic fallback
        total_est = new_bytes
        try:
            for im in self.pending_images + self.processed_images:
                buf = BytesIO()
                t = im
                if t.mode != 'RGB':
                    t = t.convert('RGB')
                t.save(buf, format='JPEG', quality=85, optimize=True)
                total_est += buf.tell()
        except Exception:
            pass
        return total_est <= self._max_total_bytes
    
image_manager = ImageDescriptionManager()