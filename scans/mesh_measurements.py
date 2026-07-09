# import trimesh
# import numpy as np
# import traceback

# def _align_mesh_to_principal_axes(mesh):
#     print("--- Aligning mesh to principal axes ---")
#     mesh.apply_translation(-mesh.center_mass)
#     principal_axes = mesh.principal_inertia_vectors
    
#     transform_matrix = np.eye(4)
#     transform_matrix[:3, :3] = principal_axes.T
    
#     mesh.apply_transform(np.linalg.inv(transform_matrix))

#     if np.mean(mesh.vertices[:, 1]) < 0:
#         flip_matrix = trimesh.transformations.rotation_matrix(np.pi, [0, 0, 1])
#         mesh.apply_transform(flip_matrix)

#     principal_axes = mesh.principal_inertia_vectors
#     final_rotation = np.eye(4)
#     final_rotation[:3, :3] = principal_axes.T
#     mesh.apply_transform(final_rotation)
    
#     return mesh

# def _find_anatomical_landmarks(mesh):
#     vertices = mesh.vertices
#     landmarks = {
#         'chin_idx': np.argmin(vertices[:, 2]),
#         'nose_tip_idx': np.argmax(vertices[:, 1]),
#         'top_of_head_idx': np.argmax(vertices[:, 2]),
#         'back_of_head_idx': np.argmin(vertices[:, 1]),
#         'right_side_idx': np.argmax(vertices[:, 0]),
#         'left_side_idx': np.argmin(vertices[:, 0]),
#     }
    
#     extents = mesh.extents
#     try:
#         nose_tip = vertices[landmarks['nose_tip_idx']]
#         nasion_est = nose_tip + [0, -extents[1]*0.1, extents[1]*0.15]
#         _, _, nasion_idx = trimesh.proximity.closest_point(mesh, [nasion_est])
#         landmarks['nasion_idx'] = nasion_idx[0]
#     except:
#         landmarks['nasion_idx'] = landmarks['nose_tip_idx']
        
#     return landmarks

# def _calculate_surface_distance(mesh, start_idx, end_idx):
#     try:
#         path = trimesh.path.shortest_path(mesh, [start_idx], [end_idx])[0]
#         if len(path) > 1:
#             points = mesh.vertices[path]
#             return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))
#     except:
#         pass
#     return float(np.linalg.norm(mesh.vertices[start_idx] - mesh.vertices[end_idx]))

# def perform_all_measurements(mesh):
#     print("--- Performing detailed measurements ---")
#     try:
#         mesh = _align_mesh_to_principal_axes(mesh)
#         landmarks = _find_anatomical_landmarks(mesh)
#         extents = mesh.bounding_box.extents
        
#         raw_width = extents[0]
#         AVERAGE_HUMAN_HEAD_WIDTH_CM = 15.4
        
#         scale_factor = 1.0
#         if raw_width > 0:
#             scale_factor = AVERAGE_HUMAN_HEAD_WIDTH_CM / raw_width
        
#         head_width = extents[0] * scale_factor
#         head_length = extents[1] * scale_factor
#         head_height = extents[2] * scale_factor

#         a, b = head_width / 2, head_length / 2
#         head_circumference_A = np.pi * (3*(a+b) - np.sqrt((3*a + b) * (a + 3*b)))

#         raw_B = _calculate_surface_distance(mesh, landmarks['nasion_idx'], landmarks['back_of_head_idx'])
#         forehead_to_back_B = raw_B * scale_factor
        
#         raw_C = _calculate_surface_distance(mesh, landmarks['left_side_idx'], landmarks['right_side_idx'])
#         cross_measurement_C = raw_C * scale_factor
        

#         under_chin_D = (head_height * 0.8) + (head_width * 0.9)
#         eyebrow_to_earlobe_E = head_height * 0.52
#         eye_corner_to_ear_F = head_width * 0.48
        
#         ear_to_ear = head_width * 0.91 
#         eye_to_eye = head_width * 0.24

#         ear_height_G = head_height * 0.28

#         ear_width_H = ear_height_G * 0.55

#         cheek_guard_clearance_L = 2.5 

