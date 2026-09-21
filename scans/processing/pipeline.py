import requests
import time
import os
import tempfile
import trimesh
import traceback
import logging
try:
    import cv2
except ImportError:
    cv2 = None
try:
    import mediapipe as mp
except ImportError:
    mp = None
import numpy as np
from PIL import Image, ImageOps
from django.conf import settings
from django.core.files import File
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class PipelineError(Exception):
    pass

def _get_api_headers(api_key):
    return {'Authorization': f'Bearer {api_key}'}

def _make_url(path: str) -> str:
    base = getattr(settings, 'KEENTOOLS_API_BASE_URL', '').strip()
    if not base:
        raise PipelineError("KEENTOOLS_API_BASE_URL is not set.")
    
    if '/avatar' not in base:
        base = base.rstrip('/') + '/avatar/'
    elif base.endswith('/avatar'):
        base += '/'
    if not base.endswith('/'):
        base += '/'

    return urljoin(base, path)

def _init_avatar(api_key, img_count):
    url = _make_url("init") 
    headers = _get_api_headers(api_key)
    headers['Content-Type'] = 'application/json'
    payload = {"image_count": img_count}

    logger.info(f"--- Step 1: Init for {img_count} images ---")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
    except Exception as e:
        raise PipelineError(f"Init failed: {e}")
    
    data = response.json()
    return data.get("avatar_id"), data.get("img_urls")


def _detect_blur_score(img_pil):
    """
    Measure image sharpness using Laplacian variance.
    Returns a float score — lower means blurrier.
    Score < 60 is considered too blurry for reliable 3D reconstruction.
    Returns None if cv2 is unavailable.
    """
    if cv2 is None:
        return None
    try:
        gray = np.array(img_pil.convert('L'))
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return None


def _crop_head_with_padding(img_pil):
    """
    Detect face bounding box and crop the image so the full head
    (including top of hair) is always visible with generous padding:
      - 55% of face height added ABOVE (for hair/head top)
      - 25% of face width added on each SIDE
      - 20% of face height added BELOW (for chin/neck)

    Uses MediaPipe FaceDetection (accurate) then falls back to
    OpenCV Haar Cascade. Returns the original image if no face found.
    """
    if cv2 is None:
        return img_pil
    try:
        img_np = np.array(img_pil)
        h_img, w_img = img_np.shape[:2]

        # --- MediaPipe FaceDetection (preferred) ---
        if mp is not None:
            try:
                mp_fd = mp.solutions.face_detection
                with mp_fd.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
                    results = detector.process(img_np)
                    if results.detections:
                        bbox = results.detections[0].location_data.relative_bounding_box
                        x1 = int(bbox.xmin * w_img)
                        y1 = int(bbox.ymin * h_img)
                        bw = int(bbox.width  * w_img)
                        bh = int(bbox.height * h_img)

                        pad_top    = int(bh * 0.55)
                        pad_side   = int(bw * 0.25)
                        pad_bottom = int(bh * 0.20)

                        x1c = max(0, x1 - pad_side)
                        y1c = max(0, y1 - pad_top)
                        x2c = min(w_img, x1 + bw + pad_side)
                        y2c = min(h_img, y1 + bh + pad_bottom)

                        if (x2c - x1c) > 50 and (y2c - y1c) > 50:
                            return Image.fromarray(img_np[y1c:y2c, x1c:x2c])
            except Exception as e:
                logger.debug(f"MediaPipe face crop failed: {e}")

        # --- Haar Cascade fallback ---
        face_xml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "haarcascade_frontalface_default.xml")
        if os.path.exists(face_xml):
            gray_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            fc = cv2.CascadeClassifier(face_xml)
            faces = fc.detectMultiScale(gray_cv, 1.1, 5, minSize=(80, 80))
            if len(faces) > 0:
                (x, y, fw, fh) = max(faces, key=lambda f: f[2] * f[3])

                pad_top    = int(fh * 0.55)
                pad_side   = int(fw * 0.25)
                pad_bottom = int(fh * 0.20)

                x1c = max(0, x - pad_side)
                y1c = max(0, y - pad_top)
                x2c = min(w_img, x + fw + pad_side)
                y2c = min(h_img, y + fh + pad_bottom)

                if (x2c - x1c) > 50 and (y2c - y1c) > 50:
                    return Image.fromarray(img_np[y1c:y2c, x1c:x2c])
    except Exception as e:
        logger.debug(f"Head crop fallback: {e}")

    return img_pil  # original unchanged


