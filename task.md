Task: Fix Firebase Admin SDK initialization to read from environment variable instead of file path

Context:
FCM_DJANGO_SETTINGS in settings.py currently points to a file path (serviceAccountKey.json) that doesn't exist on the production VPS. The actual service account JSON content is stored in the .env file under the key FIREBASE_SERVICE_ACCOUNT_PATH (name is misleading — it contains the full JSON content, not a path). We need to make Django read this JSON from the env var, write it to a temp file at runtime, and point FCM_CREDENTIALS to that temp file.

File to edit: benjaminkley/settings.py

Step 1: Find this existing block:

python
FCM_DJANGO_SETTINGS = {
    "APP_VERBOSE_NAME": "Benjamin Kley App",
    "FCM_SERVER_KEY": "[Legacy] Please use FCM_CREDENTIALS instead.",
    "ONE_DEVICE_PER_USER": False,
    "DELETE_INACTIVE_DEVICES": True,
    "FCM_CREDENTIALS": str(BASE_DIR / 'serviceAccountKey.json'),
}

Step 2: Replace it with:

python
import json
import tempfile

FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')

if FIREBASE_SERVICE_ACCOUNT_PATH:
    _fcm_creds_dict = json.loads(FIREBASE_SERVICE_ACCOUNT_PATH)
    _fcm_creds_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(_fcm_creds_dict, _fcm_creds_file)
    _fcm_creds_file.close()
    FCM_CREDENTIALS_PATH = _fcm_creds_file.name
else:
    FCM_CREDENTIALS_PATH = str(BASE_DIR / 'serviceAccountKey.json')

FCM_DJANGO_SETTINGS = {
    "APP_VERBOSE_NAME": "Benjamin Kley App",
    "FCM_SERVER_KEY": "[Legacy] Please use FCM_CREDENTIALS instead.",
    "ONE_DEVICE_PER_USER": False,
    "DELETE_INACTIVE_DEVICES": True,
    "FCM_CREDENTIALS": FCM_CREDENTIALS_PATH,
}

Important notes:

import json and import tempfile should only be added once at the top of the block (check if json is already imported elsewhere in the file to avoid duplicate imports — if so, just add import tempfile).
Do NOT remove the existing import os at the top of the file (already present).
Keep the fallback else branch — this ensures local development still works if someone has an actual serviceAccountKey.json file instead of the env var.
Don't touch any other settings in the file — this is a minimal targeted change, not a refactor.