#         cheek_guard_height_M = head_height * 0.35

#         cheek_guard_width_N = head_width * 0.92
        
#         measurements = { 
#             'head_width': head_width, 
#             'head_height': head_height, 
#             'head_length': head_length,
#             'ear_to_ear': ear_to_ear,
#             'eye_to_eye': eye_to_eye,
#             'head_circumference_A': head_circumference_A, 
#             'forehead_to_back_B': forehead_to_back_B, 
#             'cross_measurement_C': cross_measurement_C, 
#             'under_chin_D': under_chin_D, 
#             'eyebrow_to_earlobe_E': eyebrow_to_earlobe_E, 
#             'eye_corner_to_ear_F': eye_corner_to_ear_F, 
#             'ear_height_G': ear_height_G, 
#             'ear_width_H': ear_width_H,
#             'cheek_guard_clearance_L': cheek_guard_clearance_L,
#             'cheek_guard_height_M': cheek_guard_height_M,
#             'cheek_guard_width_N': cheek_guard_width_N,
#         }
        
#         measurements = {k: round(float(v), 2) for k, v in measurements.items()}
#         return measurements

#     except Exception as e:
#         print(f"Measurement Error: {e}")
#         traceback.print_exc()
#         return {}



import trimesh
import numpy as np
import traceback


def _align_mesh_to_principal_axes(mesh):
    # KeenTools meshes are already aligned to canonical axes.
    # We bypass principal axes alignment to keep the anatomical orientation stable.
    return mesh


def _find_anatomical_landmarks(mesh):
    vertices = mesh.vertices
    extents = mesh.extents
    
    # Default landmarks based on argmin/argmax as fallback
    landmarks = {
        'chin_idx': np.argmin(vertices[:, 2]),
        'nose_tip_idx': np.argmax(vertices[:, 1]),
        'top_of_head_idx': np.argmax(vertices[:, 2]),
        'back_of_head_idx': np.argmin(vertices[:, 1]),
        'right_side_idx': np.argmax(vertices[:, 0]),
        'left_side_idx': np.argmin(vertices[:, 0]),
    }

    # Only perform advanced landmark heuristics if the mesh is dense enough
    # to represent a face (e.g. > 100 vertices).
    if len(vertices) > 100:
        try:
            top_z = vertices[landmarks['top_of_head_idx'], 2]
            
            # Nose is typically in the upper half of the head, to avoid neck/hair
            z_min_nose = top_z - extents[2] * 0.5
            nose_candidates = np.where(vertices[:, 2] > z_min_nose)[0]
            if len(nose_candidates) > 0:
                landmarks['nose_tip_idx'] = nose_candidates[np.argmax(vertices[nose_candidates, 1])]
            
            nose_z = vertices[landmarks['nose_tip_idx'], 2]
            upper_head_h = top_z - nose_z
            
            # Chin search band: below the nose tip
            chin_z_min = nose_z - 1.1 * upper_head_h
            chin_z_max = nose_z - 0.4 * upper_head_h
            chin_band_mask = (vertices[:, 2] > chin_z_min) & (vertices[:, 2] < chin_z_max)
            candidate_indices = np.where(chin_band_mask)[0]
            if len(candidate_indices) > 0:
                chin_local_idx = np.argmax(vertices[candidate_indices, 1])
                landmarks['chin_idx'] = candidate_indices[chin_local_idx]
                
            chin_z = vertices[landmarks['chin_idx'], 2]
            
            # Head vertices (above chin)
            head_indices = np.where(vertices[:, 2] > chin_z)[0]
            if len(head_indices) > 0:
                landmarks['left_side_idx'] = head_indices[np.argmin(vertices[head_indices, 0])]
                landmarks['right_side_idx'] = head_indices[np.argmax(vertices[head_indices, 0])]
                landmarks['back_of_head_idx'] = head_indices[np.argmin(vertices[head_indices, 1])]
        except Exception:
            pass # Keep defaults on error

    try:
        nose_tip = vertices[landmarks['nose_tip_idx']]
        nasion_est = nose_tip + [0, -extents[1] * 0.1, extents[2] * 0.15]
        _, _, nasion_idx = trimesh.proximity.closest_point(mesh, [nasion_est])
        landmarks['nasion_idx'] = nasion_idx[0]
    except Exception:
        landmarks['nasion_idx'] = landmarks['nose_tip_idx']

    # --- Eye outer corner estimate (both sides) ---
    # Anthropometric approximation: outer eye corner sits laterally offset from the
    # nasion, at roughly the same height, slightly anterior. We project an estimate
    # point outward from the nasion and snap it to the nearest surface vertex.
    nasion_pt = vertices[landmarks['nasion_idx']]
    for side, sign in (('right', 1), ('left', -1)):
        try:
            est = nasion_pt + [sign * extents[0] * 0.17, extents[1] * 0.02, -extents[2] * 0.02]
            _, _, idx = trimesh.proximity.closest_point(mesh, [est])
            landmarks[f'eye_outer_corner_{side}_idx'] = idx[0]
        except Exception:
            landmarks[f'eye_outer_corner_{side}_idx'] = landmarks['nasion_idx']

    return landmarks


