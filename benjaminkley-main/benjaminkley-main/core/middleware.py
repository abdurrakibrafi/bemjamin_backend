import time
import logging

logger = logging.getLogger(__name__)

class LatencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration = time.time() - start_time
        response["X-Response-Time"] = f"{duration:.4f}s"
        
        # Log slow requests (> 1s because 3D processing can be slow)
        if duration > 1.0:
            logger.warning(f"Slow request detected: {request.path} took {duration:.4f}s")
            
        return response