def _neutralize_background(img_pil):
    """
    Use MediaPipe Selfie Segmentation to replace background with neutral
    mid-gray (128, 128, 128), helping KeenTools focus on head geometry
    without distracting background textures or colors.
    Falls back gracefully to original image if MediaPipe is unavailable.
    """
    if mp is None or cv2 is None:
        return img_pil
    try:
        mp_seg = mp.solutions.selfie_segmentation
        with mp_seg.SelfieSegmentation(model_selection=1) as segmenter:
            img_np = np.array(img_pil)  # already RGB
            results = segmenter.process(img_np)
            if results.segmentation_mask is not None:
                mask = results.segmentation_mask          # float32, 0.0-1.0
                mask_3ch = np.stack([mask] * 3, axis=-1) # H x W x 3
                # Neutral gray background avoids white-glare artifacts
                background = np.full_like(img_np, 128, dtype=np.uint8)
                blended = (img_np * mask_3ch + background * (1.0 - mask_3ch)).astype(np.uint8)
                return Image.fromarray(blended)
    except Exception as e:
        logger.debug(f"Background neutralization failed: {e}")
    return img_pil


def _preprocess_and_save_temp(image_field):
    """
    Full preprocessing pipeline for reliable 3D reconstruction:
    1.  EXIF-correct orientation.
    2.  Convert to RGB.
    3.  Face-aware head crop with generous padding (top of head never cut off).
    4.  Background neutralization via MediaPipe Selfie Segmentation.
    5.  CLAHE lighting normalization (L*a*b* channel) to fix uneven shadows.
    6.  Downscale to max 1600 px on longest edge for upload speed.
    7.  Save as high-quality JPEG.
    """
    temp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    try:
        with Image.open(image_field) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Step 1: Blur check — warn but do NOT reject (let KeenTools decide)
            blur_score = _detect_blur_score(img)
            if blur_score is not None and blur_score < 60:
                logger.warning(f"Image appears blurry (Laplacian score={blur_score:.1f} < 60). "
                               f"3D quality may be reduced.")

            # Step 2: Crop to head with padding so top of head is included
            img = _crop_head_with_padding(img)

            # Step 3: Replace background with neutral gray
            img = _neutralize_background(img)

            # Step 4: CLAHE on L-channel to fix harsh shadows / uneven lighting
            if cv2 is not None:
                img_np = np.array(img)
                lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                cl = clahe.apply(l)
                enhanced_np = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2RGB)
                img = Image.fromarray(enhanced_np)
            else:
                img = ImageOps.autocontrast(img)

            # Step 5: Downscale if too large
            if max(img.size) > 1600:
                img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

            img.save(temp_f.name, format="JPEG", quality=95)
    except Exception as e:
        logger.warning(f"Preprocessing fallback to raw upload: {e}")
        image_field.seek(0)
        temp_f.write(image_field.read())
    temp_f.close()
    return temp_f.name


def _get_image_focal_length(image_path):
    """Extract 35mm equivalent focal length from image EXIF if available; otherwise return None."""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif:
                # 41989: FocalLengthIn35mmFilm
                focal_35 = exif.get(41989)
                if focal_35 and float(focal_35) > 10:
                    return float(focal_35)
                # 37386: FocalLength
                focal_raw = exif.get(37386)
                if focal_raw:
                    val = float(focal_raw[0]) / float(focal_raw[1]) if isinstance(focal_raw, tuple) else float(focal_raw)
                    if val > 10:
                        return val
    except Exception:
        pass
    return None  # Let KeenTools estimate focal length automatically if EXIF is absent

