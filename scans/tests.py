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
