from django.conf import settings
from urllib.parse import urljoin

def get_full_media_url(request, media_file):
    if not media_file or not hasattr(media_file, 'url'):
        return None

    if settings.USE_S3_STORAGE:
        return media_file.url

    return urljoin(str(settings.SERVER_BASE_URL), media_file.url)

    