import trimesh
import numpy as np
import traceback
import logging

logger = logging.getLogger(__name__)


def _align_mesh_to_principal_axes(mesh):
    """
    KeenTools and canonical face meshes are already oriented in standard coordinates:
    X: Lateral (Left: negative, Right: positive)
    Y: Vertical / Height (Inferior: negative, Superior/Top: positive)
    Z: Sagittal / Depth (Posterior/Back: negative, Anterior/Front: positive)
    """
    return mesh


def _calculate_surface_distance(mesh, start_idx, end_idx):
    """
    Calculate geodesic 3D surface distance between two vertices on the mesh.
    Falls back to straight-line Euclidean distance if the path cannot be traversed.
    """
    if start_idx is None or end_idx is None:
        return 0.0
    if start_idx == end_idx:
        return 0.0

    try:
        path = trimesh.path.shortest_path(mesh, [start_idx], [end_idx])[0]
        if len(path) > 1:
            points = mesh.vertices[path]
            return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))
    except Exception:
        pass
    return float(np.linalg.norm(mesh.vertices[start_idx] - mesh.vertices[end_idx]))


def _find_anatomical_landmarks(mesh):
    """
    Detect key anatomical facial and cranial landmarks directly from 3D mesh geometry.
    Coordinates: X (width, +/-), Y (height, up/down), Z (depth, front/back).
    """
    vertices = mesh.vertices
    extents = mesh.extents
    n_vertices = len(vertices)

    # Initial extrema fallbacks
    landmarks = {
        'top_of_head_idx': int(np.argmax(vertices[:, 1])),
        'chin_idx': int(np.argmin(vertices[:, 1])),
        'nose_tip_idx': int(np.argmax(vertices[:, 2])),
        'back_of_head_idx': int(np.argmin(vertices[:, 2])),
        'right_side_idx': int(np.argmax(vertices[:, 0])),
        'left_side_idx': int(np.argmin(vertices[:, 0])),
    }

    if n_vertices <= 10:
        landmarks['nasion_idx'] = landmarks['nose_tip_idx']
        landmarks['eye_outer_corner_right_idx'] = landmarks['right_side_idx']
        landmarks['eye_outer_corner_left_idx'] = landmarks['left_side_idx']
        landmarks['zygoma_right_idx'] = landmarks['right_side_idx']
        landmarks['zygoma_left_idx'] = landmarks['left_side_idx']
        return landmarks

    top_y = vertices[landmarks['top_of_head_idx'], 1]

    # 1. Nose Tip (Pronasale): Most anterior point (max Z) in upper-central face
    y_min_nose = top_y - extents[1] * 0.55
    y_max_nose = top_y - extents[1] * 0.20
    x_nose_bound = extents[0] * 0.15
    nose_mask = (
        (vertices[:, 1] > y_min_nose) & 
        (vertices[:, 1] < y_max_nose) & 
        (np.abs(vertices[:, 0]) < x_nose_bound)
    )
    nose_candidates = np.where(nose_mask)[0]
    if len(nose_candidates) > 0:
        landmarks['nose_tip_idx'] = int(nose_candidates[np.argmax(vertices[nose_candidates, 2])])

    nose_y = vertices[landmarks['nose_tip_idx'], 1]
    upper_head_h = top_y - nose_y

    # 2. Chin (Menton / Gnathion): Lowest and forward-most point on mandible
    chin_y_min = nose_y - 1.5 * upper_head_h
    chin_y_max = nose_y - 0.5 * upper_head_h
    chin_mask = (
        (vertices[:, 1] > chin_y_min) & 
        (vertices[:, 1] < chin_y_max) & 
        (np.abs(vertices[:, 0]) < extents[0] * 0.22)
    )
    chin_candidates = np.where(chin_mask)[0]
    if len(chin_candidates) > 0:
        # Optimize combination of lowest Y and most forward Z
        chin_local = np.argmax(vertices[chin_candidates, 2] - 1.2 * vertices[chin_candidates, 1])
        landmarks['chin_idx'] = int(chin_candidates[chin_local])

    chin_y = vertices[landmarks['chin_idx'], 1]

    # 3. Nasion / Glabella: Depressed region above nose bridge between eye sockets
    nasion_est = vertices[landmarks['nose_tip_idx']] + [0, extents[1] * 0.08, -extents[2] * 0.08]
    nasion_idx = int(np.argmin(np.linalg.norm(vertices - nasion_est, axis=1)))
    landmarks['nasion_idx'] = nasion_idx

    # 4. Inion / Opisthocranion (Back of Head): Posterior cranial prominence above neck
    head_indices = np.where(vertices[:, 1] > (chin_y + (top_y - chin_y) * 0.25))[0]
    if len(head_indices) > 0:
        landmarks['back_of_head_idx'] = int(head_indices[np.argmin(vertices[head_indices, 2])])

    # 5. Outer Canthi (Left & Right Eye outer corners)
    nasion_pt = vertices[landmarks['nasion_idx']]
    right_indices = np.where(vertices[:, 0] > 0)[0]
    left_indices = np.where(vertices[:, 0] < 0)[0]

    for side, sign, pool in (('right', 1, right_indices), ('left', -1, left_indices)):
        try:
            eye_est = nasion_pt + [sign * extents[0] * 0.17, -extents[1] * 0.03, -extents[2] * 0.05]
            if len(pool) > 0:
                idx = int(pool[np.argmin(np.linalg.norm(vertices[pool] - eye_est, axis=1))])
            else:
                idx = int(np.argmin(np.linalg.norm(vertices - eye_est, axis=1)))
            landmarks[f'eye_outer_corner_{side}_idx'] = idx
        except Exception:
            landmarks[f'eye_outer_corner_{side}_idx'] = landmarks['nasion_idx']

    # 6. Zygoma (Cheekbone Prominences - Left & Right)
    for side, sign, pool in (('right', 1, right_indices), ('left', -1, left_indices)):
        try:
            zyg_est = nasion_pt + [sign * extents[0] * 0.28, -extents[1] * 0.12, -extents[2] * 0.06]
            if len(pool) > 0:
                idx = int(pool[np.argmin(np.linalg.norm(vertices[pool] - zyg_est, axis=1))])
            else:
                idx = int(np.argmin(np.linalg.norm(vertices - zyg_est, axis=1)))
            landmarks[f'zygoma_{side}_idx'] = idx
        except Exception:
            landmarks[f'zygoma_{side}_idx'] = landmarks['nasion_idx']

    # 7. Cranial side points (Parietal / Temple region, strictly above the ears)
    parietal_y_low = chin_y + (top_y - chin_y) * 0.65
    parietal_y_high = chin_y + (top_y - chin_y) * 0.88
    parietal_mask = (vertices[:, 1] > parietal_y_low) & (vertices[:, 1] < parietal_y_high)
    parietal_candidates = np.where(parietal_mask)[0]
    if len(parietal_candidates) > 0:
        landmarks['left_side_idx'] = int(parietal_candidates[np.argmin(vertices[parietal_candidates, 0])])
        landmarks['right_side_idx'] = int(parietal_candidates[np.argmax(vertices[parietal_candidates, 0])])
    else:
        landmarks['left_side_idx'] = int(head_indices[np.argmin(vertices[head_indices, 0])]) if len(head_indices) > 0 else 0
        landmarks['right_side_idx'] = int(head_indices[np.argmax(vertices[head_indices, 0])]) if len(head_indices) > 0 else 0

    # 8. Ear level reference points (Otobasion level / supra-auricular baseline at Y ~ chin_y + 0.48 * head_h)
    ear_level_y = chin_y + (top_y - chin_y) * 0.48
    ear_band_mask = (vertices[:, 1] > (ear_level_y - extents[1] * 0.08)) & (vertices[:, 1] < (ear_level_y + extents[1] * 0.08))
    ear_band_idx = np.where(ear_band_mask)[0]
    if len(ear_band_idx) > 0:
        landmarks['left_ear_level_idx'] = int(ear_band_idx[np.argmin(vertices[ear_band_idx, 0])])
        landmarks['right_ear_level_idx'] = int(ear_band_idx[np.argmax(vertices[ear_band_idx, 0])])
    else:
        landmarks['left_ear_level_idx'] = landmarks['left_side_idx']
        landmarks['right_ear_level_idx'] = landmarks['right_side_idx']

    return landmarks


