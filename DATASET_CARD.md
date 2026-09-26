# UrbanSense AI — Dataset Card: RDD2022 India Curated YOLO Training Set

**Version:** 1.0  
**Last Updated:** 2026-09-24  
**Pipeline Author:** UrbanSense AI Computer Vision & ML Data Quality Engineering Team  
**Problem Statement:** SIH Problem Statement 26124 (Mobile Urban Intelligence Platform)  
**Status:** TRAINING READY  

---

## 1. Dataset Overview & Provenance

* **Raw Dataset Source:** Road Damage Dataset 2022 (RDD2022) — India Sub-dataset.
* **Origin:** Crowdsourced / vehicle-mounted mobile smartphone video surveys across Indian urban and rural roadways (Sekilab / University of Tokyo RDD Initiative).
* **Raw Storage Location:** `datasets/India/India/` (Immutable source; strictly preserved).
* **Curated Output Location:**
  * Clean Manifest & Audit: `datasets/cleaned/rdd_urbansense/`, `datasets/audit/`
  * YOLO Training Dataset: `datasets/yolo/rdd_urbansense/`
  * Quarantine Repository: `datasets/cleaned/quarantine/`
* **Raw Image Format:** JPEG, $720 \times 720$ resolution, RGB 3-channel.
* **Raw Annotation Format:** Pascal VOC XML (`<annotation>`, `<size>`, `<object>`, `<bndbox>`).

---

## 2. Dataset Size & Structural Inventory

| Split | Raw Image Count | Raw XML Count | Annotated Images | Background Images (Empty XML) | Curated YOLO Images |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Train Pool** | 7,706 | 7,706 | 3,785 (49.1%) | 3,921 (50.9%) | 4,151 total (3,773 annotated + 378 bg) |
| **Test Split** | 1,959 | 0 (Unannotated) | 0 | N/A (Competition Blind Test) | 0 (Isolated; never leaked) |
| **Total** | **9,665** | **7,706** | **3,785** | **3,921** | **4,151** |

---

## 3. Raw vs Clean Class Inventory

| Raw Class | Description | Raw Objects | Raw Images | Clean Action | Clean Class | Clean Class ID | Clean Objects |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **D00** | Longitudinal Crack | 1,555 | 1,109 | Retained | `D00` | 0 | 1,556 *(incl. D0w0)* |
| **D01** | Longitudinal Construction Joint | 179 | 118 | Retained | `D01` | 1 | 179 |
| **D10** | Transverse Crack | 68 | 60 | Retained | `D10` | 2 | 68 |
| **D11** | Transverse Construction Joint | 45 | 36 | Retained | `D11` | 3 | 45 |
| **D20** | Alligator Crack | 2,021 | 1,758 | Retained | `D20` | 4 | 2,021 |
| **D40** | Pothole / Other Corruption | 3,187 | 1,530 | Retained | `D40` | 5 | 3,187 |
| **D43** | Crosswalk Blur | 57 | 57 | Retained | `D43` | 6 | 57 |
| **D44** | White Line Blur | 1,062 | 869 | Retained | `D44` | 7 | 1,062 |
| **D0w0** | *Typographical Error for D00* | 1 | 1 | Remapped to D00 | `D00` | 0 | *(Merged into D00)* |
| **D50** | *Non-standard Class (Manholes/Grates)* | 28 | 28 | Quarantined | N/A | N/A | 0 *(Quarantined)* |
| **TOTAL** | | **8,203** | **3,785** | | | | **8,175** |

---

## 4. Anomaly Investigation & Resolution Audit

### 4.1 Typo Resolution: `D0w0`
* **File:** `India_006389.xml` / `India_006389.jpg`
* **Bounding Box:** $x_{min}=455.0, y_{min}=490.0, x_{max}=570.0, y_{max}=663.0$ ($W=115, H=173, \text{aspect}=1.50$)
* **Physical Evidence:** Bounding box encapsulates a single longitudinal vertical crack running down the vehicle wheel track on an asphalt road. Keyboard topology shows 'w' is adjacent to '0' on standard input devices.
* **Audit Decision:** Formally remapped to `D00` (Longitudinal Crack) with an immutable audit entry in `datasets/cleaned/rdd_urbansense/cleaning_audit_trail.json`.

### 4.2 Quarantine: `D50`
* **Occurrences:** 28 objects across 28 images (e.g., `India_000128`, `India_000358`, `India_003023`).
* **Physical Evidence:** Annotations delineate cast-iron utility access manholes, stormwater drain grates, and municipal utility covers.
* **Domain Reasoning:** Manholes and drain covers are standard municipal road fixtures, not structural pavement distress or vehicular damage hazards. Training a road damage model to detect manholes as pavement defects causes severe false-positive alarms on municipal bus fleets.
* **Audit Decision:** Quarantined from YOLO defect training. All 28 instances are preserved in `datasets/cleaned/quarantine/quarantine_manifest.json` for prospective municipal asset tracking.

---

## 5. Duplicate Detection & Leakage Prevention

* **Exact SHA-256 Duplicates:** 0 across all 9,665 images.
* **Perceptual Near-Duplicates (dHash distance 0):** 6 groups identified:
  1. `India_001964` (train) and `India_000573` (test) — Cross-split near-duplicate (unannotated test frame).
  2. `India_002318` and `India_008870` (train)
  3. `India_003191` and `India_003989` (train)
  4. `India_003967` and `India_008857` (train)
  5. `India_008592` and `India_009873` (train)
  6. `India_004420` and `India_006573` (test)
* **Leakage Gate:** Paired images from survey video bursts were hard-grouped into the same split (`train`) to guarantee zero validation data contamination.

---

## 6. Train/Validation Split Specification

* **Split Algorithm:** Stratified by primary defect class across annotated images, enforcing duplicate-group integrity, with a 10% background image injection ratio.
* **Seed:** 42 (Strictly deterministic).
* **Train Set:**
  * Total Images: 3,320
  * Annotated Images: 3,018 (80.0%)
  * Background Images: 302 (10% ratio)
  * Total Objects: 6,560
* **Validation Set:**
  * Total Images: 831
  * Annotated Images: 755 (20.0%)
  * Background Images: 76 (10% ratio)
  * Total Objects: 1,615
* **Split Leakage:** 0 overlap verified ($\text{Train} \cap \text{Val} = \emptyset$).

---

## 7. YOLO Format Specification

* **Root Path:** `datasets/yolo/rdd_urbansense/`
* **Configuration:** `data.yaml`
* **Format:** `<class_id> <x_center> <y_center> <width> <height>` (normalized to $0.0 - 1.0$, 6 decimal places).
* **Background Labels:** Empty text files (0 bytes) per standard YOLO conventions.
* **Post-Conversion Validation:** 100% of the 4,151 label files verified. 0 coordinate bounds violations, 0 non-numeric tokens, 0 NaNs.

---

## 8. Reproducibility Command

To regenerate the exact audit, manifest, train/val split, and YOLO dataset from scratch:

```bash
python scripts/prepare_rdd_dataset.py \
    --raw-dir "D:/UrbanSense AI/datasets/India/India" \
    --output-base "datasets" \
    --taxonomy-file "datasets/config/taxonomy.yaml" \
    --taxonomy "Candidate_A_Full_RDD" \
    --train-ratio 0.80 \
    --background-ratio 0.10 \
    --seed 42
```
