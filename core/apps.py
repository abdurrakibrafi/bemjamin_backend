import json
import os
from django.apps import AppConfig
import firebase_admin
from firebase_admin import credentials
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        if not firebase_admin._apps:
            try:
                cred_path = settings.FCM_DJANGO_SETTINGS.get("FCM_CREDENTIALS")
                if not cred_path:
                    print("Warning: FCM_CREDENTIALS path is not set in settings. Firebase not initialized.")
                    return
                
                if isinstance(cred_path, dict):
                    cred = credentials.Certificate(cred_path)
                elif isinstance(cred_path, str) and cred_path.strip().startswith('{'):
                    cred_dict = json.loads(cred_path)
                    cred = credentials.Certificate(cred_dict)
                else:
                    cred = credentials.Certificate(cred_path)
                
                firebase_admin.initialize_app(cred)
                print("Firebase Admin SDK initialized successfully.")
            
            except Exception as e:
                print(f"CRITICAL ERROR: Failed to initialize Firebase Admin SDK: {e}")