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
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                idx = []
                for part in line.split()[1:]:
                    i = int(part.split("/")[0])
                    if i < 0:
                        i = len(verts) + i + 1
                    idx.append(i - 1)
                for k in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[k], idx[k + 1]])
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces, dtype=int)
    valid = (faces >= 0).all(axis=1) & (faces < len(verts)).all(axis=1)
    return trimesh.Trimesh(verts, faces[valid], process=False)


def load_mesh_with_fallback(path):
    try:
        return trimesh.load(path, file_type="obj", force="mesh")
    except IndexError:
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            name = str(int(time.time())) + "_" + os.path.basename(path)
            shutil.copy(path, os.path.join(DEBUG_DIR, name))
        except Exception:
            pass
        return _load_obj_manual(path)
