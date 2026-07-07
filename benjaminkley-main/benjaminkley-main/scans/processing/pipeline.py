import requests
import time
import os
import tempfile
import trimesh
import traceback
import logging
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

def _start_reconstruction(api_key, avatar_id, img_count):
    url = _make_url(f"{avatar_id}/process")
    headers = _get_api_headers(api_key)
    headers['Content-Type'] = 'application/json'
    
    payload = {
        "focal_length_type": {
            "focal_length_type": "manual",
            "focal_length_values": [28.0] * img_count
        },
        "expressions_enabled": False
    }

    logger.info(f"--- Step 3: Start Reconstruction ---")
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
    if scan.image_front: image_paths.append(scan.image_front.path)
    for img in scan.extra_images.all(): image_paths.append(img.image.path)
    
    if len(image_paths) < 1: raise PipelineError("No images")

    obj_temp_path = None 

    try:
        count = len(image_paths)
        
        avatar_id, urls = _init_avatar(api_key, count)
        
        for path, url in zip(image_paths, urls):
            _upload_photo(path, url)
            
        _start_reconstruction(api_key, avatar_id, count)
        
        _poll_for_completion(api_key, avatar_id)
        
        obj_temp_path = _download_obj_for_math(api_key, avatar_id)
        
        logger.info("Measuring OBJ...")
        mesh = trimesh.load(obj_temp_path, file_type='obj', force='mesh')
        from ..mesh_measurements import perform_all_measurements
        measurements = perform_all_measurements(mesh)
        
        _download_glb_for_display(scan, api_key, avatar_id)
        
        return {"measurements": measurements}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise PipelineError(str(e))
        
    finally:
        if obj_temp_path and os.path.exists(obj_temp_path):
            os.remove(obj_temp_path)