import requests
import time
import os
import tempfile
import trimesh
import traceback
import logging
from scipy.spatial import cKDTree
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

import cv2
import numpy as np
from PIL import Image, ImageOps

def _preprocess_and_save_temp(image_field):
    """
    Normalize image:
    1. Orient via EXIF transpose.
    2. Standardize to canonical portrait container with subtle padding if aspect ratio deviates.
    3. Apply adaptive contrast & lighting equalization (CLAHE) to balance single-sided shadows/flash.
    """
    temp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    try:
        with Image.open(image_field) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Standardize all images to identical canonical portrait container (576 x 1024)
            # This completely eliminates FOV and aspect ratio mismatches between front and side images
            img = ImageOps.pad(img, (576, 1024), color=(255, 255, 255))

            # Apply CLAHE on L-channel to balance harsh directional shadows/highlights
            img_np = np.array(img)
            lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            enhanced_np = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
            img = Image.fromarray(enhanced_np)

            img.save(temp_f.name, format="JPEG", quality=95)
    except Exception as e:
        logger.warning(f"Preprocessing fallback: {e}")
        image_field.seek(0)
        temp_f.write(image_field.read())
    temp_f.close()
    return temp_f.name

def symmetrize_3d_mesh(mesh, alpha=0.70):
    """
    Apply bilateral anatomical symmetry regularization across sagittal plane (X=0).
    Pairs left and right vertices, smoothing out single-sided perspective bulges or swelling.
    Uses cKDTree for fast and low-memory nearest-neighbor pairing.
    """
    try:
        vertices = mesh.vertices.copy()
        left_idx = np.where(vertices[:, 0] < -0.005)[0]
        right_idx = np.where(vertices[:, 0] > 0.005)[0]

        if len(left_idx) == 0 or len(right_idx) == 0:
            return mesh

        left_pts = vertices[left_idx]
        right_pts = vertices[right_idx]
        target_mirror = np.column_stack((np.abs(left_pts[:, 0]), left_pts[:, 1], left_pts[:, 2]))

        tree = cKDTree(right_pts)
        min_dists, min_idx = tree.query(target_mirror, k=1)
        paired_right = right_idx[min_idx]

        valid_mask = min_dists < 0.15
        valid_left = left_idx[valid_mask]
        valid_right = paired_right[valid_mask]

        for l, r in zip(valid_left, valid_right):
            vl = vertices[l]
            vr = vertices[r]
            
            avg_abs_x = 0.5 * (abs(vl[0]) + abs(vr[0]))
            avg_y = 0.5 * (vl[1] + vr[1])
            avg_z = 0.5 * (vl[2] + vr[2])
            
            vertices[l, 0] = (1 - alpha) * vl[0] + alpha * (-avg_abs_x)
            vertices[l, 1] = (1 - alpha) * vl[1] + alpha * avg_y
            vertices[l, 2] = (1 - alpha) * vl[2] + alpha * avg_z
            
            vertices[r, 0] = (1 - alpha) * vr[0] + alpha * (avg_abs_x)
            vertices[r, 1] = (1 - alpha) * vr[1] + alpha * avg_y
            vertices[r, 2] = (1 - alpha) * vr[2] + alpha * avg_z

        mid_idx = np.where(np.abs(vertices[:, 0]) <= 0.005)[0]
        vertices[mid_idx, 0] = 0.0

        mesh.vertices = vertices
    except Exception as e:
        logger.warning(f"Symmetry regularization exception: {e}")
    return mesh

def _get_image_focal_length(image_path):
    """Extract 35mm equivalent focal length from image EXIF if available."""
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
    return 35.0  # Standard human portrait focal length baseline

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

def _start_reconstruction(api_key, avatar_id, image_paths):
    url = _make_url(f"{avatar_id}/process")
    headers = _get_api_headers(api_key)
    headers['Content-Type'] = 'application/json'
    
    # Extract focal lengths if EXIF is preserved; otherwise use auto estimation
    focal_values = [_get_image_focal_length(p) for p in image_paths]
    has_valid_exif_focals = all(f is not None and f > 15 for f in focal_values)
    
    if has_valid_exif_focals:
        payload = {
            "focal_length_type": {
                "focal_length_type": "manual",
                "focal_length_values": focal_values
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

    logger.info(f"--- Step 3: Start Reconstruction (payload: {payload}) ---")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code not in [200, 400]: 
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
        if scan.image_front:
            temp_path = _preprocess_and_save_temp(scan.image_front)
            image_paths.append(temp_path)
            temp_files.append(temp_path)

        for img in scan.extra_images.all():
            temp_path = _preprocess_and_save_temp(img.image)
            image_paths.append(temp_path)
            temp_files.append(temp_path)

        if len(image_paths) < 1: raise PipelineError("No images")

        count = len(image_paths)
        
        avatar_id, urls = _init_avatar(api_key, count)
        
        for path, url in zip(image_paths, urls):
            _upload_photo(path, url)
            
        _start_reconstruction(api_key, avatar_id, image_paths)
        
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