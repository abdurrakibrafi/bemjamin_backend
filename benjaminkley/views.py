from django.http import FileResponse, Http404
import os
from django.conf import settings

def serve_obj_file(request, filename):
    obj_path = os.path.join(settings.MEDIA_ROOT, 'scans', 'outputs', filename)
    
    if not os.path.exists(obj_path):
        raise Http404("3D Model file not found")
        
    content_type = 'application/octet-stream'
    if filename.lower().endswith('.glb'):
        content_type = 'model/gltf-binary'
        
    response = FileResponse(open(obj_path, 'rb'), content_type=content_type)
    response['Access-Control-Allow-Origin'] = '*'
    return response