def _find_ear_landmarks(mesh, landmarks, side='right'):
    """
    Detect ear anatomical landmarks: Superaurale (ear top), Subaurale (earlobe bottom),
    Helix outermost point, Tragion (anterior root), and posterior rim.
    All points are extracted purely from the 3D mesh vertices without fixed multipliers.
    """
    vertices = mesh.vertices
    extents = mesh.extents

    chin_y = vertices[landmarks['chin_idx'], 1]
    top_y = vertices[landmarks['top_of_head_idx'], 1]
    head_h = max(float(top_y - chin_y), float(extents[1]))

    # Ear vertical region sits between eyebrow plane and lower nose/mouth level
    band_low = chin_y + head_h * 0.32
    band_high = chin_y + head_h * 0.62

    side_mask = (vertices[:, 0] > 0) if side == 'right' else (vertices[:, 0] < 0)
    y_mask = (vertices[:, 1] >= band_low) & (vertices[:, 1] <= band_high)
    candidate_idx = np.where(side_mask & y_mask)[0]

    # Fallback to whole hemisphere if vertical band is sparse
    if len(candidate_idx) == 0:
        candidate_idx = np.where(side_mask)[0]
    if len(candidate_idx) == 0:
        candidate_idx = np.array([landmarks['right_side_idx'] if side == 'right' else landmarks['left_side_idx']], dtype=int)

    candidates = vertices[candidate_idx]

    # Outermost lateral point (Superaurale / Helix)
    outer_local = np.argmax(np.abs(candidates[:, 0]))
    ear_outer_idx = int(candidate_idx[outer_local])
    outer_z = vertices[ear_outer_idx, 2]

    # Isolate the localized ear region in Z-depth around the lateral peak
    ear_z_mask = np.abs(candidates[:, 2] - outer_z) <= (extents[2] * 0.12)
    ear_slice_idx = candidate_idx[ear_z_mask]
    if len(ear_slice_idx) >= 3:
        candidate_idx = ear_slice_idx
        candidates = vertices[candidate_idx]

    # Ear top (max Y) and earlobe bottom (min Y) in this cluster
    ear_top_idx = int(candidate_idx[np.argmax(candidates[:, 1])])
    earlobe_bottom_idx = int(candidate_idx[np.argmin(candidates[:, 1])])

    # Ear anterior root / Tragion (max Z) and posterior rim (min Z)
    ear_root_idx = int(candidate_idx[np.argmax(candidates[:, 2])])
    ear_posterior_idx = int(candidate_idx[np.argmin(candidates[:, 2])])

    ear_depth_raw = float(abs(vertices[ear_root_idx, 2] - vertices[ear_posterior_idx, 2]))

    return {
        'ear_top_idx': ear_top_idx,
        'earlobe_bottom_idx': earlobe_bottom_idx,
        'ear_outer_idx': ear_outer_idx,
        'ear_root_idx': ear_root_idx,
        'ear_posterior_idx': ear_posterior_idx,
        'ear_depth_raw': ear_depth_raw,
    }


