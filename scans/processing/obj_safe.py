import os
import shutil
import time

import numpy as np
import trimesh

DEBUG_DIR = "/app/media/debug_obj"


def _load_obj_manual(path):
    verts, faces = [], []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    except ValueError:
                        continue
            elif line.startswith("f "):
                idx = []
                for part in line.split()[1:]:
                    try:
                        i = int(part.split("/")[0])
                        if i < 0:
                            i = len(verts) + i + 1
                        idx.append(i - 1)
                    except (ValueError, IndexError):
                        continue
                for k in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[k], idx[k + 1]])

    verts = np.asarray(verts, dtype=float)
    if len(verts) == 0:
        raise ValueError(f"No valid vertices found in OBJ: {path}")

    if len(faces) == 0:
        faces = np.empty((0, 3), dtype=int)
        valid = np.zeros(0, dtype=bool)
    else:
        faces = np.asarray(faces, dtype=int)
        if faces.ndim != 2 or faces.shape[1] != 3:
            faces = np.empty((0, 3), dtype=int)
            valid = np.zeros(0, dtype=bool)
        else:
            valid = (faces >= 0).all(axis=1) & (faces < len(verts)).all(axis=1)

    return trimesh.Trimesh(verts, faces[valid], process=False)


def load_mesh_with_fallback(path):
    try:
        return trimesh.load(path, file_type="obj", force="mesh")
    except Exception as e:
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            name = str(int(time.time())) + "_" + os.path.basename(path)
            shutil.copy(path, os.path.join(DEBUG_DIR, name))
        except Exception:
            pass
        return _load_obj_manual(path)
