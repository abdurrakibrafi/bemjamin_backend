from django.test import SimpleTestCase
import numpy as np
import trimesh

from scans.mesh_measurements import perform_all_measurements


class MeasurementRegressionTests(SimpleTestCase):
    def _build_box_mesh(self, width, height, length):
        vertices = np.array([
            [0, 0, 0],
            [width, 0, 0],
            [width, height, 0],
            [0, height, 0],
            [0, 0, length],
            [width, 0, length],
            [width, height, length],
            [0, height, length],
        ], dtype=float)
        faces = np.array([
            [0, 1, 2],
            [0, 2, 3],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [1, 2, 6],
            [1, 6, 5],
            [2, 3, 7],
            [2, 7, 6],
            [3, 0, 4],
            [3, 4, 7],
        ], dtype=int)
        return trimesh.Trimesh(vertices=vertices, faces=faces)

    def test_measurements_change_for_different_mesh_sizes(self):
        small_mesh = self._build_box_mesh(0.08, 0.12, 0.10)
        large_mesh = self._build_box_mesh(0.16, 0.24, 0.20)

        small_measurements = perform_all_measurements(small_mesh)
        large_measurements = perform_all_measurements(large_mesh)

        self.assertNotEqual(small_measurements.get('head_width'), large_measurements.get('head_width'))
        self.assertNotEqual(small_measurements.get('head_height'), large_measurements.get('head_height'))
        self.assertNotEqual(small_measurements.get('head_length'), large_measurements.get('head_length'))

    def test_circumference_slicing_on_cylinder(self):
        # Create a cylinder representing a head shape
        cylinder = trimesh.creation.cylinder(radius=0.08, height=0.3, sections=64)
        # Ensure it has dense geometry (> 100 vertices)
        self.assertTrue(len(cylinder.vertices) > 100)
        
        measurements = perform_all_measurements(cylinder)
        self.assertIn('head_circumference_A', measurements)
        self.assertGreater(measurements['head_circumference_A'], 0.0)

    def test_calibration_fails_gracefully_on_invalid_image(self):
        from scans.processing.calibration import estimate_physical_scale_from_photo
        # Non-existent file
        self.assertIsNone(estimate_physical_scale_from_photo("non_existent_file.jpg"))
        
        # Blank image (no face)
        import tempfile
        import cv2
        import os
        blank_img = np.zeros((100, 100, 3), dtype=np.uint8)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp:
            cv2.imwrite(temp.name, blank_img)
            temp_name = temp.name
            
        try:
            self.assertIsNone(estimate_physical_scale_from_photo(temp_name))
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    def test_perform_measurements_fallback(self):
        cylinder = trimesh.creation.cylinder(radius=0.08, height=0.3, sections=64)
        # Verify it runs without error with non-existent image
        measurements = perform_all_measurements(cylinder, front_image_path="invalid_image.jpg")
        self.assertIn('head_circumference_A', measurements)
        self.assertGreater(measurements['head_circumference_A'], 0.0)

    def test_all_fourteen_measurements_present_and_positive(self):
        cylinder = trimesh.creation.cylinder(radius=0.08, height=0.3, sections=64)
        measurements = perform_all_measurements(cylinder)
        
        expected_keys = [
            'head_width', 'head_height', 'head_length', 'ear_to_ear', 'eye_to_eye',
            'head_circumference_A', 'forehead_to_back_B', 'cross_measurement_C',
            'under_chin_D', 'eyebrow_to_earlobe_E', 'eye_corner_to_ear_F',
            'ear_height_G', 'ear_width_H', 'cheek_guard_clearance_L',
            'cheek_guard_height_M', 'cheek_guard_width_N'
        ]
        for key in expected_keys:
            self.assertIn(key, measurements, f"Missing expected key: {key}")
            self.assertGreater(measurements[key], 0.0, f"Key {key} must be greater than 0")

    def test_exif_focal_length_extraction(self):
        from scans.processing.pipeline import _get_image_focal_length
        # Test fallback on non-existent file returns None for KeenTools auto focal estimation
        focal = _get_image_focal_length("non_existent.jpg")
        self.assertIsNone(focal)

    def test_image_preprocessing_preserves_aspect_ratio_and_resizes_1600(self):
        from scans.processing.pipeline import _preprocess_and_save_temp
        from PIL import Image
        import io, os

        # Create a non-standard aspect ratio test image (e.g., 2400 x 1800, 4:3)
        img = Image.new('RGB', (2400, 1800), color=(128, 128, 128))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)

        saved_path = _preprocess_and_save_temp(img_bytes)
        try:
            with Image.open(saved_path) as processed:
                w, h = processed.size
                # Max dimension must be <= 1600
                self.assertLessEqual(max(w, h), 1600)
                # Aspect ratio must be preserved (4:3 ratio -> 1600 x 1200)
                self.assertEqual(w, 1600)
                self.assertEqual(h, 1200)
        finally:
            if os.path.exists(saved_path):
                os.remove(saved_path)

    def test_calibration_value_range_validation(self):
        from scans.serializers import ScanCreateSerializer
        serializer = ScanCreateSerializer()

        # Valid range (40 - 70 cm)
        self.assertEqual(serializer.validate_calibration_value(56.0), 56.0)

        # Out of range (< 40 or > 70 cm)
        from rest_framework import serializers
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_calibration_value(25.0)
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_calibration_value(85.0)