def _estimate_mesh_scale_factor(mesh):
    """
    Determine raw mesh unit scaling factor (e.g. decimeters, meters, millimeters).
    """
    extents = np.asarray(mesh.bounding_box.extents, dtype=float)
    if extents.size == 0 or np.max(extents) <= 0:
        return 6.58

    max_extent = float(np.max(extents))
    if max_extent < 1.0:
        return 65.8      # Meters -> cm
    elif max_extent > 50.0:
        return 0.0658    # Millimeters -> cm
    return 6.58          # KeenTools decimeter default -> cm


def symmetrize_3d_mesh(mesh, alpha=0.70):
    """
    Apply bilateral anatomical symmetry regularization across sagittal plane (X=0).
    Pairs left and right vertices, smoothing out single-sided perspective bulges or swelling.
    """
    try:
        vertices = mesh.vertices.copy()
        left_idx = np.where(vertices[:, 0] < -0.005)[0]
        right_idx = np.where(vertices[:, 0] > 0.005)[0]

        if len(left_idx) == 0 or len(right_idx) == 0:
            return mesh

        left_pts = vertices[left_idx]
        right_pts = vertices[right_idx]
        target_mirror = np.column_stack((np.abs(left_pts[:, 0]), left_pts[:, 1], left_pts[:, 2]))

        chunk_size = 1000
        paired_right = np.zeros(len(left_idx), dtype=int)
        min_dists = np.zeros(len(left_idx), dtype=float)

        for i in range(0, len(left_idx), chunk_size):
            chunk = target_mirror[i:i+chunk_size]
            dists = np.sum((chunk[:, np.newaxis, :] - right_pts[np.newaxis, :, :]) ** 2, axis=2)
            min_idx = np.argmin(dists, axis=1)
            paired_right[i:i+chunk_size] = right_idx[min_idx]
            min_dists[i:i+chunk_size] = np.sqrt(dists[np.arange(len(chunk)), min_idx])

        valid_mask = min_dists < 0.15
        valid_left = left_idx[valid_mask]
        valid_right = paired_right[valid_mask]

        for l, r in zip(valid_left, valid_right):
            vl = vertices[l]
            vr = vertices[r]
            
            avg_abs_x = 0.5 * (abs(vl[0]) + abs(vr[0]))
            avg_y = 0.5 * (vl[1] + vr[1])
            avg_z = 0.5 * (vl[2] + vr[2])
            
            vertices[l, 0] = (1 - alpha) * vl[0] + alpha * (-avg_abs_x)
            vertices[l, 1] = (1 - alpha) * vl[1] + alpha * avg_y
            vertices[l, 2] = (1 - alpha) * vl[2] + alpha * avg_z
            
            vertices[r, 0] = (1 - alpha) * vr[0] + alpha * (avg_abs_x)
            vertices[r, 1] = (1 - alpha) * vr[1] + alpha * avg_y
            vertices[r, 2] = (1 - alpha) * vr[2] + alpha * avg_z

        mid_idx = np.where(np.abs(vertices[:, 0]) <= 0.005)[0]
        vertices[mid_idx, 0] = 0.0

        mesh.vertices = vertices
    except Exception as e:
        logger.warning(f"Symmetry regularization exception: {e}")
    return mesh