def _upload_photo(image_path, upload_url):
    logger.info(f"--- Step 2: Uploading {os.path.basename(image_path)} ---")
    if not os.path.exists(image_path):
        raise PipelineError(f"File not found: {image_path}")

    with open(image_path, 'rb') as f:
        img_data = f.read()
    
    try:
        res = requests.put(upload_url, data=img_data, headers={"Content-Type": "image/jpeg"}, timeout=120)
        if res.status_code not in [200, 201]: 
            raise PipelineError(f"S3 upload failed: {res.status_code}")
    except Exception as e:
        raise PipelineError(f"Upload failed: {e}")

def _start_reconstruction(api_key, avatar_id, focal_lengths=None):
    """
    Start KeenTools 3D reconstruction.
    focal_lengths: pre-extracted list of float|None values from ORIGINAL images
                   (must be extracted before preprocessing strips EXIF data).
    """
    url = _make_url(f"{avatar_id}/process")
    headers = _get_api_headers(api_key)
    headers['Content-Type'] = 'application/json'

    # Use pre-extracted focal lengths (from original files, before EXIF is lost)
    has_valid_focals = (
        focal_lengths is not None
        and len(focal_lengths) > 0
        and all(f is not None and f > 15 for f in focal_lengths)
    )

    if has_valid_focals:
        payload = {
            "focal_length_type": {
                "focal_length_type": "manual",
                "focal_length_values": focal_lengths
            },
            "expressions_enabled": False
        }
    else:
        payload = {
            "focal_length_type": {
                "focal_length_type": "auto"
            },
            "expressions_enabled": False
        }

    logger.info(f"--- Step 3: Start Reconstruction (focal_valid={has_valid_focals}, payload={payload}) ---")
    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code not in [200, 202]:
        raise PipelineError(f"Start failed: {response.status_code} - {response.text}")

def _poll_for_completion(api_key, avatar_id, timeout=600):
    status_url = _make_url(f"{avatar_id}/get-status")
    headers = _get_api_headers(api_key)
    headers['Content-Type'] = 'application/json'
    start_time = time.time()
    
    logger.info(f"--- Step 4: Polling Status ---")
    while time.time() - start_time < timeout:
        try:
            response = requests.get(status_url, headers=headers, timeout=15)
            data = response.json()
            status = data.get('status', '').lower()
            
            if status == 'completed':
                logger.info("--- Completed ---")
                return
            elif status == 'failed':
                error_msg = data.get('data', {}).get('error_message', 'Unknown error')
                raise PipelineError(f"Job failed: {error_msg}")
            
            time.sleep(6)
        except PipelineError:
            raise
        except Exception:
            time.sleep(6)
    raise PipelineError("Job timed out.")

def _download_file_logic(api_key, avatar_id, params, timeout=180):
    url = _make_url(f"{avatar_id}/get-3d-model")
    headers = _get_api_headers(api_key)
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 425:
                time.sleep(2)
                continue
                
            if response.status_code != 200:
                raise PipelineError(f"API Error {response.status_code}: {response.text}")

            json_resp = response.json()
            event = json_resp.get("event")
            data = json_resp.get("data", {})

            if event == "retry-after":
                wait_time = data.get("time_sec", 2)
                time.sleep(wait_time)
                continue
            
            elif event == "redirect":
                download_url = data.get("url")
                if not download_url:
                    raise PipelineError("Redirect event received but no URL provided.")
                
                file_res = requests.get(download_url, timeout=180)
                file_res.raise_for_status()
                return file_res.content
            
            else:
                raise PipelineError(f"Unknown event type: {event}")

        except requests.RequestException as e:
            time.sleep(2)
            if time.time() - start_time > timeout:
                raise PipelineError(f"Download error: {e}")

    raise PipelineError("Download timed out.")

