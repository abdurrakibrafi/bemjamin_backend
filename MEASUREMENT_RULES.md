# 3D Mesh Measurement Rules & Specifications

## 1. Immutable User Calibration Standard
* **Rule**: When the user provides a `calibration_value` (e.g., Head Circumference $A = 60.0\text{ cm}$), this value is **strictly immutable**.
* **Constraint**: The system must **NEVER** overwrite, re-slice, or recalculate `head_circumference_A` if a manual input is present.
* **Mesh Scaling**: The entire 3D mesh is scaled proportionately using:
  $$\text{calibration\_scale} = \frac{\text{calibration\_value}}{\text{raw\_mesh\_circumference}}$$
  All downstream biometric measurements must inherit this calibrated scale.

---

## 2. Prohibition of Fixed/Approximate Multipliers
* **Rule**: Do **NOT** use arbitrary fixed multipliers (such as `0.50 * A`, `0.442 * A`, `0.567 * A`) to hardcode or clamp values.
* **Requirement**: Every biometric and helmet fitting measurement must be calculated **directly and purely from the 3D mesh geometry** (geodesic surface paths or 3D Euclidean caliper measurements).

---

## 3. Anatomical Landmark Precision (Eliminating Bust/Neck Interference)
KeenTools avatar models include the neck, throat, and upper chest. Landmarks must be strictly isolated to the cranial and facial regions:

### A. Chin Landmark (`chin_idx`)
* **Problem**: Unbounded search falls down to the lower throat or collar, causing `head_height` to spike to ~32 cm and `under_chin_D` to ~42 cm.
* **Correct Logic**: Isolate the **Pogonion** (most anterior forward protrusion of the lower jaw) within $7.5\text{ cm}$ to $11.0\text{ cm}$ directly below the nose tip ($X \approx 0$). It must never descend into the submental or cervical (neck) region.

### B. Ear Bounding Box (`_find_ear_landmarks`)
* **Problem**: A wide vertical search band without tight spatial bounding measures the entire side of the head ($11.5\text{ cm}$ height and $7.3\text{ cm}$ depth).
* **Correct Logic**: 
  - Locate the lateral helix peak (`ear_outer_idx`).
  - Restrict the pinna search box strictly around this peak:
    - Vertical: $\Delta Y \le \pm 3.8\text{ cm}$ (maximum physical ear height $\approx 7.0\text{ cm}$).
    - Depth: $\Delta Z \le \pm 2.5\text{ cm}$ (maximum physical ear width $\approx 4.5\text{ cm}$).
  - `ear_height_G`: Straight-line caliper distance from superior helix (`ear_top_idx`) to inferior lobule (`earlobe_bottom_idx`).
  - `ear_width_H`: Straight-line caliper distance from anterior tragus (`ear_root_idx`) to posterior rim (`ear_posterior_idx`).

### C. Inion / Back of Head (`back_of_head_idx`)
* **Problem**: Searching too low on the mesh targets the cervical spine / lower neck, making `forehead_to_back_B` ~40 cm.
* **Correct Logic**: The Inion / Opisthocranion must sit on the posterior cranial vault roughly level with the eyebrows/eyes ($Y \ge \text{chin\_y} + 0.50 \times \text{head\_height}$).

### D. Coronal Arc Starting Point (`ear_root_top_idx`)
* **Problem**: Starting on the lateral floating tip of the ear causes the coronal path to crawl around the outer ear.
* **Correct Logic**: Start at the cranial junction where the upper ear root attaches to the skull (**Otobasion superius**).

---

## 4. Ground Truth Benchmark Reference ($A = 58.0\text{ cm}$)
When calibrating on a physical head of circumference $A = 58.0\text{ cm}$ (ATO FORM Starlight specifications):
* **Head Circumference (A)**: $58.0\text{ cm}$ (User input)
* **Forehead to Back (B)**: $35.0\text{ cm}$ (Nasion over vertex to nape of neck)
* **Cross Measurement (C)**: $32.0\text{ cm}$ (Ear to ear over crown)
* **Under Chin (D)**: $37.0\text{ cm}$ (Ear to ear under chin)
* **Eyebrow to Earlobe (E)**: $8.0\text{ cm}$
* **Eye Corner to Ear Root (F)**: $8.5\text{ cm}$
* **Ear Height (G)**: $7.0\text{ cm}$
* **Ear Width (H)**: $4.5\text{ cm}$
* **Cheek Guard Height (M)**: $\approx 4.5\text{ cm}$
* **Cheek Guard Clearance (L)**: $\approx 4.5 - 5.3\text{ cm}$
* **Cheek Guard Width (N)**: $\approx 5.3\text{ cm}$