def _find_ear_landmarks(mesh, landmarks, side='right'):
    """
    Locate approximate ear landmarks (top of ear, earlobe bottom, ear outer/lateral point)
    by searching a vertical band of the mesh on one side of the head for the
    laterally-protruding ear region, rather than guessing a fixed ratio of head height.

    This is a geometric heuristic (works best on reasonably dense, ear-detailed scans);
    on low-poly or ear-occluded scans it degrades gracefully to a proportional estimate.
    """
    vertices = mesh.vertices
    extents = mesh.extents

    chin_z = vertices[landmarks['chin_idx'], 2]
    top_z = vertices[landmarks['top_of_head_idx'], 2]
    head_h = top_z - chin_z

    # Ears typically sit between roughly eyebrow level and nose-base level
    band_low = chin_z + head_h * 0.25
    band_high = chin_z + head_h * 0.65

    x_thresh = extents[0] * 0.32  # only look well off the mid-sagittal plane
    z_mask = (vertices[:, 2] > band_low) & (vertices[:, 2] < band_high)

    if side == 'right':
        side_mask = vertices[:, 0] > x_thresh
    else:
        side_mask = vertices[:, 0] < -x_thresh

    mask = z_mask & side_mask
    candidate_idx = np.where(mask)[0]

    if len(candidate_idx) < 5:
        return None  # not enough surface detail in that band to trust a result

    candidates = vertices[candidate_idx]

    # The ear's outermost (most lateral) point in this band
    outer_local = np.argmax(np.abs(candidates[:, 0]))
    ear_outer_idx = candidate_idx[outer_local]
    outer_y = vertices[ear_outer_idx, 1]

    # Narrow to a front-back slice around the lateral point to isolate the ear itself
    y_slice_mask = np.abs(candidates[:, 1] - outer_y) < (extents[1] * 0.09)
    slice_idx = candidate_idx[y_slice_mask]
    if len(slice_idx) < 3:
        slice_idx = candidate_idx

    ear_top_idx = slice_idx[np.argmax(vertices[slice_idx, 2])]
    earlobe_bottom_idx = slice_idx[np.argmin(vertices[slice_idx, 2])]

    y_vals = vertices[slice_idx, 1]
    ear_front_to_back = float(np.max(y_vals) - np.min(y_vals))

    return {
        'ear_top_idx': ear_top_idx,
        'earlobe_bottom_idx': earlobe_bottom_idx,
        'ear_outer_idx': ear_outer_idx,
        'ear_depth_raw': ear_front_to_back,
    }


def _calculate_surface_distance(mesh, start_idx, end_idx):
    try:
        path = trimesh.path.shortest_path(mesh, [start_idx], [end_idx])[0]
        if len(path) > 1:
            points = mesh.vertices[path]
            return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))
    except Exception:
        pass
    return float(np.linalg.norm(mesh.vertices[start_idx] - mesh.vertices[end_idx]))


def _calculate_vertical_distance(mesh, ref_idx, target_idx):
    """Vertical (z-axis) distance between a reference-line height and a target point."""
    return float(abs(mesh.vertices[ref_idx, 2] - mesh.vertices[target_idx, 2]))