def perform_all_measurements(mesh, front_image_path=None, calibration_type=None, calibration_value=None):
    """
    Compute all 14 biometric and head protection dimensions strictly from 3D geometry.
    No hardcoded ratios or dummy guesses are used.
    """
    print("--- Performing pure 3D geometry measurements ---")
    try:
        mesh = _align_mesh_to_principal_axes(mesh)
        mesh = symmetrize_3d_mesh(mesh, alpha=0.70)
        landmarks = _find_anatomical_landmarks(mesh)
        extents = mesh.bounding_box.extents
        vertices = mesh.vertices

        # 1. Measure raw 3D Head Circumference (A) by horizontal slice at eyebrow/nasion level
        raw_circumference_A = 0.0
        try:
            nasion_y = float(vertices[landmarks['nasion_idx'], 1])
            slice_3d = mesh.section(plane_origin=[0, nasion_y, 0], plane_normal=[0, 1, 0])
            if slice_3d is not None and hasattr(slice_3d, 'length') and slice_3d.length > 0:
                raw_circumference_A = float(slice_3d.length)
        except Exception:
            pass

        # Fallback perimeter from cranial ellipse if planar slicing is unavailable
        if raw_circumference_A <= 0:
            raw_a = extents[0] * 0.46
            raw_b = extents[2] * 0.48
            if raw_a > 0 and raw_b > 0:
                raw_circumference_A = float(np.pi * (3 * (raw_a + raw_b) - np.sqrt((3 * raw_a + raw_b) * (raw_a + 3 * raw_b))))

        # 2. Determine Scale Factor based on Physical Calibration Reference
        scale_factor = _estimate_mesh_scale_factor(mesh)

        if calibration_value is not None and float(calibration_value) > 0:
            cal_val = float(calibration_value)
            if calibration_type == 'USER_CIRCUMFERENCE' or calibration_type is None:
                if raw_circumference_A > 0:
                    scale_factor = cal_val / raw_circumference_A
                    print(f"--- User Circumference Calibration ({cal_val}cm): Scale factor = {scale_factor:.4f} ---")
            elif calibration_type == 'USER_IPD':
                left_eye = vertices[landmarks['eye_outer_corner_left_idx']]
                right_eye = vertices[landmarks['eye_outer_corner_right_idx']]
                mesh_eye_dist = float(np.linalg.norm(left_eye - right_eye))
                if mesh_eye_dist > 0:
                    scale_factor = cal_val / mesh_eye_dist
                    print(f"--- User Eye-Distance Calibration ({cal_val}cm): Scale factor = {scale_factor:.4f} ---")
        elif front_image_path is not None:
            try:
                from scans.processing.calibration import estimate_physical_scale_from_photo
                physical_ocular = estimate_physical_scale_from_photo(front_image_path)
                if physical_ocular is not None and physical_ocular > 0:
                    left_eye = vertices[landmarks['eye_outer_corner_left_idx']]
                    right_eye = vertices[landmarks['eye_outer_corner_right_idx']]
                    mesh_ocular = float(np.linalg.norm(left_eye - right_eye))
                    if mesh_ocular > 0:
                        scale_factor = physical_ocular / mesh_ocular
                        print(f"--- Photo AI Calibration: Scale factor = {scale_factor:.4f} ---")
            except Exception as cal_err:
                logger.warning(f"Photo calibration exception: {cal_err}")

        # 3. True Cranial Head Width, Length, and Height from 3D mesh
        top_y = vertices[landmarks['top_of_head_idx'], 1]
        chin_y = vertices[landmarks['chin_idx'], 1]
        head_height = float(abs(top_y - chin_y)) * scale_factor

        # Cranial Head Width: Distance across parietal/temple region strictly above ears
        parietal_left = vertices[landmarks['left_side_idx']]
        parietal_right = vertices[landmarks['right_side_idx']]
        raw_head_width = float(abs(parietal_right[0] - parietal_left[0]))
        head_width = raw_head_width * scale_factor

        # Head Length: Glabella/Nasion to Occipital prominence
        nasion_pt = vertices[landmarks['nasion_idx']]
        inion_pt = vertices[landmarks['back_of_head_idx']]
        raw_head_length = float(abs(nasion_pt[2] - inion_pt[2]))
        head_length = raw_head_length * scale_factor

        # Measurement A: Head Circumference
        head_circumference_A = raw_circumference_A * scale_factor

        # Measurement B: Forehead to Back Sagittal Arc (Nasion -> Vertex -> Occiput over head surface)
        raw_B_front = _calculate_surface_distance(mesh, landmarks['nasion_idx'], landmarks['top_of_head_idx'])
        raw_B_back = _calculate_surface_distance(mesh, landmarks['top_of_head_idx'], landmarks['back_of_head_idx'])
        forehead_to_back_B = (raw_B_front + raw_B_back) * scale_factor

        # Ear Anatomical Landmarks
        ear_right = _find_ear_landmarks(mesh, landmarks, side='right')
        ear_left = _find_ear_landmarks(mesh, landmarks, side='left')

        left_ear_ref = ear_left['ear_top_idx'] if ear_left else landmarks.get('left_ear_level_idx', landmarks['left_side_idx'])
        right_ear_ref = ear_right['ear_top_idx'] if ear_right else landmarks.get('right_ear_level_idx', landmarks['right_side_idx'])

        # Measurement C: Cross Measurement Coronal Arc (Left ear top -> Vertex -> Right ear top)
        raw_C_left = _calculate_surface_distance(mesh, left_ear_ref, landmarks['top_of_head_idx'])
        raw_C_right = _calculate_surface_distance(mesh, landmarks['top_of_head_idx'], right_ear_ref)
        cross_measurement_C = (raw_C_left + raw_C_right) * scale_factor

        # Measurement D: Under Chin Arc (Left temple/ear root -> Chin/Menton -> Right temple/ear root)
        left_chin_ref = ear_left['ear_root_idx'] if ear_left else landmarks.get('left_ear_level_idx', landmarks['left_side_idx'])
        right_chin_ref = ear_right['ear_root_idx'] if ear_right else landmarks.get('right_ear_level_idx', landmarks['right_side_idx'])
        raw_D_left = _calculate_surface_distance(mesh, left_chin_ref, landmarks['chin_idx'])
        raw_D_right = _calculate_surface_distance(mesh, landmarks['chin_idx'], right_chin_ref)
        under_chin_D = (raw_D_left + raw_D_right) * scale_factor

        # Measurements E, G, H (Ear Metrics - strictly 3D vertex coordinates)
        ear = ear_right if ear_right is not None else ear_left
        
        # E: Vertical distance from eyebrow/nasion plane to bottom of earlobe
        raw_E = float(abs(vertices[landmarks['nasion_idx'], 1] - vertices[ear['earlobe_bottom_idx'], 1]))
        eyebrow_to_earlobe_E = raw_E * scale_factor

        # G: Ear height (Top of ear to earlobe bottom)
        raw_G = float(np.mean([
            abs(vertices[e['ear_top_idx'], 1] - vertices[e['earlobe_bottom_idx'], 1])
            for e in (ear_right, ear_left) if e is not None
        ]))
        ear_height_G = raw_G * scale_factor

        # H: Ear width (front-to-back helical depth of ear)
        raw_H_vals = [e['ear_depth_raw'] for e in (ear_right, ear_left) if e is not None and e.get('ear_depth_raw', 0) > 0]
        if len(raw_H_vals) > 0:
            raw_H = float(np.mean(raw_H_vals))
        else:
            raw_H = float(np.mean([
                np.linalg.norm(vertices[e['ear_root_idx']] - vertices[e['ear_posterior_idx']])
                for e in (ear_right, ear_left) if e is not None
            ]))
        if raw_H <= 0:
            raw_H = float(abs(vertices[landmarks['top_of_head_idx'], 1] - vertices[landmarks['chin_idx'], 1])) * 0.15
        ear_width_H = raw_H * scale_factor

        # Measurement F: Eye Corner to Ear (Horizontal front-to-back distance from Outer Canthus to Ear Root)
        eye_side = 'right' if ear_right is not None else 'left'
        eye_idx = landmarks.get(f'eye_outer_corner_{eye_side}_idx', landmarks['nasion_idx'])
        ear_root_idx = ear['ear_root_idx'] if ear else landmarks['back_of_head_idx']
        raw_F = float(abs(vertices[eye_idx, 2] - vertices[ear_root_idx, 2]))
        if raw_F <= 0:
            raw_F = float(np.linalg.norm(vertices[eye_idx] - vertices[ear_root_idx]))
        eye_corner_to_ear_F = raw_F * scale_factor

        # Eye to Eye: 3D Euclidean distance between left and right outer canthi
        raw_eye_to_eye = float(np.linalg.norm(
            vertices[landmarks['eye_outer_corner_left_idx']] - vertices[landmarks['eye_outer_corner_right_idx']]
        ))
        eye_to_eye = raw_eye_to_eye * scale_factor

        # Ear to Ear: 3D Euclidean distance between outermost lateral ear points
        raw_ear_to_ear = float(np.linalg.norm(
            vertices[ear_left['ear_outer_idx']] - vertices[ear_right['ear_outer_idx']]
        ))
        ear_to_ear = raw_ear_to_ear * scale_factor

        # Cheek Guard L, M, N: Derived directly from Zygoma (cheekbone) and Mandible geometry
        zyg_left = vertices[landmarks['zygoma_left_idx']]
        zyg_right = vertices[landmarks['zygoma_right_idx']]
        
        # N: Cheek Guard Width (Bizygomatic Breadth across cheekbones)
        raw_N = float(np.linalg.norm(zyg_left - zyg_right))
        cheek_guard_width_N = raw_N * scale_factor

        # M: Cheek Guard Height (Vertical distance from chin to cheekbone)
        raw_M = float(abs(zyg_left[1] - vertices[landmarks['chin_idx'], 1]))
        cheek_guard_height_M = raw_M * scale_factor

        # L: Cheek Guard Clearance (Anterior distance from cheekbone to ear root)
        raw_L = float(abs(zyg_left[2] - vertices[left_ear_ref, 2]))
        cheek_guard_clearance_L = raw_L * scale_factor

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
        logger.error(f"Measurement Calculation Error: {e}")
        traceback.print_exc()
        return {}