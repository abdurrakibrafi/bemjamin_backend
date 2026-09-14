import os
try:
    import cv2
except ImportError:
    cv2 = None
try:
    import mediapipe as mp
except ImportError:
    mp = None
import numpy as np
import urllib.request
import logging

logger = logging.getLogger(__name__)

# Average adult human interpupillary distance (IPD) is approximately 6.3 cm (63 mm)
AVERAGE_IPD_CM = 6.3

FACE_CASCADE_URL = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
EYE_CASCADE_URL = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_eye.xml"

def _ensure_cascade_files():
    """Ensure Haar cascade files exist in the local directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    face_path = os.path.join(current_dir, "haarcascade_frontalface_default.xml")
    eye_path = os.path.join(current_dir, "haarcascade_eye.xml")

    for url, path in [(FACE_CASCADE_URL, face_path), (EYE_CASCADE_URL, eye_path)]:
        if not os.path.exists(path):
            try:
                logger.info(f"Downloading Haar cascade from {url} to {path}...")
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                logger.error(f"Failed to download Haar cascade file {path}: {e}")
                
    return face_path, eye_path

def estimate_physical_scale_from_photo(image_path: str) -> float:
    """
    Detect the eyes using OpenCV Haar Cascade, measure the pixel distance between them,
    and calibrate using the average human Interpupillary Distance (6.3 cm).
    Returns:
        The estimated physical distance between the outer eye corners in centimeters
        (which is roughly 9.2 cm based on average face proportions, i.e., IPD of 6.3cm * 1.46 ratio),
        or None if detection fails.
    """
    if cv2 is None:
        logger.warning("OpenCV (cv2) is not available; skipping photo calibration.")
        return None

    face_xml, eye_xml = _ensure_cascade_files()
    if not os.path.exists(face_xml) or not os.path.exists(eye_xml):
        logger.error("Haar cascade XML files are missing.")
        return None

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        logger.error(f"Failed to load image from {image_path}")
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Load classifiers
    face_cascade = cv2.CascadeClassifier(face_xml)
    eye_cascade = cv2.CascadeClassifier(eye_xml)

    if face_cascade.empty() or eye_cascade.empty():
        logger.error("Failed to load Haar cascade classifiers.")
        return None

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
    if len(faces) == 0:
        logger.warning("No face detected by OpenCV Haar Cascade.")
        return None

    # Process the largest face detected
    (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
    face_roi_gray = gray[y:y+h, x:x+w]

    # Detect eyes within the face ROI
    eyes = eye_cascade.detectMultiScale(face_roi_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    
    # Filter and sort eyes by their horizontal coordinates (X)
    valid_eyes = []
    for (ex, ey, ew, eh) in eyes:
        # Eyes are usually in the upper half of the face ROI
        if ey < h * 0.55:
            center_x = x + ex + ew // 2
            center_y = y + ey + eh // 2
            valid_eyes.append((center_x, center_y))

    # We need exactly 2 eyes for pupillary distance calculation
    if len(valid_eyes) < 2:
        logger.warning(f"Detected {len(valid_eyes)} eyes, need at least 2.")
        return None

    # Sort eyes left-to-right
    valid_eyes = sorted(valid_eyes, key=lambda pt: pt[0])
    
    # Select the two eyes that are furthest apart or most symmetric (usually the left and right eye)
    # If more than 2, take the pair that corresponds to standard face proportions (distance ~ 0.45 * face width)
    best_pair = (valid_eyes[0], valid_eyes[-1])
    p1, p2 = best_pair

    # Calculate interpupillary distance in pixels
    ipd_px = np.linalg.norm(np.array(p1) - np.array(p2))
    if ipd_px <= 0:
        return None

    # Physical scale calculation (cm per pixel)
    px_to_cm = AVERAGE_IPD_CM / ipd_px

    # Anthropometric ratio: The distance between outer eye corners (ectocanthion)
    # is approximately 1.46 times the interpupillary distance (IPD).
    # i.e., average IPD is 6.3cm, average outer-corner distance is ~9.2cm.
    outer_eye_distance_cm = AVERAGE_IPD_CM * 1.46

    logger.info(f"OpenCV Calibration - IPD: {ipd_px:.1f}px, Ocular distance: {outer_eye_distance_cm:.2f}cm")
    return float(outer_eye_distance_cm)


def detect_facial_landmarks_2d(image_path: str):
    """
    Detect anatomical facial landmarks from front 2D photograph.
    Uses MediaPipe FaceMesh if installed.
    Falls back gracefully to OpenCV Haar Cascade if MediaPipe is not installed.
    
    Returns a dict with normalized relative coordinates (X, Y, Z), or None.
    """
    if not image_path or not os.path.exists(image_path):
        return None

    # 1. MediaPipe FaceMesh (precise 468+ 3D/2D face surface mesh)
    if mp is not None:
        try:
            mp_face_mesh = mp.solutions.face_mesh
            with mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5
            ) as face_mesh:
                img = cv2.imread(image_path) if cv2 is not None else None
                if img is not None:
                    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    results = face_mesh.process(rgb_img)
                    if results.multi_face_landmarks:
                        lms = results.multi_face_landmarks[0].landmark
                        # Key landmark indices in MediaPipe Face Mesh:
                        # 168: Glabella / Nasion (midpoint between eyebrows)
                        # 152: Menton / Chin bottom
                        # 33: Right eye outer canthus
                        # 263: Left eye outer canthus
                        # 234: Right ear tragus / root
                        # 454: Left ear tragus / root
                        # 10: Top of forehead / hairline
                        return {
                            'glabella_norm': (lms[168].x, lms[168].y, lms[168].z),
                            'chin_norm': (lms[152].x, lms[152].y, lms[152].z),
                            'right_eye_norm': (lms[33].x, lms[33].y, lms[33].z),
                            'left_eye_norm': (lms[263].x, lms[263].y, lms[263].z),
                            'right_tragus_norm': (lms[234].x, lms[234].y, lms[234].z),
                            'left_tragus_norm': (lms[454].x, lms[454].y, lms[454].z),
                            'forehead_norm': (lms[10].x, lms[10].y, lms[10].z),
                            'source': 'mediapipe'
                        }
        except Exception as e:
            logger.debug(f"MediaPipe landmark detection failed: {e}")

    # 2. Haar Cascade fallback
    if cv2 is not None:
        try:
            face_xml, eye_xml = _ensure_cascade_files()
            if os.path.exists(face_xml) and os.path.exists(eye_xml):
                img = cv2.imread(image_path)
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    fc = cv2.CascadeClassifier(face_xml)
                    faces = fc.detectMultiScale(gray, 1.1, 5, minSize=(100, 100))
                    if len(faces) > 0:
                        (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
                        ih, iw = img.shape[:2]
                        return {
                            'glabella_norm': ((x + w * 0.5) / iw, (y + h * 0.35) / ih, 0.0),
                            'chin_norm': ((x + w * 0.5) / iw, (y + h * 0.95) / ih, 0.0),
                            'right_eye_norm': ((x + w * 0.3) / iw, (y + h * 0.38) / ih, 0.0),
                            'left_eye_norm': ((x + w * 0.7) / iw, (y + h * 0.38) / ih, 0.0),
                            'source': 'haar_fallback'
                        }
        except Exception as e:
            logger.debug(f"Haar landmark fallback failed: {e}")

    return None
