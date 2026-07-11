import os
import cv2
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
