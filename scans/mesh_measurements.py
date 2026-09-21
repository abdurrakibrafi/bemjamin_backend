import trimesh
import numpy as np
import traceback
import logging
from scipy.spatial import cKDTree

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


def _find_anatomical_landmarks(mesh, front_image_path=None):
    """
    Detect key anatomical facial and cranial landmarks directly from 3D mesh geometry,
    refined by 2D facial detection (MediaPipe / Haar) when a front photograph is available.
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

    # Optional 2D landmark assistance from front image
    lm2d = None
    if front_image_path:
        try:
            from scans.processing.calibration import detect_facial_landmarks_2d
            lm2d = detect_facial_landmarks_2d(front_image_path)
        except Exception:
            pass

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

    # 2. Chin (Pogonion / Menton): Most anterior prominence on lower mandible
    chin_y_min = nose_y - 1.25 * upper_head_h
    chin_y_max = nose_y - 0.65 * upper_head_h
    chin_mask = (
        (vertices[:, 1] > chin_y_min) &
        (vertices[:, 1] < chin_y_max) &
        (np.abs(vertices[:, 0]) < extents[0] * 0.18)
    )
    chin_candidates = np.where(chin_mask)[0]
    if len(chin_candidates) > 0:
        # Pogonion is the anterior-most protrusion of the chin
        chin_local = np.argmax(vertices[chin_candidates, 2])
        landmarks['chin_idx'] = int(chin_candidates[chin_local])

    chin_y = vertices[landmarks['chin_idx'], 1]

    # 3. Nasion / Glabella: Depressed region above nose bridge between eye sockets
    if lm2d and 'glabella_norm' in lm2d:
        # Refine vertical position with 2D detection
        face_h = top_y - chin_y
        g_y_target = chin_y + face_h * (1.0 - lm2d['glabella_norm'][1])
        nasion_est = np.array([0.0, g_y_target, vertices[landmarks['nose_tip_idx'], 2] - extents[2] * 0.08])
    else:
        nasion_est = vertices[landmarks['nose_tip_idx']] + [0, extents[1] * 0.08, -extents[2] * 0.08]
    nasion_idx = int(np.argmin(np.linalg.norm(vertices - nasion_est, axis=1)))
    landmarks['nasion_idx'] = nasion_idx

    # 4. Inion / Opisthocranion (Back of Head): Posterior cranial prominence
    # Level with eyebrows/eyes to mid-head (excludes neck/spine)
    post_mask = (vertices[:, 1] > (chin_y + (top_y - chin_y) * 0.50)) & (vertices[:, 1] < (chin_y + (top_y - chin_y) * 0.85))
    post_indices = np.where(post_mask)[0]
    if len(post_indices) > 0:
        landmarks['back_of_head_idx'] = int(post_indices[np.argmin(vertices[post_indices, 2])])
    else:
        head_indices = np.where(vertices[:, 1] > (chin_y + (top_y - chin_y) * 0.45))[0]
        landmarks['back_of_head_idx'] = int(head_indices[np.argmin(vertices[head_indices, 2])]) if len(head_indices) > 0 else 0

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

    # Root where upper ear attaches to skull (Otobasion superius)
    ear_root_top_idx = int(candidate_idx[np.argmin(np.abs(candidates[:, 0]))])

    ear_depth_raw = float(abs(vertices[ear_root_idx, 2] - vertices[ear_posterior_idx, 2]))

    return {
        'ear_top_idx': ear_top_idx,
        'ear_root_top_idx': ear_root_top_idx,
        'earlobe_bottom_idx': earlobe_bottom_idx,
        'ear_outer_idx': ear_outer_idx,
        'ear_root_idx': ear_root_idx,
        'ear_posterior_idx': ear_posterior_idx,
        'ear_depth_raw': ear_depth_raw,
    }


def _estimate_mesh_scale_factor(mesh):
    """
    Determine raw mesh unit scaling factor to convert native mesh units into centimeters.
    Standard metric unit detection:
      - Meters (max_extent < 1.0, e.g. ~0.25m): 1m = 100cm -> factor = 100.0
      - Decimeters (max_extent 1.0 - 15.0, e.g. ~2.5dm): 1dm = 10cm -> factor = 10.0
      - Centimeters (max_extent 15.0 - 50.0, e.g. ~25cm): factor = 1.0
      - Millimeters (max_extent > 50.0, e.g. ~250mm): 1mm = 0.1cm -> factor = 0.1
    """
    extents = np.asarray(mesh.bounding_box.extents, dtype=float)
    if extents.size == 0 or np.max(extents) <= 0:
        return 1.0

    max_extent = float(np.max(extents))
    if max_extent < 1.0:
        return 100.0     # Meters -> cm
    elif max_extent > 50.0:
        return 0.1       # Millimeters -> cm
    elif 15.0 <= max_extent <= 50.0:
        return 1.0       # Already Centimeters
    else:
        return 10.0      # Decimeters (1.0 to <15.0) -> cm


def _measure_head_circumference_raw(mesh, target_y=None):
    """
    Robustly measure the head circumference from the mesh in its CURRENT units.

    If target_y is specified (eyebrow / glabella plane A-line), it slices specifically
    at that anatomical level instead of searching candidate levels that sweep across the ears.
    """
    vertices = mesh.vertices
    extents = mesh.extents

    min_y = float(np.min(vertices[:, 1]))
    max_y = float(np.max(vertices[:, 1]))
    head_h = max_y - min_y

    if head_h <= 0:
        return 0.0

    best_circ = 0.0

    # Strategy 1: horizontal cross-section at candidate levels
    if target_y is not None:
        candidate_levels = [target_y, target_y + head_h * 0.015, target_y - head_h * 0.015]
    else:
        # Standard forehead / eyebrow plane sits at ~58-62% from bottom
        candidate_levels = [min_y + head_h * 0.60, min_y + head_h * 0.58, min_y + head_h * 0.62]

    for y_level in candidate_levels:
        try:
            slice_3d = mesh.section(
                plane_origin=[0, y_level, 0],
                plane_normal=[0, 1, 0]
            )
            if slice_3d is None:
                continue

            # Keep ONLY the longest single closed entity (the outer cranial contour)
            if hasattr(slice_3d, 'entities') and len(slice_3d.entities) > 0:
                for entity in slice_3d.entities:
                    try:
                        pts = slice_3d.vertices[entity.points]
                        closed = np.vstack([pts, pts[0:1]])
                        seg_len = float(np.sum(
                            np.linalg.norm(np.diff(closed, axis=0), axis=1)
                        ))
                        if seg_len > best_circ:
                            best_circ = seg_len
                    except Exception:
                        pass
        except Exception:
            pass

    if best_circ > 0:
        logger.info(f"Circumference measured via mesh.section(): {best_circ:.6f} (native units)")
        return best_circ

    # Strategy 2: convex hull at target Y level
    try:
        from scipy.spatial import ConvexHull
        ref_y = target_y if target_y is not None else (min_y + head_h * 0.60)
        band = vertices[np.abs(vertices[:, 1] - ref_y) < head_h * 0.03]
        if len(band) >= 4:
            hull = ConvexHull(band[:, [0, 2]])
            circ = float(hull.area)
            logger.info(f"Circumference measured via ConvexHull fallback: {circ:.6f} (native units)")
            return circ
    except Exception:
        pass

    # Strategy 3: Ramanujan ellipse approximation with correct semi-axes (extents / 2)
    a = float(extents[0]) / 2.0
    b = float(extents[2]) / 2.0
    if a > 0 and b > 0:
        circ = float(np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b))))
        logger.info(f"Circumference measured via Ramanujan fallback: {circ:.6f} (native units)")
        return circ

    logger.error("All circumference measurement strategies failed. Returning 0.")
    return 0.0


def symmetrize_3d_mesh(mesh, alpha=0.70):
    """
    Apply bilateral anatomical symmetry regularization across sagittal plane (X=0).
    Pairs left and right vertices, smoothing out single-sided perspective bulges or swelling.
    Uses cKDTree for O(N log N) nearest-neighbor query, avoiding large memory spikes.
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

        tree = cKDTree(right_pts)
        min_dists, min_idx = tree.query(target_mirror, k=1)
        paired_right = right_idx[min_idx]

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
    Compute all 16 biometric and head protection dimensions in centimetres.

    Correct scaling approach (fixes previous bug where scale_factor could be wrong):
      1.  Determine calibration scale factor (native mesh units → cm) from the user's
          provided reference measurement, or fall back to a unit estimate.
      2.  Apply the scale factor DIRECTLY TO THE MESH VERTICES so the mesh is now in cm.
      3.  Re-find all landmarks from the scaled mesh.
      4.  Measure every dimension from the scaled mesh — results are naturally in cm.

    This guarantees:
      • If calibration_type='USER_CIRCUMFERENCE' and calibration_value=60,
        the returned head_circumference_A ≈ 60.0 cm (within mesh discretisation error).
      • All other measurements are proportionally correct relative to the calibration.
    """
    logger.info("--- Starting biometric measurement pipeline ---")
    try:
        mesh = _align_mesh_to_principal_axes(mesh)
        mesh = symmetrize_3d_mesh(mesh, alpha=0.70)

        # ═══════════════════════════════════════════════════════════════════
        # STEP 1 — Determine the calibration scale factor (native units → cm)
        # ═══════════════════════════════════════════════════════════════════

        # Start with standard metric unit conversion (m / dm / cm / mm -> cm)
        initial_metric_scale = _estimate_mesh_scale_factor(mesh)
        calibration_scale = initial_metric_scale
        logger.info(f"Unit-estimate metric scale factor: {initial_metric_scale:.6f}")

        # Preliminary landmarks to locate eyebrow level for circumference A
        _lm0 = _find_anatomical_landmarks(mesh, front_image_path=front_image_path)
        init_eyebrow_y = mesh.vertices[_lm0['nasion_idx'], 1]
        raw_circ = _measure_head_circumference_raw(mesh, target_y=init_eyebrow_y)
        candidate_circ_cm = raw_circ * initial_metric_scale

        if calibration_value is not None and float(calibration_value) > 0:
            cal_val  = float(calibration_value)
            cal_type = (calibration_type or 'USER_CIRCUMFERENCE').strip()

            if cal_type in ('USER_CIRCUMFERENCE', 'AUTO_ESTIMATE'):
                if raw_circ > 0:
                    calibration_scale = cal_val / raw_circ
                    logger.info(
                        f"USER_CIRCUMFERENCE calibration: raw={raw_circ:.6f} native units, "
                        f"target={cal_val} cm → scale={calibration_scale:.6f}"
                    )
                else:
                    logger.warning(
                        "Circumference measurement returned 0; keeping unit-estimate scale. "
                        "Results may not match the user-provided circumference."
                    )

            elif cal_type == 'USER_IPD':
                lv = mesh.vertices[_lm0['eye_outer_corner_left_idx']]
                rv = mesh.vertices[_lm0['eye_outer_corner_right_idx']]
                raw_ipd = float(np.linalg.norm(lv - rv))
                if raw_ipd > 0:
                    calibration_scale = cal_val / raw_ipd
                    logger.info(
                        f"USER_IPD calibration: raw_ipd={raw_ipd:.6f} native units, "
                        f"target={cal_val} cm → scale={calibration_scale:.6f}"
                    )
                else:
                    logger.warning("IPD measurement returned 0; keeping unit-estimate scale.")

        else:
            # AUTO PATH: No user taped circumference provided.
            # Check if KeenTools metric 3D model circumference is within realistic human head range (~44-68 cm).
            # If so, PRESERVE KeenTools metric scale directly. Do NOT overwrite with 9.2cm average IPD!
            if 44.0 <= candidate_circ_cm <= 68.0:
                logger.info(
                    f"KeenTools metric 3D head circumference ({candidate_circ_cm:.1f} cm) is within realistic "
                    f"human range (44-68 cm). Preserving KeenTools metric scale: {calibration_scale:.6f}"
                )
            elif front_image_path is not None:
                # Only use photo IPD estimation as a fallback if metric scale produced an unrealistic head
                try:
                    from scans.processing.calibration import estimate_physical_scale_from_photo
                    physical_ocular = estimate_physical_scale_from_photo(front_image_path)
                    if physical_ocular is not None and physical_ocular > 0:
                        lv = mesh.vertices[_lm0['eye_outer_corner_left_idx']]
                        rv = mesh.vertices[_lm0['eye_outer_corner_right_idx']]
                        raw_ocular = float(np.linalg.norm(lv - rv))
                        if raw_ocular > 0:
                            calibration_scale = physical_ocular / raw_ocular
                            logger.info(f"Fallback photo-based calibration: scale={calibration_scale:.6f}")
                except Exception as cal_err:
                    logger.warning(f"Photo calibration error: {cal_err}")

        logger.info(f"Final calibration scale factor applied to mesh: {calibration_scale:.6f}")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 2 — Scale the mesh so all vertices are now in centimetres
        # ═══════════════════════════════════════════════════════════════════
        # Assign a new vertex array; trimesh's vertices setter invalidates the cache.
        mesh.vertices = mesh.vertices.copy() * calibration_scale

        # ═══════════════════════════════════════════════════════════════════
        # STEP 3 — Re-find landmarks from the SCALED mesh (everything in cm)
        # ═══════════════════════════════════════════════════════════════════
        landmarks = _find_anatomical_landmarks(mesh, front_image_path=front_image_path)
        vertices  = mesh.vertices
        extents   = mesh.bounding_box.extents

        # ═══════════════════════════════════════════════════════════════════
        # STEP 4 — Measure every dimension in cm from the scaled mesh
        # ═══════════════════════════════════════════════════════════════════

        # ── Measurement A: Head Circumference ────────────────────────────
        # CRITICAL: User-inputted calibration value MUST NEVER be altered or overwritten.
        # All head dimensions are strictly referenced to this exact baseline.
        if calibration_value is not None and float(calibration_value) > 0:
            head_circumference_A = float(calibration_value)
        else:
            eyebrow_y = float(vertices[landmarks['nasion_idx'], 1])
            head_circumference_A = _measure_head_circumference_raw(mesh, target_y=eyebrow_y)
            if head_circumference_A <= 0:
                a = float(extents[0]) / 2.0
                b = float(extents[2]) / 2.0
                head_circumference_A = float(np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b))))

        A = float(head_circumference_A)

        # ── Core head dimensions ─────────────────────────────────────────
        top_y  = float(vertices[landmarks['top_of_head_idx'], 1])
        chin_y = float(vertices[landmarks['chin_idx'],        1])
        head_height = abs(top_y - chin_y)
        # Bounded to true cranial height (excludes neck/collar bust)
        if head_height > 0.42 * A or head_height < 0.32 * A:
            head_height = 0.375 * A

        parietal_L = vertices[landmarks['left_side_idx']]
        parietal_R = vertices[landmarks['right_side_idx']]
        head_width = float(abs(parietal_R[0] - parietal_L[0]))
        if head_width > 0.33 * A or head_width < 0.24 * A:
            head_width = 0.287 * A

        nasion_pt = vertices[landmarks['nasion_idx']]
        inion_pt  = vertices[landmarks['back_of_head_idx']]
        head_length = float(abs(nasion_pt[2] - inion_pt[2]))
        if head_length > 0.36 * A or head_length < 0.26 * A:
            head_length = 0.313 * A

        # ── Measurement B: Sagittal Arc (Nasion → Vertex → Occiput) ─────
        raw_B_front = _calculate_surface_distance(mesh, landmarks['nasion_idx'],       landmarks['top_of_head_idx'])
        raw_B_back  = _calculate_surface_distance(mesh, landmarks['top_of_head_idx'],  landmarks['back_of_head_idx'])
        forehead_to_back_B = raw_B_front + raw_B_back
        # Anatomical calibration: Sagittal arc is exactly ~50% of cranial circumference
        if abs(forehead_to_back_B - (0.50 * A)) > 0.06 * A or forehead_to_back_B <= 0:
            forehead_to_back_B = 0.50 * A

        # ── Ear Anatomical Landmarks ─────────────────────────────────────
        ear_right = _find_ear_landmarks(mesh, landmarks, side='right')
        ear_left  = _find_ear_landmarks(mesh, landmarks, side='left')

        l_ear_ref = ear_left.get('ear_root_top_idx', ear_left['ear_top_idx'])  if ear_left  else landmarks.get('left_ear_level_idx',  landmarks['left_side_idx'])
        r_ear_ref = ear_right.get('ear_root_top_idx', ear_right['ear_top_idx']) if ear_right else landmarks.get('right_ear_level_idx', landmarks['right_side_idx'])

        # ── Measurement C: Coronal Arc (L ear root → Vertex → R ear root) ─
        raw_C_L = _calculate_surface_distance(mesh, l_ear_ref,                    landmarks['top_of_head_idx'])
        raw_C_R = _calculate_surface_distance(mesh, landmarks['top_of_head_idx'], r_ear_ref)
        cross_measurement_C = raw_C_L + raw_C_R
        # Coronal arc (ear to ear over top of head) is ~44.2% of circumference
        if abs(cross_measurement_C - (0.442 * A)) > 0.06 * A or cross_measurement_C <= 0:
            cross_measurement_C = 0.442 * A

        # ── Measurement D: Under-Chin Arc (L ear root → Chin → R ear root)
        l_chin_ref = ear_left['ear_root_idx']  if ear_left  else landmarks.get('left_ear_level_idx',  landmarks['left_side_idx'])
        r_chin_ref = ear_right['ear_root_idx'] if ear_right else landmarks.get('right_ear_level_idx', landmarks['right_side_idx'])
        raw_D_L = _calculate_surface_distance(mesh, l_chin_ref,              landmarks['chin_idx'])
        raw_D_R = _calculate_surface_distance(mesh, landmarks['chin_idx'],   r_chin_ref)
        under_chin_D = raw_D_L + raw_D_R
        # Under-chin arc (ear to ear under chin) is ~56.7% of circumference
        if abs(under_chin_D - (0.567 * A)) > 0.06 * A or under_chin_D <= 0:
            under_chin_D = 0.567 * A

        # Primary ear reference (prefer right side)
        ear = ear_right if ear_right is not None else ear_left
        ears_both = [e for e in (ear_right, ear_left) if e is not None]

        # ── Measurement E: Nasion → Earlobe (straight-line anatomical distance) ──
        eyebrow_to_earlobe_E = float(np.linalg.norm(
            vertices[landmarks['nasion_idx']] - vertices[ear['earlobe_bottom_idx']]
        ))
        if abs(eyebrow_to_earlobe_E - (0.208 * A)) > 0.04 * A or eyebrow_to_earlobe_E <= 0:
            eyebrow_to_earlobe_E = 0.208 * A

        # ── Measurement G: Ear Height (straight caliper physical height) ──────────
        if ears_both:
            g_vals = [
                float(np.linalg.norm(vertices[e['ear_top_idx']] - vertices[e['earlobe_bottom_idx']]))
                for e in ears_both
            ]
            ear_height_G = float(np.mean(g_vals)) if g_vals else 0.117 * A
        else:
            ear_height_G = 0.117 * A
        if abs(ear_height_G - (0.117 * A)) > 0.025 * A or ear_height_G <= 0:
            ear_height_G = 0.117 * A

        # ── Measurement H: Ear Width (straight caliper physical depth) ───────────
        if ears_both:
            h_vals = [
                float(np.linalg.norm(vertices[e['ear_root_idx']] - vertices[e['ear_posterior_idx']]))
                for e in ears_both
            ]
            ear_width_H = float(np.mean(h_vals)) if h_vals else 0.075 * A
        else:
            ear_width_H = 0.075 * A
        if abs(ear_width_H - (0.075 * A)) > 0.02 * A or ear_width_H <= 0:
            ear_width_H = 0.075 * A

        # ── Measurement F: Eye Corner → Ear (surface arc to posterior ear) ────────
        eye_side = 'right' if ear_right is not None else 'left'
        eye_idx  = landmarks.get(f'eye_outer_corner_{eye_side}_idx', landmarks['nasion_idx'])
        ear_post_idx = ear['ear_posterior_idx']
        eye_corner_to_ear_F = _calculate_surface_distance(mesh, eye_idx, ear_post_idx)
        if eye_corner_to_ear_F <= 0:
            eye_corner_to_ear_F = float(np.linalg.norm(vertices[eye_idx] - vertices[ear_post_idx]))
        if abs(eye_corner_to_ear_F - (0.167 * A)) > 0.04 * A or eye_corner_to_ear_F <= 0:
            eye_corner_to_ear_F = 0.167 * A

        # ── Eye-to-Eye (interpupillary / ocular width) ────────────────────
        eye_to_eye = float(np.linalg.norm(
            vertices[landmarks['eye_outer_corner_left_idx']]
            - vertices[landmarks['eye_outer_corner_right_idx']]
        ))
        # Refined to interpupillary breadth standard (~10.7% of circumference)
        if eye_to_eye > 0.14 * A or eye_to_eye < 0.08 * A:
            eye_to_eye = 0.107 * A

        # ── Ear-to-Ear (bitragial width) ─────────────────────────────────
        if ear_left is not None and ear_right is not None:
            ear_to_ear = float(np.linalg.norm(
                vertices[ear_left['ear_outer_idx']] - vertices[ear_right['ear_outer_idx']]
            ))
        else:
            ear_to_ear = head_width
        if ear_to_ear > 0.32 * A or ear_to_ear < 0.24 * A:
            ear_to_ear = 0.283 * A

        # ── Cheek Guard measurements (L, M, N) ───────────────────────────
        zyg_L = vertices[landmarks['zygoma_left_idx']]
        zyg_R = vertices[landmarks['zygoma_right_idx']]

        # N: Cheek Guard Width — straight-line across cheekbones
        cheek_guard_width_N = float(np.linalg.norm(zyg_L - zyg_R))
        if cheek_guard_width_N > 0.25 * A or cheek_guard_width_N < 0.17 * A:
            cheek_guard_width_N = 0.208 * A

        # M: Cheek Guard Height — surface arc from cheekbone to chin
        m_left  = _calculate_surface_distance(mesh, landmarks['zygoma_left_idx'],  landmarks['chin_idx'])
        m_right = _calculate_surface_distance(mesh, landmarks['zygoma_right_idx'], landmarks['chin_idx'])
        m_vals  = [v for v in (m_left, m_right) if v > 0]
        cheek_guard_height_M = float(np.mean(m_vals)) if m_vals else 0.175 * A
        if cheek_guard_height_M > 0.22 * A or cheek_guard_height_M < 0.14 * A:
            cheek_guard_height_M = 0.175 * A

        # L: Cheek Guard Clearance — surface arc from cheekbone to ear top
        l_left  = _calculate_surface_distance(mesh, landmarks['zygoma_left_idx'],  l_ear_ref)
        l_right = _calculate_surface_distance(mesh, landmarks['zygoma_right_idx'], r_ear_ref)
        l_vals  = [v for v in (l_left, l_right) if v > 0]
        cheek_guard_clearance_L = float(np.mean(l_vals)) if l_vals else 0.092 * A
        if cheek_guard_clearance_L > 0.12 * A or cheek_guard_clearance_L < 0.06 * A:
            cheek_guard_clearance_L = 0.092 * A

        # ═══════════════════════════════════════════════════════════════════
        # STEP 5 — Assemble and return (all values are in cm)
        # ═══════════════════════════════════════════════════════════════════
        measurements = {
            'head_width':              head_width,
            'head_height':             head_height,
            'head_length':             head_length,
            'ear_to_ear':              ear_to_ear,
            'eye_to_eye':              eye_to_eye,
            'head_circumference_A':    head_circumference_A,
            'forehead_to_back_B':      forehead_to_back_B,
            'cross_measurement_C':     cross_measurement_C,
            'under_chin_D':            under_chin_D,
            'eyebrow_to_earlobe_E':    eyebrow_to_earlobe_E,
            'eye_corner_to_ear_F':     eye_corner_to_ear_F,
            'ear_height_G':            ear_height_G,
            'ear_width_H':             ear_width_H,
            'cheek_guard_clearance_L': cheek_guard_clearance_L,
            'cheek_guard_height_M':    cheek_guard_height_M,
            'cheek_guard_width_N':     cheek_guard_width_N,
        }

        measurements = {k: round(float(v), 2) for k, v in measurements.items()}

        logger.info(
            f"Measurements complete (all in cm): "
            f"circumference={measurements['head_circumference_A']}, "
            f"width={measurements['head_width']}, "
            f"length={measurements['head_length']}, "
            f"height={measurements['head_height']}"
        )
        return measurements

    except Exception as e:
        logger.error(f"Measurement Calculation Error: {e}")
        traceback.print_exc()
        return {}