def _download_obj_for_math(api_key, avatar_id):
    logger.info("--- Downloading OBJ for Measurements ---")
    
    params = {
        "mesh_format": "obj",
        "mesh_lod": "high_poly"
    }
    
    file_content = _download_file_logic(api_key, avatar_id, params)
    
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".obj")
    temp.write(file_content)
    temp.close()
    return temp.name

def _download_glb_for_display(scan, api_key, avatar_id):
    logger.info("--- Downloading Textured GLB for Display ---")
    
    params = {
        "mesh_format": "glb",
        "mesh_lod": "high_poly",
        "texture": "jpg"
    }
    
    file_content = _download_file_logic(api_key, avatar_id, params)
    
    temp_path = None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".glb") as temp_file:
        temp_file.write(file_content)
        temp_path = temp_file.name
    
    with open(temp_path, 'rb') as f:
        scan.processed_3d_model.save(f"{scan.id}_model.glb", File(f), save=True)
    
    os.remove(temp_path)

def run_full_scan_pipeline(scan_id):
    from scans.models import Scan
    scan = Scan.objects.get(id=scan_id)
    api_key = getattr(settings, 'KEENTOOLS_SECRET_KEY', None)
    if not api_key: raise PipelineError("Key missing")

    image_paths = []
    temp_files = []
    obj_temp_path = None 

    try:
        # ── STEP A: Extract EXIF focal lengths from ORIGINAL files BEFORE
        #            preprocessing strips EXIF data. This fixes the bug where
        #            PIL re-saving loses EXIF and KeenTools always falls back
        #            to auto focal length estimation.
        original_focal_lengths = []

        if scan.image_front:
            scan.image_front.open()   # ensure file pointer is at start
            fl = _get_image_focal_length(scan.image_front)
            original_focal_lengths.append(fl)
            scan.image_front.seek(0)

        for img in scan.extra_images.order_by('order').all():
            img.image.open()
            fl = _get_image_focal_length(img.image)
            original_focal_lengths.append(fl)
            img.image.seek(0)

        logger.info(f"Pre-extracted focal lengths: {original_focal_lengths}")

        # ── STEP B: Preprocess and save temp files (EXIF may be lost here)
        if scan.image_front:
            scan.image_front.seek(0)
            temp_path = _preprocess_and_save_temp(scan.image_front)
            image_paths.append(temp_path)
            temp_files.append(temp_path)

        for img in scan.extra_images.order_by('order').all():
            img.image.seek(0)
            temp_path = _preprocess_and_save_temp(img.image)
            image_paths.append(temp_path)
            temp_files.append(temp_path)

        if len(image_paths) < 1:
            raise PipelineError("No images to process")

        count = len(image_paths)


        avatar_id, urls = _init_avatar(api_key, count)

        if len(urls) != count:
            raise PipelineError(f"URL count mismatch: got {len(urls)} URLs for {count} images")

        for path, url in zip(image_paths, urls):
            _upload_photo(path, url)

        _start_reconstruction(api_key, avatar_id, focal_lengths=original_focal_lengths)
        
        _poll_for_completion(api_key, avatar_id)
        
        obj_temp_path = _download_obj_for_math(api_key, avatar_id)
        
        logger.info("Measuring OBJ...")
        mesh = trimesh.load(obj_temp_path, file_type='obj', force='mesh')
        from ..mesh_measurements import perform_all_measurements
        cal_val = float(scan.calibration_value) if scan.calibration_value else None
        measurements = perform_all_measurements(
            mesh,
            front_image_path=image_paths[0],
            calibration_type=scan.calibration_type,
            calibration_value=cal_val
        )
        
        _download_glb_for_display(scan, api_key, avatar_id)
        
        return {"measurements": measurements}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise PipelineError(str(e))
        
    finally:
        if obj_temp_path and os.path.exists(obj_temp_path):
            os.remove(obj_temp_path)
        for path in temp_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Could not remove temporary image file {path}: {e}")