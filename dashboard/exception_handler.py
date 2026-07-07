import logging
import traceback
import json
from datetime import datetime
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)

def _scrub_sensitive_data(data):
    SENSITIVE_KEYS = ['password', 'token', 'secret', 'confirm_password', 'new_password', 'old_password']
    if isinstance(data, dict):
        clean_data = {}
        for key, value in data.items():
            if any(sensitive_key in key.lower() for sensitive_key in SENSITIVE_KEYS):
                clean_data[key] = '[REDACTED]'
            else:
                clean_data[key] = _scrub_sensitive_data(value)
        return clean_data
    elif isinstance(data, list):
        return [_scrub_sensitive_data(item) for item in data]
    return data

def custom_exception_handler(exc, context):
    request = context.get('request')
    if request:
        user_info = f"User ID: {request.user.id} ({request.user.username})" if request.user.is_authenticated else "Anonymous User"
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        
        try:
            request_data = request.data
            if hasattr(request_data, 'dict'):
                request_data = request_data.dict()
            scrubbed_body = _scrub_sensitive_data(request_data)
            body_str = json.dumps(scrubbed_body, indent=2)
        except Exception:
            body_str = "Could not parse or scrub request body."

        error_trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        log_message = (
            f"\n--- UNHANDLED API EXCEPTION ---\n"
            f"User       : {user_info}\n"
            f"IP Address : {ip_address}\n"
            f"Request    : {request.method} {request.get_full_path()}\n"
            f"Body       : {body_str}\n"
            f"Exception  : {exc.__class__.__name__}: {exc}\n"
            f"Traceback  :\n{error_trace}"
            f"---------------------------------\n"
        )
        logger.error(log_message)
    response = exception_handler(exc, context)

    if response is not None:
        errors_payload = response.data
        message = "An error occurred."
        if isinstance(errors_payload, dict):
            for value in errors_payload.values():
                if isinstance(value, list) and value:
                    message = value[0]
                    break
                elif isinstance(value, str):
                    message = value
                    break
        elif isinstance(errors_payload, list) and errors_payload:
            message = errors_payload[0]

        response.data = {
            'success': False,
            'code': response.status_code,
            'message': message,
            'timestamp': int(datetime.now().timestamp()),
            'errors': errors_payload
        }

    return response