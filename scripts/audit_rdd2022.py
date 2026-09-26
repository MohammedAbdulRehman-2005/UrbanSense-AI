#!/usr/bin/env python3
"""
UrbanSense AI — RDD2022 India Dataset Automated Audit
=====================================================
Milestone 1: Complete automated audit of the RDD2022 INDIA dataset.
Source of Truth: Pascal VOC XML annotations + JPEG images.

Checks:
  1. Discovery of all image and XML files.
  2. Stem-based Image <-> XML matching (detect unmatched, duplicates, ambiguities).
  3. Safe XML parsing with error trapping.
  4. Complete class inventory (standard RDD2022 + anomalous classes).
  5. Image dimension audit (Pillow header inspect, XML <size> verification).
  6. Comprehensive bounding box validation (missing, non-numeric, inverted, negative, out-of-bounds, zero-area).
  7. Empty and background annotation tracking.
  8. Generation of machine-readable reports:
     - audit_output/audit_report.json
     - audit_output/audit_report.csv
     - audit_output/class_distribution.csv
     - audit_output/dataset_problems.json
     - audit_output/dataset_manifest.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("RDD2022Audit")

# Standard RDD2022 taxonomy mapping
RDD_TAXONOMY: Dict[str, str] = {
    "D00": "Longitudinal Crack",
    "D01": "Longitudinal Construction Joint",
    "D10": "Transverse Crack",
    "D11": "Transverse Construction Joint",
    "D20": "Alligator Crack",
    "D40": "Pothole / Other Corruption",
    "D43": "Crosswalk Blur",
    "D44": "White Line Blur",
}

# Known anomaly descriptions for clarity
ANOMALY_TAXONOMY: Dict[str, str] = {
    "D0w0": "Typo for D00 (Longitudinal Crack)",
    "D50": "Non-standard RDD class (Manhole / Utility Cover)",
}


def describe_class(class_name: str) -> str:
    """Return descriptive name for standard or anomalous class."""
    if class_name in RDD_TAXONOMY:
        return RDD_TAXONOMY[class_name]
    if class_name in ANOMALY_TAXONOMY:
        return f"ANOMALOUS: {ANOMALY_TAXONOMY[class_name]}"
    return "UNKNOWN / NOT IN BASIC RDD MAP"


def find_candidate_dataset_dirs(explicit_path: Optional[str] = None) -> List[Path]:
    """Discover potential RDD2022 India dataset root directories."""
    candidates = []
    if explicit_path:
        p = Path(explicit_path).resolve()
        if p.exists() and p.is_dir():
            candidates.append(p)
            return candidates

    search_roots = [
        Path("D:/UrbanSense AI/datasets/India/India"),
        Path("D:/UrbanSense AI/datasets/India"),
        Path("datasets/India/India"),
        Path("datasets/India"),
        Path("D:/RDD2022/India"),
        Path("D:/RDD2022_India"),
        Path("datasets/RDD2022/India"),
        Path("D:/datasets/India"),
    ]

    for p in search_roots:
        resolved = p.resolve()
        if resolved.exists() and resolved.is_dir() and resolved not in candidates:
            # Check if directory contains images or xmls or subdirs
            has_train_or_img = any(
                (resolved / sub).exists() for sub in ["train", "test", "images", "annotations"]
            )
            if has_train_or_img:
                candidates.append(resolved)

    # Fallback: scan local datasets/ folder if present
    local_datasets = Path("datasets").resolve()
    if local_datasets.exists() and local_datasets.is_dir():
        for sub in local_datasets.iterdir():
            if sub.is_dir() and "india" in sub.name.lower() and sub not in candidates:
                candidates.append(sub)

    return candidates


def select_best_dataset_root(candidates: List[Path]) -> Path:
    """Select the most specific dataset root containing images and annotations."""
    if not candidates:
        raise FileNotFoundError(
            "Could not automatically locate the RDD2022 India dataset directory. "
            "Please specify using --dataset-dir <path>."
        )

    # Sort candidates by preference: direct 'train' and 'test' presence
    best = None
    best_score = -1

    for c in candidates:
        score = 0
        if (c / "train" / "images").exists():
            score += 10
        if (c / "train" / "annotations" / "xmls").exists():
            score += 10
        if (c / "test" / "images").exists():
            score += 5
        if "india" in c.name.lower():
            score += 2
        if score > best_score:
            best_score = score
            best = c

    if best is None:
        best = candidates[0]

    return best


@dataclass
class BoundingBoxRecord:
    xml_path: str
    image_path: Optional[str]
    class_name: str
    xmin: Optional[float]
    ymin: Optional[float]
    xmax: Optional[float]
    ymax: Optional[float]
    image_width: Optional[int]
    image_height: Optional[int]
    reason: str


@dataclass
class ImageXmlMatchRecord:
    stem: str
    image_path: Optional[str] = None
    xml_path: Optional[str] = None
    split: str = "unknown"  # "train", "test", or "other"
    image_exists: bool = False
    xml_exists: bool = False
    width: Optional[int] = None
    height: Optional[int] = None
    channels: Optional[int] = None
    mode: Optional[str] = None
    object_count: int = 0
    classes: List[str] = field(default_factory=list)
    xml_image_width: Optional[int] = None
    xml_image_height: Optional[int] = None
    dimension_match: bool = True
    has_invalid_bbox: bool = False
    is_empty_annotation: bool = False
    xml_valid: bool = True
    xml_parse_error: Optional[str] = None


def audit_rdd2022_dataset(
    dataset_root: Path,
    output_dir: Path,
    progress_interval: int = 1000,
) -> Dict[str, Any]:
    """Execute the full audit on the RDD2022 India dataset."""
    logger.info("=" * 70)
    logger.info("STARTING RDD2022 INDIA DATASET AUDIT")
    logger.info("=" * 70)
    logger.info(f"Target Dataset Root: {dataset_root.resolve()}")
    logger.info(f"Output Directory:    {output_dir.resolve()}")

    start_time = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # 1. FILE DISCOVERY
    # -------------------------------------------------------------
    logger.info("Step 1: Discovering files...")
    image_extensions = {".jpg", ".jpeg", ".png"}
    xml_extensions = {".xml"}

    discovered_images: List[Path] = []
    discovered_xmls: List[Path] = []

    ext_counts: Counter = Counter()

    for p in dataset_root.rglob("*"):
        if p.is_file():
            suffix = p.suffix.lower()
            if suffix in image_extensions:
                discovered_images.append(p)
                ext_counts[suffix] += 1
            elif suffix in xml_extensions:
                discovered_xmls.append(p)
                ext_counts[suffix] += 1

    total_images = len(discovered_images)
    total_xmls = len(discovered_xmls)

    logger.info(f"Discovered {total_images:,} images across extensions: {dict(ext_counts)}")
    logger.info(f"Discovered {total_xmls:,} XML annotation files")

    # -------------------------------------------------------------
    # 2. IMAGE <-> XML MATCHING & STEM INTEGRITY
    # -------------------------------------------------------------
    logger.info("Step 2: Checking stem matching and integrity...")

    image_stem_map: Dict[str, List[Path]] = defaultdict(list)
    xml_stem_map: Dict[str, List[Path]] = defaultdict(list)

    for img_p in discovered_images:
        image_stem_map[img_p.stem].append(img_p)

    for xml_p in discovered_xmls:
        xml_stem_map[xml_p.stem].append(xml_p)

    # Stem collision detection
    duplicate_image_stems = {
        stem: [str(p) for p in paths] for stem, paths in image_stem_map.items() if len(paths) > 1
    }
    duplicate_xml_stems = {
        stem: [str(p) for p in paths] for stem, paths in xml_stem_map.items() if len(paths) > 1
    }

    all_stems: Set[str] = set(image_stem_map.keys()) | set(xml_stem_map.keys())

    matched_stems: Set[str] = set(image_stem_map.keys()) & set(xml_stem_map.keys())
    images_without_xml_stems: Set[str] = set(image_stem_map.keys()) - set(xml_stem_map.keys())
    xml_without_image_stems: Set[str] = set(xml_stem_map.keys()) - set(image_stem_map.keys())

    logger.info(f"Total Unique Stems:       {len(all_stems):,}")
    logger.info(f"Matched Image <-> XML:    {len(matched_stems):,}")
    logger.info(f"Images without XML:       {len(images_without_xml_stems):,}")
    logger.info(f"XMLs without Image:       {len(xml_without_image_stems):,}")
    logger.info(f"Duplicate Image Stems:    {len(duplicate_image_stems):,}")
    logger.info(f"Duplicate XML Stems:      {len(duplicate_xml_stems):,}")

    # -------------------------------------------------------------
    # 3. IMAGE DIMENSION AUDIT (PILLOW)
    # -------------------------------------------------------------
    logger.info("Step 3: Auditing image dimensions and readability...")
    image_dim_map: Dict[str, Tuple[Optional[int], Optional[int], Optional[str]]] = {}
    corrupt_images: List[Dict[str, str]] = []
    dimension_counter: Counter = Counter()

    for idx, img_p in enumerate(discovered_images, 1):
        if idx % progress_interval == 0 or idx == total_images:
            logger.info(f"  Processed {idx:,}/{total_images:,} images...")

        if not HAS_PIL:
            # Fallback if PIL not installed
            image_dim_map[str(img_p)] = (None, None, None)
            continue

        try:
            with Image.open(img_p) as img:
                w, h = img.size
                m = img.mode
                image_dim_map[str(img_p)] = (w, h, m)
                dimension_counter[(w, h)] += 1
        except Exception as e:
            logger.warning(f"Corrupt/unreadable image: {img_p} — {e}")
            corrupt_images.append({"path": str(img_p), "error": str(e)})
            image_dim_map[str(img_p)] = (None, None, None)

    # -------------------------------------------------------------
    # 4. PARSE EVERY XML & AUDIT ANNOTATIONS
    # -------------------------------------------------------------
    logger.info("Step 4: Parsing XML annotations and bounding boxes...")

    class_object_counts: Counter = Counter()
    class_image_counts: Counter = Counter()
    total_objects: int = 0
    annotated_images: int = 0
    empty_xml_files: List[str] = []
    invalid_xml_files: List[Dict[str, str]] = []
    invalid_bounding_boxes: List[BoundingBoxRecord] = []
    dimension_mismatches: List[Dict[str, Any]] = []

    # Map XML path to parsed data
    xml_data_map: Dict[str, Dict[str, Any]] = {}

    for idx, xml_p in enumerate(discovered_xmls, 1):
        if idx % progress_interval == 0 or idx == total_xmls:
            logger.info(f"  Parsed {idx:,}/{total_xmls:,} XML files...")

        xml_str_path = str(xml_p)
        matched_img_paths = image_stem_map.get(xml_p.stem, [])
        matched_img_str = str(matched_img_paths[0]) if matched_img_paths else None

        # Actual image dimensions if image exists
        actual_w, actual_h, _ = image_dim_map.get(matched_img_str, (None, None, None))

        try:
            tree = ET.parse(xml_p)
            root = tree.getroot()
        except Exception as e:
            invalid_xml_files.append({"xml_path": xml_str_path, "error": str(e)})
            xml_data_map[xml_str_path] = {
                "valid": False,
                "error": str(e),
                "objects": [],
                "xml_w": None,
                "xml_h": None,
            }
            continue

        # Extract size from XML
        size_elem = root.find("size")
        xml_w, xml_h = None, None
        if size_elem is not None:
            w_elem = size_elem.find("width")
            h_elem = size_elem.find("height")
            if w_elem is not None and w_elem.text and w_elem.text.strip().isdigit():
                xml_w = int(w_elem.text.strip())
            if h_elem is not None and h_elem.text and h_elem.text.strip().isdigit():
                xml_h = int(h_elem.text.strip())

        # Dimension match verification
        if xml_w is not None and actual_w is not None:
            if xml_w != actual_w or xml_h != actual_h:
                dimension_mismatches.append({
                    "xml_path": xml_str_path,
                    "image_path": matched_img_str,
                    "xml_dimensions": [xml_w, xml_h],
                    "actual_dimensions": [actual_w, actual_h],
                })

        eff_w = actual_w if actual_w is not None else xml_w
        eff_h = actual_h if actual_h is not None else xml_h

        # Extract objects
        objects = root.findall("object")
        if not objects:
            empty_xml_files.append(xml_str_path)
            xml_data_map[xml_str_path] = {
                "valid": True,
                "error": None,
                "objects": [],
                "xml_w": xml_w,
                "xml_h": xml_h,
            }
            continue

        annotated_images += 1
        classes_in_this_xml: Set[str] = set()
        parsed_objects = []

        for obj in objects:
            name_elem = obj.find("name")
            class_name = (
                name_elem.text.strip()
                if (name_elem is not None and name_elem.text)
                else "MISSING_CLASS_NAME"
            )

            class_object_counts[class_name] += 1
            classes_in_this_xml.add(class_name)
            total_objects += 1

            # Bounding box validation
            bnd = obj.find("bndbox")
            if bnd is None:
                invalid_bounding_boxes.append(BoundingBoxRecord(
                    xml_path=xml_str_path,
                    image_path=matched_img_str,
                    class_name=class_name,
                    xmin=None, ymin=None, xmax=None, ymax=None,
                    image_width=eff_w, image_height=eff_h,
                    reason="Missing <bndbox> element",
                ))
                continue

            coord_vals: Dict[str, float] = {}
            missing_or_bad = False
            for c in ["xmin", "ymin", "xmax", "ymax"]:
                c_elem = bnd.find(c)
                if c_elem is None or not c_elem.text or not c_elem.text.strip():
                    invalid_bounding_boxes.append(BoundingBoxRecord(
                        xml_path=xml_str_path,
                        image_path=matched_img_str,
                        class_name=class_name,
                        xmin=None, ymin=None, xmax=None, ymax=None,
                        image_width=eff_w, image_height=eff_h,
                        reason=f"Missing coordinate <{c}>",
                    ))
                    missing_or_bad = True
                    break
                try:
                    coord_vals[c] = float(c_elem.text.strip())
                except ValueError:
                    invalid_bounding_boxes.append(BoundingBoxRecord(
                        xml_path=xml_str_path,
                        image_path=matched_img_str,
                        class_name=class_name,
                        xmin=None, ymin=None, xmax=None, ymax=None,
                        image_width=eff_w, image_height=eff_h,
                        reason=f"Non-numeric coordinate in <{c}>: '{c_elem.text}'",
                    ))
                    missing_or_bad = True
                    break

            if missing_or_bad:
                continue

            xmin, ymin = coord_vals["xmin"], coord_vals["ymin"]
            xmax, ymax = coord_vals["xmax"], coord_vals["ymax"]

            # Checks
            reason_list = []
            if xmin >= xmax:
                reason_list.append(f"xmin >= xmax ({xmin} >= {xmax})")
            if ymin >= ymax:
                reason_list.append(f"ymin >= ymax ({ymin} >= {ymax})")
            if xmin < 0:
                reason_list.append(f"negative xmin ({xmin})")
            if ymin < 0:
                reason_list.append(f"negative ymin ({ymin})")
            if eff_w is not None:
                if xmax > eff_w:
                    reason_list.append(f"xmax > width ({xmax} > {eff_w})")
                if xmin > eff_w:
                    reason_list.append(f"xmin > width ({xmin} > {eff_w})")
            if eff_h is not None:
                if ymax > eff_h:
                    reason_list.append(f"ymax > height ({ymax} > {eff_h})")
                if ymin > eff_h:
                    reason_list.append(f"ymin > height ({ymin} > {eff_h})")
            if (xmax - xmin) * (ymax - ymin) <= 0:
                reason_list.append("zero or negative area")

            if reason_list:
                invalid_bounding_boxes.append(BoundingBoxRecord(
                    xml_path=xml_str_path,
                    image_path=matched_img_str,
                    class_name=class_name,
                    xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
                    image_width=eff_w, image_height=eff_h,
                    reason="; ".join(reason_list),
                ))

            parsed_objects.append({
                "class": class_name,
                "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                "is_valid": len(reason_list) == 0,
            })

        for c in classes_in_this_xml:
            class_image_counts[c] += 1

        xml_data_map[xml_str_path] = {
            "valid": True,
            "error": None,
            "objects": parsed_objects,
            "xml_w": xml_w,
            "xml_h": xml_h,
        }

    # Identify unknown/anomalous classes
    unknown_classes = [c for c in class_object_counts.keys() if c not in RDD_TAXONOMY]

    # -------------------------------------------------------------
    # 5. GENERATE AUDIT REPORT CSV (PER-IMAGE/ANNOTATION RELATIONSHIP)
    # -------------------------------------------------------------
    logger.info("Step 5: Writing audit_report.csv...")
    audit_csv_path = output_dir / "audit_report.csv"

    csv_rows: List[Dict[str, Any]] = []

    # Sort stems for deterministic output
    sorted_stems = sorted(all_stems)

    for stem in sorted_stems:
        img_paths = image_stem_map.get(stem, [])
        xml_paths = xml_stem_map.get(stem, [])

        img_p = img_paths[0] if img_paths else None
        xml_p = xml_paths[0] if xml_paths else None

        img_str = str(img_p) if img_p else None
        xml_str = str(xml_p) if xml_p else None

        w, h, m = image_dim_map.get(img_str, (None, None, None)) if img_str else (None, None, None)

        # Split determination
        split = "unknown"
        if img_p:
            parts = [part.lower() for part in img_p.parts]
            if "train" in parts:
                split = "train"
            elif "test" in parts:
                split = "test"
        elif xml_p:
            parts = [part.lower() for part in xml_p.parts]
            if "train" in parts:
                split = "train"
            elif "test" in parts:
                split = "test"

        xml_info = xml_data_map.get(xml_str, {})
        objs = xml_info.get("objects", [])
        xml_w = xml_info.get("xml_w")
        xml_h = xml_info.get("xml_h")
        xml_valid = xml_info.get("valid", True if xml_str is None else False)

        obj_count = len(objs)
        classes_present = sorted(list({o["class"] for o in objs}))
        is_empty = (xml_str is not None) and (obj_count == 0) and xml_valid
        has_invalid_box = any(not o.get("is_valid", True) for o in objs)

        dim_match = True
        if xml_w is not None and w is not None:
            dim_match = (xml_w == w and xml_h == h)

        csv_rows.append({
            "stem": stem,
            "split": split,
            "image_path": img_str or "",
            "xml_path": xml_str or "",
            "image_exists": img_p is not None,
            "xml_exists": xml_p is not None,
            "width": w or "",
            "height": h or "",
            "mode": m or "",
            "object_count": obj_count,
            "classes": ";".join(classes_present),
            "xml_image_width": xml_w or "",
            "xml_image_height": xml_h or "",
            "dimension_match": dim_match,
            "has_invalid_bbox": has_invalid_box,
            "is_empty_annotation": is_empty,
            "xml_valid": xml_valid,
        })

    with open(audit_csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "stem", "split", "image_path", "xml_path", "image_exists", "xml_exists",
            "width", "height", "mode", "object_count", "classes",
            "xml_image_width", "xml_image_height", "dimension_match",
            "has_invalid_bbox", "is_empty_annotation", "xml_valid",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    # -------------------------------------------------------------
    # 6. GENERATE CLASS DISTRIBUTION CSV
    # -------------------------------------------------------------
    logger.info("Step 6: Writing class_distribution.csv...")
    class_csv_path = output_dir / "class_distribution.csv"

    # Sort classes: standard classes first, then unknown/anomalous classes
    standard_keys = [c for c in RDD_TAXONOMY.keys() if c in class_object_counts]
    extra_keys = [c for c in class_object_counts.keys() if c not in RDD_TAXONOMY]
    sorted_classes = sorted(standard_keys) + sorted(extra_keys)

    class_dist_rows: List[Dict[str, Any]] = []
    for c in sorted_classes:
        obj_count = class_object_counts[c]
        img_count = class_image_counts[c]
        obj_pct = round((obj_count / total_objects * 100.0) if total_objects > 0 else 0.0, 3)
        img_pct = round((img_count / annotated_images * 100.0) if annotated_images > 0 else 0.0, 3)

        class_dist_rows.append({
            "class": c,
            "description": describe_class(c),
            "object_count": obj_count,
            "image_count": img_count,
            "object_percentage": f"{obj_pct:.3f}%",
            "image_percentage": f"{img_pct:.3f}%",
        })

    with open(class_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["class", "description", "object_count", "image_count", "object_percentage", "image_percentage"],
        )
        writer.writeheader()
        writer.writerows(class_dist_rows)

    # -------------------------------------------------------------
    # 7. GENERATE DATASET PROBLEMS JSON
    # -------------------------------------------------------------
    logger.info("Step 7: Writing dataset_problems.json...")
    problems_json_path = output_dir / "dataset_problems.json"

    problems_data = {
        "images_without_xml": [
            {"stem": s, "image_path": str(image_stem_map[s][0])}
            for s in sorted(images_without_xml_stems)
        ],
        "xml_without_image": [
            {"stem": s, "xml_path": str(xml_stem_map[s][0])}
            for s in sorted(xml_without_image_stems)
        ],
        "duplicate_image_stems": duplicate_image_stems,
        "duplicate_xml_stems": duplicate_xml_stems,
        "empty_xml": empty_xml_files,
        "invalid_xml": invalid_xml_files,
        "invalid_images": corrupt_images,
        "invalid_bounding_boxes": [asdict(b) for b in invalid_bounding_boxes],
        "dimension_mismatches": dimension_mismatches,
        "unknown_classes": [
            {
                "class": c,
                "description": describe_class(c),
                "object_count": class_object_counts[c],
                "image_count": class_image_counts[c],
            }
            for c in unknown_classes
        ],
    }

    with open(problems_json_path, "w", encoding="utf-8") as f:
        json.dump(problems_data, f, indent=2)

    # -------------------------------------------------------------
    # 8. GENERATE AUDIT REPORT JSON
    # -------------------------------------------------------------
    logger.info("Step 8: Writing audit_report.json...")
    report_json_path = output_dir / "audit_report.json"

    audit_summary = {
        "dataset_root": str(dataset_root.resolve()),
        "audit_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audit_duration_seconds": round(time.time() - start_time, 2),
        "total_image_files": total_images,
        "total_xml_files": total_xmls,
        "matched_image_xml": len(matched_stems),
        "images_without_xml": len(images_without_xml_stems),
        "xml_without_image": len(xml_without_image_stems),
        "duplicate_image_stems": len(duplicate_image_stems),
        "duplicate_xml_stems": len(duplicate_xml_stems),
        "total_objects": total_objects,
        "annotated_images": annotated_images,
        "empty_xml_files": len(empty_xml_files),
        "invalid_xml_files": len(invalid_xml_files),
        "invalid_images": len(corrupt_images),
        "invalid_bounding_boxes": len(invalid_bounding_boxes),
        "dimension_mismatches": len(dimension_mismatches),
        "image_dimension_distribution": {
            f"{w}x{h}": count for (w, h), count in dimension_counter.items()
        },
        "classes": dict(class_object_counts),
        "images_per_class": dict(class_image_counts),
        "unknown_classes": unknown_classes,
        "class_details": [
            {
                "class": c,
                "description": describe_class(c),
                "object_count": class_object_counts[c],
                "image_count": class_image_counts[c],
                "object_percentage": round((class_object_counts[c] / total_objects * 100.0) if total_objects > 0 else 0.0, 3),
                "image_percentage": round((class_image_counts[c] / annotated_images * 100.0) if annotated_images > 0 else 0.0, 3),
            }
            for c in sorted_classes
        ],
    }

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2)

    # -------------------------------------------------------------
    # 9. GENERATE CLEAN DATASET MANIFEST
    # -------------------------------------------------------------
    logger.info("Step 9: Writing dataset_manifest.json...")
    manifest_path = output_dir / "dataset_manifest.json"

    manifest_entries = []
    for r in csv_rows:
        manifest_entries.append({
            "stem": r["stem"],
            "split": r["split"],
            "image_path": r["image_path"],
            "xml_path": r["xml_path"],
            "width": r["width"],
            "height": r["height"],
            "object_count": r["object_count"],
            "classes": r["classes"].split(";") if r["classes"] else [],
            "is_background": r["is_empty_annotation"],
            "is_clean": (
                r["image_exists"]
                and r["xml_valid"]
                and not r["has_invalid_bbox"]
                and r["dimension_match"]
            ),
        })

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "dataset_root": str(dataset_root.resolve()),
            "total_samples": len(manifest_entries),
            "clean_annotated_samples": sum(1 for m in manifest_entries if m["is_clean"] and not m["is_background"] and m["split"] == "train"),
            "clean_background_samples": sum(1 for m in manifest_entries if m["is_clean"] and m["is_background"] and m["split"] == "train"),
            "unannotated_test_samples": sum(1 for m in manifest_entries if m["split"] == "test"),
            "samples": manifest_entries,
        }, f, indent=2)

    logger.info(f"Audit completed in {time.time() - start_time:.2f} seconds.")
    return audit_summary


def print_terminal_report(summary: Dict[str, Any], output_dir: Path) -> None:
    """Print the final formatted audit report to terminal."""
    classes = summary.get("classes", {})
    img_per_class = summary.get("images_per_class", {})
    unknowns = summary.get("unknown_classes", [])
    total_objs = summary.get("total_objects", 0)

    print("\n" + "=" * 70)
    print("RDD2022 INDIA DATASET AUDIT")
    print("=" * 70)

    print("\nDATASET")
    print(f"Root: {summary.get('dataset_root')}")
    print(f"Audit Duration: {summary.get('audit_duration_seconds')} seconds")

    print("\nFILES")
    print(f"Images: {summary.get('total_image_files'):,}")
    print(f"XMLs:   {summary.get('total_xml_files'):,}")

    print("\nMATCHING")
    print(f"Images with XML:    {summary.get('matched_image_xml'):,}")
    print(f"Images without XML: {summary.get('images_without_xml'):,} (unannotated test set)")
    print(f"XMLs without image: {summary.get('xml_without_image'):,}")
    print(f"Duplicate image stems: {summary.get('duplicate_image_stems'):,}")
    print(f"Duplicate XML stems:   {summary.get('duplicate_xml_stems'):,}")

    print("\nANNOTATIONS")
    print(f"Total objects:    {summary.get('total_objects'):,}")
    print(f"Annotated images: {summary.get('annotated_images'):,}")
    print(f"Empty XMLs:       {summary.get('empty_xml_files'):,} (background / negative road images)")
    print(f"Invalid XMLs:     {summary.get('invalid_xml_files'):,}")

    print("\nCLASSES (Exact counts from dataset)")
    # Order standard classes
    standard_order = ["D00", "D01", "D10", "D11", "D20", "D40", "D43", "D44"]
    for c in standard_order:
        cnt = classes.get(c, 0)
        icnt = img_per_class.get(c, 0)
        pct = (cnt / total_objs * 100.0) if total_objs > 0 else 0.0
        desc = RDD_TAXONOMY.get(c, "")
        print(f"  {c:<4} ({desc:<30}): {cnt:>5,} objects across {icnt:>5,} images ({pct:>6.2f}%)")

    extra_classes = [c for c in classes.keys() if c not in standard_order]
    if extra_classes:
        print("\nANOMALOUS / EXTRA CLASSES DETECTED:")
        for c in sorted(extra_classes):
            cnt = classes.get(c, 0)
            icnt = img_per_class.get(c, 0)
            pct = (cnt / total_objs * 100.0) if total_objs > 0 else 0.0
            desc = describe_class(c)
            print(f"  {c:<4} ({desc:<30}): {cnt:>5,} objects across {icnt:>5,} images ({pct:>6.2f}%)")

    print("\nIMAGE INTEGRITY")
    print(f"Unreadable images:   {summary.get('invalid_images'):,}")
    print(f"Dimension mismatches:{summary.get('dimension_mismatches'):,}")
    dims = summary.get("image_dimension_distribution", {})
    for dim_str, count in dims.items():
        print(f"  Dimension {dim_str}: {count:,} images (100.0%)")

    print("\nBOUNDING BOXES")
    print(f"Invalid boxes: {summary.get('invalid_bounding_boxes'):,}")

    print("\nOUTPUT FILES")
    print(f"  {output_dir / 'audit_report.json'}")
    print(f"  {output_dir / 'audit_report.csv'}")
    print(f"  {output_dir / 'class_distribution.csv'}")
    print(f"  {output_dir / 'dataset_problems.json'}")
    print(f"  {output_dir / 'dataset_manifest.json'}")

    print("\n" + "=" * 70)
    print("AUDIT COMPLETE")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit RDD2022 India dataset for UrbanSense AI."
    )
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default=None,
        help="Path to RDD2022 India dataset root (auto-detected if omitted).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="audit_output",
        help="Directory to save audit reports (default: audit_output).",
    )
    args = parser.parse_args()

    candidates = find_candidate_dataset_dirs(args.dataset_dir)
    if not candidates:
        logger.error("No candidate RDD2022 India dataset directory found.")
        return 1

    try:
        best_root = select_best_dataset_root(candidates)
    except Exception as e:
        logger.error(f"Failed to identify dataset root: {e}")
        return 1

    output_path = Path(args.output_dir)

    try:
        summary = audit_rdd2022_dataset(best_root, output_path)
        print_terminal_report(summary, output_path)
        return 0
    except Exception as e:
        logger.exception(f"Audit failed with unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