def _calculate_horizontal_distance(mesh, ref_idx, target_idx):
    """Front-back (y-axis) distance between a reference point and a target point."""
    return float(abs(mesh.vertices[ref_idx, 1] - mesh.vertices[target_idx, 1]))


def _estimate_mesh_scale_factor(mesh):
    """Estimate a conversion factor from mesh units to centimeters.

    Real 3D scans can be exported in meters, centimeters, or millimeters. We detect the scale
    heuristically based on the bounding box size:
    1. Meters (max_extent < 1.0) -> Convert to cm by multiplying by 100.0
    2. Millimeters (max_extent > 50) -> Convert to cm by multiplying by 0.1
    3. Centimeters (otherwise) -> Keep as-is (scale factor of 1.0)
    """
    extents = np.asarray(mesh.bounding_box.extents, dtype=float)
    if extents.size == 0:
        return 1.0

    max_extent = float(np.max(extents))
    if max_extent <= 0:
        return 1.0

    if max_extent < 1.0:
        return 100.0
    elif max_extent > 50.0:
        return 0.1
    return 1.0


def perform_all_measurements(mesh):
    print("--- Performing detailed measurements ---")
    try:
        mesh = _align_mesh_to_principal_axes(mesh)
        landmarks = _find_anatomical_landmarks(mesh)
        extents = mesh.bounding_box.extents

        scale_factor = _estimate_mesh_scale_factor(mesh)

        vertices = mesh.vertices
        if len(vertices) > 100:
            top_z = vertices[landmarks['top_of_head_idx'], 2]
            chin_z = vertices[landmarks['chin_idx'], 2]
            head_height = (top_z - chin_z) * scale_factor
            
            # Filter vertices above the chin to find actual head width and length (excluding shoulders)
            head_vertices = vertices[vertices[:, 2] > chin_z]
            if len(head_vertices) > 0:
                head_extents = np.max(head_vertices, axis=0) - np.min(head_vertices, axis=0)
                head_width = head_extents[0] * scale_factor
                head_length = head_extents[1] * scale_factor
            else:
                head_width = extents[0] * scale_factor
                head_length = extents[1] * scale_factor
        else:
            head_width = extents[0] * scale_factor
            head_length = extents[1] * scale_factor
            head_height = extents[2] * scale_factor

        # A: head circumference at eyebrow level (ellipse approximation)
        a, b = head_width / 2, head_length / 2
        head_circumference_A = np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b)))

        # B: nasion -> occipital prominence (geodesic, over the top)
        raw_B = _calculate_surface_distance(mesh, landmarks['nasion_idx'], landmarks['back_of_head_idx'])
        forehead_to_back_B = raw_B * scale_factor

        # C: left side -> right side, across the top (geodesic)
        raw_C = _calculate_surface_distance(mesh, landmarks['left_side_idx'], landmarks['right_side_idx'])
        cross_measurement_C = raw_C * scale_factor

        # D: under the chin, side to side (A-reference-line -> chin -> opposite A-reference-line)
        raw_D_left = _calculate_surface_distance(mesh, landmarks['left_side_idx'], landmarks['chin_idx'])
        raw_D_right = _calculate_surface_distance(mesh, landmarks['chin_idx'], landmarks['right_side_idx'])
        under_chin_D = (raw_D_left + raw_D_right) * scale_factor

        # Ear landmarks (real geometry search; falls back to ratio estimate if scan is too coarse)
        ear_right = _find_ear_landmarks(mesh, landmarks, side='right')
        ear_left = _find_ear_landmarks(mesh, landmarks, side='left')
        ear = ear_right if ear_right is not None else ear_left

        # --- FIX: ear_height_G is now averaged across both sides when both are
        # available, instead of relying on whichever single side happened to be
        # picked. This reduces scan-to-scan instability (e.g. 9.45cm vs 2.43cm
        # for the same person) caused by one side's landmark search picking up
        # noisy/occluded surface detail. ---
        ear_heights = []
        for e in (ear_right, ear_left):
            if e is not None:
                raw_h = abs(mesh.vertices[e['ear_top_idx'], 2] - mesh.vertices[e['earlobe_bottom_idx'], 2])
                ear_heights.append(raw_h)

        if ear is not None:
            # E: vertical distance, A reference line (eyebrow/nasion height) -> bottom of earlobe
            raw_E = _calculate_vertical_distance(mesh, landmarks['nasion_idx'], ear['earlobe_bottom_idx'])
            eyebrow_to_earlobe_E = raw_E * scale_factor

            # G: ear height (top of ear -> earlobe bottom), averaged over available sides
            raw_G = float(np.mean(ear_heights)) if ear_heights else 0.0
            ear_height_G = raw_G * scale_factor

            # H: ear width (front-back extent of the ear region)
            ear_width_H = ear['ear_depth_raw'] * scale_factor
        else:
            # Fallback if no usable ear detail was found on the scan
            eyebrow_to_earlobe_E = head_height * 0.52
            ear_height_G = head_height * 0.28
            ear_width_H = ear_height_G * 0.55

        # F: horizontal (front-back) distance, outer eye corner -> E reference line.
        # Use whichever side's ear landmark we found, matched to the same-side eye corner.
        eye_side = 'right' if ear_right is not None else 'left'
        eye_idx = landmarks.get(f'eye_outer_corner_{eye_side}_idx', landmarks['nasion_idx'])
        if ear is not None:
            raw_F = _calculate_horizontal_distance(mesh, eye_idx, ear['earlobe_bottom_idx'])
            eye_corner_to_ear_F = raw_F * scale_factor
        else:
            eye_corner_to_ear_F = head_width * 0.48

        # --- FIX: eye_to_eye now measured from the actual detected eye-corner
        # landmarks instead of a fixed head_width ratio (which previously gave
        # an identical, anatomically implausible 3.70cm on every scan). ---
        raw_eye_to_eye = _calculate_surface_distance(
            mesh,
            landmarks['eye_outer_corner_left_idx'],
            landmarks['eye_outer_corner_right_idx'],
        )
        eye_to_eye = raw_eye_to_eye * scale_factor

        # --- FIX: ear_to_ear now measured from the actual detected ear outer
        # landmarks (both sides) instead of a fixed head_width ratio. Falls
        # back to the ratio estimate only if one side's ear landmark could not
        # be found (coarse/occluded scan). ---
        if ear_right is not None and ear_left is not None:
            raw_ear_to_ear = _calculate_surface_distance(
                mesh, ear_left['ear_outer_idx'], ear_right['ear_outer_idx']
            )
            ear_to_ear = raw_ear_to_ear * scale_factor
        else:
            ear_to_ear = head_width * 0.91

        # NOTE: L, M, N are not part of the ATO Form measurement sheet (Fig. 1-4).
        # They appear to be internal/derived helmet cheek-guard design parameters
        # rather than direct anatomical measurements, so no mesh landmark exists
        # for them. Left as engineering-ratio estimates; flag for clarification
        # with whoever owns the cheek-guard spec if precise values are needed.
        cheek_guard_clearance_L = 2.5
        cheek_guard_height_M = head_height * 0.35
        cheek_guard_width_N = head_width * 0.92

        measurements = {
            'head_width': head_width,
            'head_height': head_height,
            'head_length': head_length,
            'ear_to_ear': ear_to_ear,
            'eye_to_eye': eye_to_eye,
            'head_circumference_A': head_circumference_A,
            'forehead_to_back_B': forehead_to_back_B,
            'cross_measurement_C': cross_measurement_C,
            'under_chin_D': under_chin_D,
            'eyebrow_to_earlobe_E': eyebrow_to_earlobe_E,
            'eye_corner_to_ear_F': eye_corner_to_ear_F,
            'ear_height_G': ear_height_G,
            'ear_width_H': ear_width_H,
            'cheek_guard_clearance_L': cheek_guard_clearance_L,
            'cheek_guard_height_M': cheek_guard_height_M,
            'cheek_guard_width_N': cheek_guard_width_N,
        }

        measurements = {k: round(float(v), 2) for k, v in measurements.items()}
        return measurements

    except Exception as e:
        print(f"Measurement Error: {e}")
        traceback.print_exc()
        return {}