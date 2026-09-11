"""Run the fine-tuned Raqeeb detector over a video with multi-object tracking.

Plain detection re-decides every frame independently, so boxes flicker and the same
gun is counted once per frame. Tracking associates detections across frames, so each
threat keeps a stable ID for as long as it is on the belt -- which is what turns
"5,000 detections" into "3 distinct weapons went through this checkpoint".

Usage:
    python track_video.py test_clip.mp4
    python track_video.py test_clip.mp4 --model best_yolov8n.pt --conf 0.4
    python track_video.py test_clip.mp4 --tracker bytetrack.yaml --no-trails
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

# Distinct BGR colours cycled per track ID, so two bags side by side never share one.
TRACK_COLORS = [
    (56, 56, 255), (151, 157, 255), (31, 112, 255), (29, 178, 255),
    (49, 210, 207), (10, 249, 72), (23, 204, 146), (134, 219, 61),
    (52, 147, 26), (187, 212, 0), (168, 153, 44), (255, 194, 0),
    (147, 69, 52), (255, 115, 100), (236, 24, 0), (255, 56, 132),
    (133, 0, 82), (255, 56, 203), (200, 149, 255), (199, 55, 255),
]


def color_for(track_id: int) -> tuple[int, int, int]:
    return TRACK_COLORS[int(track_id) % len(TRACK_COLORS)]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("source", help="video file, image folder, or camera index (e.g. 0)")
    p.add_argument("--model", default="best_yolov8s.pt", help="weights to run (default: best_yolov8s.pt)")
    p.add_argument(
        "--tracker",
        default="trackers/raqeeb_botsort.yaml",
        help="tracker config: the tuned repo config, or botsort.yaml / bytetrack.yaml for Ultralytics defaults",
    )
    p.add_argument("--conf", type=float, default=0.25, help="detection confidence threshold (default: 0.25)")
    p.add_argument("--iou", type=float, default=0.7, help="NMS IoU threshold (default: 0.7)")
    p.add_argument("--imgsz", type=int, default=1280,
                   help="inference size. NOT the training size: belt frames show bags smaller than "
                        "the training stills did, so thin objects need upscaling to survive (default: 1280)")
    p.add_argument("--device", default=None, help="cuda device e.g. 0, or cpu (default: auto)")
    p.add_argument("--output", default=None, help="output video path (default: <source>_tracked.mp4)")
    p.add_argument("--trail-len", type=int, default=20, help="motion-trail length in frames (default: 20)")
    p.add_argument("--no-trails", action="store_true", help="shorthand for --trail-len 0")
    p.add_argument(
        "--min-hits",
        type=int,
        default=2,
        help="frames a track must survive to count as a real threat in the summary (default: 2)",
    )
    p.add_argument(
        "--min-conf",
        type=float,
        default=0.5,
        help="peak confidence a track must reach to count as a real threat (default: 0.5)",
    )
    p.add_argument("--show", action="store_true", help="preview in a window while processing")
    p.add_argument("--no-save", action="store_true", help="skip writing the annotated video")
    p.add_argument("--gt", default=None,
                   help="ground-truth JSON from make_test_video.py; scores MOTA/IDF1/ID-switches")
    p.add_argument("--gt-iou", type=float, default=0.5, help="IoU threshold for GT matching (default: 0.5)")
    p.add_argument("--class-agnostic", action="store_true",
                   help="match GT to predictions ignoring class, to separate association errors from misclassification")
    return p.parse_args()


def source_fps(source: str, fallback: float = 30.0) -> float:
    """Read the source frame rate so the output video and the timestamps agree with it."""
    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    fps = cap.get(cv2.CAP_PROP_FPS) if cap.isOpened() else 0.0
    cap.release()
    return fps if fps and fps > 0 else fallback


def draw_track(frame: np.ndarray, poly: np.ndarray, label: str, color: tuple[int, int, int]) -> None:
    """Draw one oriented box plus its label, anchored to the polygon's topmost corner."""
    cv2.polylines(
        frame, [poly.astype(np.int32).reshape(-1, 1, 2)],
        isClosed=True, color=color, thickness=2, lineType=cv2.LINE_AA,
    )

    anchor = poly[poly[:, 1].argmin()]
    x, y = int(anchor[0]), int(anchor[1])
    (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    y = max(y, th + base + 2)
    cv2.rectangle(frame, (x, y - th - base - 2), (x + tw + 4, y), color, -1)
    cv2.putText(frame, label, (x + 2, y - base), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255), 1, cv2.LINE_AA)


