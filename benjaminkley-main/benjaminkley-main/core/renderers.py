import ujson
from rest_framework.renderers import JSONRenderer
from datetime import datetime

class CustomJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get('response')

        if isinstance(data, dict) and 'success' in data:
            return ujson.dumps(data).encode('utf-8')

        is_error = response and response.status_code >= 400
        specific_message_found = None

        if isinstance(data, dict):
            if 'custom_meta' in data and 'message' in data.get('custom_meta', {}):
                specific_message_found = data['custom_meta']['message']
                del data['custom_meta']
            else:
                message_keys_in_priority = ['message', 'detail', 'status']
                for key in message_keys_in_priority:
                    if key in data and isinstance(data[key], str):
                        specific_message_found = data[key]
                        break

            if is_error and not specific_message_found:
                for value in data.values():
                    if isinstance(value, list) and value and isinstance(value[0], str):
                        specific_message_found = value[0]
                        break
                    elif isinstance(value, str):
                        specific_message_found = value
                        break
        
        if specific_message_found:
            message = specific_message_found
        else:
            message = "An error occurred." if is_error else "Request was successful."

        response_data = {
            'success': not is_error,
            'code': response.status_code if response else 200,
            'message': message,
            'timestamp': int(datetime.now().timestamp()),
            'data': data
        }

        return ujson.dumps(response_data).encode('utf-8')