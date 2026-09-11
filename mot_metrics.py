"""CLEAR-MOT and IDF1 scoring for oriented-box tracks.

Kept separate from `track_video.py` so the metric definitions can be read (and argued
with) without wading through inference code.

Two families of number, and they answer different questions:

  * CLEAR-MOT (MOTA/MOTP/IDSW) is frame-local. It asks "in each frame, did we find the
    right boxes, and did the ID stay the same as last frame?" It punishes a swap once,
    where it happens.
  * IDF1 is track-global. It asks "over the whole clip, was each real object covered by
    one consistent predicted ID?" A tracker that drops an object and re-acquires it
    under a new ID barely dents MOTA but craters IDF1 -- which for threat counting is
    the failure that matters, because it double-counts the weapon.

The standard MOT toolkits assume axis-aligned boxes. These are oriented quads, so
overlap is computed by exact convex-polygon intersection instead of xyxy arithmetic.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

try:
    import cv2
except ImportError as e:  # pragma: no cover
    raise SystemExit("mot_metrics needs opencv-python") from e


def poly_iou(a: np.ndarray, b: np.ndarray) -> float:
    """Exact IoU of two convex quads, via polygon intersection."""
    a32 = np.asarray(a, dtype=np.float32).reshape(-1, 2)
    b32 = np.asarray(b, dtype=np.float32).reshape(-1, 2)
    area_a, area_b = abs(cv2.contourArea(a32)), abs(cv2.contourArea(b32))
    if area_a <= 0 or area_b <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(a32, b32)
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0


def match_frame(gt: list[dict], pred: list[dict], iou_thr: float,
                class_aware: bool) -> list[tuple[int, int, float]]:
    """Optimal one-to-one GT/prediction assignment for a single frame.

    Hungarian rather than greedy: greedy matching by best-IoU-first can strand a pair
    that a global assignment would have matched, which shows up as a phantom ID switch.
    """
    if not gt or not pred:
        return []
    iou = np.zeros((len(gt), len(pred)))
    for i, g in enumerate(gt):
        for j, p in enumerate(pred):
            if class_aware and g["cls"] != p["cls"]:
                continue
            iou[i, j] = poly_iou(g["poly"], p["poly"])

    rows, cols = linear_sum_assignment(-iou)
    return [(int(r), int(c), float(iou[r, c])) for r, c in zip(rows, cols) if iou[r, c] >= iou_thr]


def evaluate(gt_frames: list[dict], pred_frames: list[dict], iou_thr: float = 0.5,
             class_aware: bool = True) -> dict:
    """Score predicted tracks against ground truth. Both are [{frame, objects:[...]}]."""
    gt_by_frame = {f["frame"]: f["objects"] for f in gt_frames}
    pred_by_frame = {f["frame"]: f["objects"] for f in pred_frames}

    n_gt = n_pred = n_match = idsw = 0
    iou_sum = 0.0
    last_partner: dict[int, int] = {}          # gt id -> pred id it was matched to last
    hits_per_gt: dict[int, int] = {}           # gt id -> frames it was matched
    span_per_gt: dict[int, int] = {}           # gt id -> frames it was present
    cooc: dict[tuple[int, int], int] = {}      # (gt id, pred id) -> frames matched together

    for frame in sorted(set(gt_by_frame) | set(pred_by_frame)):
        gt = gt_by_frame.get(frame, [])
        pred = pred_by_frame.get(frame, [])
        n_gt += len(gt)
        n_pred += len(pred)
        for g in gt:
            span_per_gt[g["id"]] = span_per_gt.get(g["id"], 0) + 1

        matches = match_frame(gt, pred, iou_thr, class_aware)
        n_match += len(matches)
        matched_gt_ids = set()
        for gi, pj, iou in matches:
            gid, pid = gt[gi]["id"], pred[pj]["id"]
            matched_gt_ids.add(gid)
            iou_sum += iou
            hits_per_gt[gid] = hits_per_gt.get(gid, 0) + 1
            cooc[(gid, pid)] = cooc.get((gid, pid), 0) + 1
            # An ID switch is only meaningful against the last ID this object had, even
            # if that was several frames ago -- so the record is not cleared on a miss.
            if gid in last_partner and last_partner[gid] != pid:
                idsw += 1
            last_partner[gid] = pid

    fn, fp = n_gt - n_match, n_pred - n_match
    mota = 1.0 - (fn + fp + idsw) / n_gt if n_gt else float("nan")
    motp = iou_sum / n_match if n_match else float("nan")

    # IDF1: one global GT-id <-> pred-id assignment maximising co-occurring frames.
    idtp = 0
    if cooc:
        gids = sorted({g for g, _ in cooc})
        pids = sorted({p for _, p in cooc})
        m = np.zeros((len(gids), len(pids)))
        for (g, p), c in cooc.items():
            m[gids.index(g), pids.index(p)] = c
        rows, cols = linear_sum_assignment(-m)
        idtp = int(m[rows, cols].sum())
    idfp, idfn = n_pred - idtp, n_gt - idtp
    idf1 = 2 * idtp / (2 * idtp + idfp + idfn) if (2 * idtp + idfp + idfn) else float("nan")

    ratios = [hits_per_gt.get(g, 0) / s for g, s in span_per_gt.items() if s]
    return {
        "mota": mota, "motp": motp, "idf1": idf1, "idsw": idsw,
        "tp": n_match, "fp": fp, "fn": fn, "n_gt": n_gt, "n_pred": n_pred,
        "gt_tracks": len(span_per_gt),
        "mostly_tracked": sum(1 for r in ratios if r >= 0.8),
        "partially_tracked": sum(1 for r in ratios if 0.2 < r < 0.8),
        "mostly_lost": sum(1 for r in ratios if r <= 0.2),
        "iou_thr": iou_thr, "class_aware": class_aware,
    }


def format_report(m: dict, gt_counts: dict[str, int], pred_counts: dict[str, int]) -> str:
    """Human-readable block, including the count comparison the belt use case cares about."""
    lines = [
        "",
        f"Tracking accuracy vs ground truth (IoU>={m['iou_thr']}, "
        f"{'class-aware' if m['class_aware'] else 'class-agnostic'} matching)",
        f"  MOTA {m['mota']:6.3f}   overall accuracy: 1 - (misses + false positives + ID switches) / GT",
        f"  IDF1 {m['idf1']:6.3f}   how consistently one predicted ID covers one real object",
        f"  MOTP {m['motp']:6.3f}   mean IoU of the boxes that did match",
        "",
        f"  matched {m['tp']}, missed {m['fn']}, false positives {m['fp']}  "
        f"(of {m['n_gt']} GT boxes, {m['n_pred']} predicted)",
        f"  ID switches: {m['idsw']}",
        f"  of {m['gt_tracks']} GT tracks: {m['mostly_tracked']} mostly tracked, "
        f"{m['partially_tracked']} partial, {m['mostly_lost']} mostly lost",
    ]
    if gt_counts or pred_counts:
        lines += ["", "  Distinct-object count (what a screening log would actually record):",
                  f"    {'class':<10} {'truth':>6} {'counted':>8}"]
        for name in sorted(set(gt_counts) | set(pred_counts)):
            g, p = gt_counts.get(name, 0), pred_counts.get(name, 0)
            flag = "" if g == p else f"   <-- {'over' if p > g else 'under'} by {abs(p - g)}"
            lines.append(f"    {name:<10} {g:>6} {p:>8}{flag}")
    return "\n".join(lines)