def draw_trail(frame: np.ndarray, points: deque, color: tuple[int, int, int]) -> None:
    """Fade in a track's centroid history so the viewer can see where the object came from."""
    pts = list(points)
    for i in range(1, len(pts)):
        weight = i / len(pts)
        cv2.line(frame, pts[i - 1], pts[i], color,
                 thickness=max(1, int(1 + 2 * weight)), lineType=cv2.LINE_AA)


def draw_hud(frame: np.ndarray, text: str) -> None:
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(frame, (0, 0), (tw + 16, th + base + 12), (0, 0, 0), -1)
    cv2.putText(frame, text, (8, th + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA)


def is_confirmed(rec: dict, args: argparse.Namespace) -> bool:
    """Whether a track is a real threat rather than detector noise.

    The two gates catch different failures: the frame count rejects boxes that flicker
    for an instant, while the confidence gate rejects a weak detection that is
    *consistently* weak, which a stopped belt gives a tracker plenty of frames to hold
    onto. Of the two, confidence is by far the stronger lever.

    The defaults are deliberately permissive. Swept over two synthetic belt clips, no
    setting of either gate reached zero missed objects -- the misses are detections the
    model never made, so tightening these only ever trades false alarms for nothing.
    Since a missed weapon costs more than a false alarm, the defaults sit at that miss
    floor and leave the tightening to whoever is willing to accept the risk.
    """
    return rec["frames"] >= args.min_hits and rec["best_conf"] >= args.min_conf


def polygons_and_centers(det, is_obb: bool) -> tuple[np.ndarray, np.ndarray]:
    """Corner polygons and centroids, so oriented and axis-aligned boxes draw the same way."""
    if is_obb:
        return det.xyxyxyxy.cpu().numpy(), det.xywhr[:, :2].cpu().numpy()
    xyxy = det.xyxy.cpu().numpy()
    polys = np.stack(
        [xyxy[:, [0, 1]], xyxy[:, [2, 1]], xyxy[:, [2, 3]], xyxy[:, [0, 3]]], axis=1
    )
    centers = np.stack(
        [(xyxy[:, 0] + xyxy[:, 2]) / 2, (xyxy[:, 1] + xyxy[:, 3]) / 2], axis=1
    )
    return polys, centers


def main() -> None:
    args = parse_args()
    trail_len = 0 if args.no_trails else max(0, args.trail_len)

    src_path = Path(args.source)
    if not src_path.exists() and not args.source.isdigit():
        raise SystemExit(f"source not found: {args.source}")

    fps = source_fps(args.source)
    out_path = Path(args.output) if args.output else src_path.with_name(f"{src_path.stem}_tracked.mp4")

    model = YOLO(args.model)
    names = model.names

    # stream=True yields one Result at a time instead of buffering the whole video in
    # RAM; persist=True keeps tracker state alive across those yields.
    results = model.track(
        source=args.source,
        tracker=args.tracker,
        conf=args.conf,
        iou=args.iou,
        imgsz=args.imgsz,
        device=args.device,
        persist=True,
        stream=True,
        verbose=False,
    )

    writer = None
    trails: dict[int, deque] = {}
    tracks: dict[int, dict] = {}  # one record per ID -- the payoff of tracking over frame-wise detection
    pred_frames: list[dict] = []  # per-frame boxes, only kept when scoring against ground truth
    frame_idx = 0
    t0 = time.perf_counter()

    for result in results:
        frame = result.orig_img.copy()
        h, w = frame.shape[:2]

        if writer is None and not args.no_save:
            writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            if not writer.isOpened():
                raise SystemExit(f"could not open video writer for {out_path}")

        is_obb = result.obb is not None
        det = result.obb if is_obb else result.boxes
        live_ids: set[int] = set()
        frame_objects: list[dict] = []

        # det.id is None on frames where the tracker confirmed nothing.
        if det is not None and len(det) and det.id is not None:
            ids = det.id.int().cpu().tolist()
            classes = det.cls.int().cpu().tolist()
            confs = det.conf.cpu().tolist()
            polys, centers = polygons_and_centers(det, is_obb)

            for tid, cls, conf, poly, center in zip(ids, classes, confs, polys, centers):
                live_ids.add(tid)
                color = color_for(tid)

                if trail_len:
                    trail = trails.setdefault(tid, deque(maxlen=trail_len))
                    trail.append((int(center[0]), int(center[1])))
                    draw_trail(frame, trail, color)
                draw_track(frame, poly.reshape(-1, 2), f"#{tid} {names[cls]} {conf:.2f}", color)

                rec = tracks.get(tid)
                if rec is None:
                    rec = tracks[tid] = {
                        "id": tid, "first_frame": frame_idx, "last_frame": frame_idx,
                        "frames": 0, "best_conf": 0.0, "class_votes": defaultdict(int),
                    }
                rec["last_frame"] = frame_idx
                rec["frames"] += 1
                rec["best_conf"] = max(rec["best_conf"], conf)
                rec["class_votes"][names[cls]] += 1

                if args.gt:
                    frame_objects.append({"id": tid, "cls": cls, "poly": poly.reshape(-1, 2).tolist()})

        if args.gt:
            pred_frames.append({"frame": frame_idx, "objects": frame_objects})

        # Trails of tracks the tracker has dropped would otherwise linger forever.
        for gone in set(trails) - live_ids:
            del trails[gone]

        confirmed = sum(1 for r in tracks.values() if is_confirmed(r, args))
        draw_hud(frame, f"frame {frame_idx}  |  tracking {len(live_ids)}  |  threats seen: {confirmed}")

        if writer is not None:
            writer.write(frame)
        if args.show:
            cv2.imshow("Raqeeb tracking", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        frame_idx += 1

    if writer is not None:
        writer.release()
    if args.show:
        cv2.destroyAllWindows()

    rows = report(tracks, args, frame_idx, time.perf_counter() - t0, fps,
                  out_path if writer is not None else None)
    if args.gt:
        score_against_gt(args, rows, pred_frames)


def score_against_gt(args: argparse.Namespace, rows: list[dict], pred_frames: list[dict]) -> None:
    """Compare the predicted tracks against ground truth from make_test_video.py."""
    from mot_metrics import evaluate, format_report

    gt = json.loads(Path(args.gt).read_text())
    metrics = evaluate(gt["frames"], pred_frames, iou_thr=args.gt_iou,
                       class_aware=not args.class_agnostic)

    gt_counts: dict[str, int] = defaultdict(int)
    for meta in gt["tracks"].values():
        gt_counts[meta["name"]] += 1
    pred_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["confirmed"]:
            pred_counts[r["class"]] += 1

    print(format_report(metrics, dict(gt_counts), dict(pred_counts)))


def report(tracks: dict, args: argparse.Namespace, n_frames: int, elapsed: float,
           fps: float, out_path: Path | None) -> list[dict]:
    """Print the per-track summary and, when a video was written, save it as CSV + JSON."""
    rows = []
    for rec in sorted(tracks.values(), key=lambda r: r["first_frame"]):
        # A track can flip class on a marginal frame; a majority vote over its whole
        # life is steadier than whatever the last frame happened to say.
        rec["class"] = max(rec.pop("class_votes").items(), key=lambda kv: kv[1])[0]
        rec["confirmed"] = is_confirmed(rec, args)
        rec["first_seen_s"] = round(rec["first_frame"] / fps, 2)
        rec["last_seen_s"] = round(rec["last_frame"] / fps, 2)
        rec["best_conf"] = round(rec["best_conf"], 3)
        rows.append(rec)

    confirmed = [r for r in rows if r["confirmed"]]
    print(f"\nProcessed {n_frames} frames in {elapsed:.1f}s ({n_frames / max(elapsed, 1e-9):.1f} fps)")
    print(f"{len(rows)} track(s) started, {len(confirmed)} confirmed (>= {args.min_hits} frames)\n")

    if rows:
        print(f"{'ID':>4}  {'class':<9} {'conf':>5}  {'frames':>6}  {'first':>8}  {'last':>8}  status")
        for r in rows:
            print(
                f"{r['id']:>4}  {r['class']:<9} {r['best_conf']:>5.2f}  {r['frames']:>6}  "
                f"{r['first_seen_s']:>7.2f}s  {r['last_seen_s']:>7.2f}s  "
                f"{'confirmed' if r['confirmed'] else 'transient'}"
            )

        counts: dict[str, int] = defaultdict(int)
        for r in confirmed:
            counts[r["class"]] += 1
        if counts:
            print("\nDistinct threats: " + ", ".join(f"{v}x {k}" for k, v in sorted(counts.items())))

    if out_path is not None:
        base = out_path.with_suffix("")
        fields = ["id", "class", "best_conf", "frames", "first_frame", "last_frame",
                  "first_seen_s", "last_seen_s", "confirmed"]
        with open(f"{base}_tracks.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows({k: r[k] for k in fields} for r in rows)
        with open(f"{base}_tracks.json", "w", encoding="utf-8") as f:
            json.dump(
                {"source": args.source, "model": args.model, "tracker": args.tracker,
                 "fps": fps, "frames": n_frames, "tracks": rows},
                f, indent=2,
            )
        print(f"\nVideo:  {out_path}")
        print(f"Tracks: {base}_tracks.csv / .json")

    return rows


if __name__ == "__main__":
    main()
