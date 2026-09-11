"""Break detector recall down by occlusion depth, object size and class.

The tracking benchmark says objects go missing on the synthetic belt clips, but not
why. Recommending a training change on a guess is expensive -- a wrong guess costs a
full GPU run -- so this attributes each miss to a measurable property of the box before
anything gets retrained.

Occlusion depth is exact rather than inferred: make_test_video.py records every bag's
footprint, so the number of bags stacked over a given box is a lookup, not a proxy.

Usage:
    python diagnose_recall.py belt_val.mp4 belt_val_gt.json
    python diagnose_recall.py belt_test.mp4 belt_test_gt.json --conf 0.10
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from mot_metrics import poly_iou


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("gt")
    p.add_argument("--model", default="best_yolov8s.pt")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--iou", type=float, default=0.5, help="IoU for calling a GT box detected")
    return p.parse_args()


def depth_at(cx: float, cy: float, vx: int, bags: list[dict]) -> int:
    """How many bag footprints cover this point, in strip coordinates."""
    sx = cx + vx
    return sum(1 for b in bags if b["x"] <= sx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"])


def bucket_report(title: str, groups: dict, order=None) -> None:
    print(f"\n  {title}")
    print(f"    {'bucket':<18} {'GT boxes':>9} {'detected':>9} {'recall':>8}")
    keys = order if order is not None else sorted(groups)
    for k in keys:
        if k not in groups:
            continue
        hit, tot = groups[k]
        print(f"    {str(k):<18} {tot:>9} {hit:>9} {hit / tot if tot else 0:>8.3f}")


def main() -> None:
    args = parse_args()
    gt = json.loads(Path(args.gt).read_text())
    names, bags, vxs = gt["names"], gt["meta"]["bags"], gt["meta"]["viewport_x"]
    gt_by_frame = {f["frame"]: f["objects"] for f in gt["frames"]}

    model = YOLO(args.model)
    by_depth: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    by_class: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_area: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    per_track: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    track_depth: dict[int, list[int]] = defaultdict(list)

    for i, result in enumerate(model.predict(args.video, conf=args.conf, imgsz=args.imgsz,
                                             stream=True, verbose=False)):
        objs = gt_by_frame.get(i, [])
        if not objs:
            continue
        det = result.obb
        preds = []
        if det is not None and len(det):
            polys = det.xyxyxyxy.cpu().numpy()
            classes = det.cls.int().cpu().tolist()
            preds = list(zip(classes, polys))

        vx = vxs[i] if i < len(vxs) else 0
        for o in objs:
            poly = np.array(o["poly"], dtype=np.float32)
            hit = any(c == o["cls"] and poly_iou(poly, p) >= args.iou for c, p in preds)
            area = abs(cv2.contourArea(poly))
            cx, cy = poly[:, 0].mean(), poly[:, 1].mean()
            d = depth_at(cx, cy, vx, bags)
            size = "small (<2k px2)" if area < 2000 else "medium (<10k)" if area < 10000 else "large"

            for bucket, key in ((by_depth, min(d, 3)), (by_class, names[o["cls"]]),
                                (by_area, size), (per_track, o["id"])):
                bucket[key][1] += 1
                bucket[key][0] += hit
            track_depth[o["id"]].append(d)

    print(f"\nDetector recall on {args.video}  (model={args.model}, conf={args.conf}, IoU>={args.iou})")
    bucket_report("by number of bags stacked over the object", by_depth, order=[1, 2, 3])
    bucket_report("by class", by_class)
    bucket_report("by box area", by_area, order=["small (<2k px2)", "medium (<10k)", "large"])

    lost = [(t, h / n, np.mean(track_depth[t])) for t, (h, n) in per_track.items() if n and h / n <= 0.2]
    print(f"\n  {len(lost)} of {len(per_track)} GT tracks were mostly lost (recall <= 0.2)")
    if lost:
        overall_depth = np.mean([d for ds in track_depth.values() for d in ds])
        print(f"    mean stacking depth of lost tracks : {np.mean([d for _, _, d in lost]):.2f}")
        print(f"    mean stacking depth of all boxes   : {overall_depth:.2f}")


if __name__ == "__main__":
    main()
