"""Synthesise a belt video from the held-out test split, with ground-truth tracks.

No public X-ray security dataset ships video -- every one of them is stills or CT
volumes, because real scanners are line-scan devices that build a single long strip
image as the belt travels. So the honest way to get tracking footage is to build the
strip ourselves out of labelled stills and scroll a viewport across it, propagating
the labels frame by frame as we go.

That propagation is the whole point: it yields ground-truth track IDs, which is what
lets `track_video.py --gt` report MOTA / IDF1 / ID-switches instead of an eyeball
judgement that the boxes "look like they're tracking".

Unlike a plain constant-velocity scroll, this injects the belt behaviour that actually
breaks trackers:

  * stop-and-reverse -- screeners rock the belt back to re-inspect something. Objects
    leave the frame and come back, which is a genuine re-identification test and
    violates the constant-velocity assumption a Kalman filter leans on.
  * speed changes and acceleration ramps
  * truncation at the frame edges as bags enter and leave
  * optional abutting/overlapping bags
  * per-frame gain and noise jitter

Usage:
    python make_test_video.py
    python make_test_video.py --num-images 20 --seed 7 --output belt_hard.mp4
    python make_test_video.py --no-reverse --no-noise      # closer to the easy case
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np
import yaml


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--images", default="Dataset/test/images", help="source image directory")
    p.add_argument("--labels", default="Dataset/test/labels", help="matching YOLO-OBB label directory")
    p.add_argument("--data-yaml", default="Dataset/data.yaml", help="dataset yaml, read for class names")
    p.add_argument("--output", default="belt_test.mp4", help="output video path")
    p.add_argument("--num-images", type=int, default=14, help="bags to place on the belt (default: 14)")
    p.add_argument("--width", type=int, default=960, help="frame width (default: 960)")
    p.add_argument("--height", type=int, default=580, help="frame height (default: 580)")
    p.add_argument("--fps", type=float, default=15.0, help="output frame rate (default: 15)")
    p.add_argument("--speed", type=float, default=18.0, help="cruise belt speed in px/frame (default: 18)")
    p.add_argument("--gap", type=int, default=140, help="mean gap between bags in px (default: 140)")
    p.add_argument("--overlap-prob", type=float, default=0.2,
                   help="chance a bag abuts/overlaps its neighbour (default: 0.2)")
    p.add_argument("--min-visibility", type=float, default=0.35,
                   help="fraction of a box that must be inside frame to be ground truth (default: 0.35)")
    p.add_argument("--max-frames", type=int, default=1500, help="safety cap on video length")
    p.add_argument("--no-reverse", action="store_true", help="disable stop-and-reverse events")
    p.add_argument("--no-noise", action="store_true", help="disable per-frame gain/noise jitter")
    p.add_argument("--no-balance", action="store_true",
                   help="sample images purely at random instead of covering rare classes first")
    p.add_argument("--seed", type=int, default=0, help="random seed, so runs are reproducible")
    return p.parse_args()


def load_labels(path: Path, w: int, h: int) -> list[tuple[int, np.ndarray]]:
    """Read one YOLO-OBB label file into (class, 4x2 pixel polygon) pairs."""
    out = []
    if not path.exists():
        return out
    for line in path.read_text().strip().splitlines():
        parts = line.split()
        if len(parts) != 9:
            continue
        cls = int(parts[0])
        poly = np.array(parts[1:], dtype=np.float64).reshape(4, 2)
        poly[:, 0] *= w
        poly[:, 1] *= h
        out.append((cls, poly))
    return out


def choose_images(img_dir: Path, lbl_dir: Path, n: int, balance: bool, rng: random.Random) -> list[Path]:
    """Pick source images, preferring coverage of rare classes over a blind sample.

    Scissors are only 31 instances in the test split, so a uniform sample of a dozen
    images will usually miss the class entirely and silently leave it untested.
    """
    paths = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
    if not paths:
        raise SystemExit(f"no images found in {img_dir}")
    if not balance:
        return rng.sample(paths, min(n, len(paths)))

    classes_of: dict[Path, set[int]] = {}
    for p in paths:
        lbl = lbl_dir / f"{p.stem}.txt"
        if lbl.exists():
            classes_of[p] = {int(l.split()[0]) for l in lbl.read_text().split("\n") if l.strip()}

    chosen: list[Path] = []
    covered: set[int] = set()
    pool = list(classes_of)
    rng.shuffle(pool)

    # First pass: whatever adds a class we do not have yet.
    for p in sorted(pool, key=lambda p: len(classes_of[p])):
        if len(chosen) >= n:
            break
        if classes_of[p] - covered:
            chosen.append(p)
            covered |= classes_of[p]
    # Then top up at random.
    for p in pool:
        if len(chosen) >= n:
            break
        if p not in chosen:
            chosen.append(p)
    rng.shuffle(chosen)
    return chosen[:n]


BELT_LEVEL = 250.0  # pixel value of empty belt, i.e. the "air" reading of the scanner


def to_transmission(img: np.ndarray) -> np.ndarray:
    """Normalise a bag image to transmission in [0, 1], where 1.0 is empty air.

    Roughly half the Sixray images have a grey (~222) background rather than white.
    Pasted as-is they read as rectangular tiles on the belt, and any overlap stacks
    into a dark rectangle that looks nothing like an X-ray.

    Dividing by each image's own background is not a cosmetic fix, it is the physically
    correct normalisation: an X-ray image is I = I0 * exp(-mu*t), so dividing by the
    unattenuated I0 that the image was captured at leaves pure transmission, which is
    comparable across images taken on different machines at different gains.
    """
    border = np.concatenate([img[0, :, :], img[-1, :, :], img[:, 0, :], img[:, -1, :]])
    i0 = np.median(border, axis=0).astype(np.float32)
    i0[i0 < 1] = 255.0  # a fully dark border means the guess is useless; assume white
    return np.clip(img.astype(np.float32) / i0, 0.0, 1.0)


def build_strip(paths: list[Path], lbl_dir: Path, args: argparse.Namespace,
                rng: random.Random) -> tuple[np.ndarray, list[dict], list[dict]]:
    """Composite the chosen bags into one long belt image and return it with its labels.

    Overlapping bags multiply their transmissions rather than being pasted or min-blended.
    Attenuation is exponential in material thickness, so two objects in the same ray path
    multiply -- which is why an overlap comes out as plausibly superposed material, and
    why two empty backgrounds (1.0 * 1.0) correctly stay empty.
    """
    H = args.height
    placed: list[dict] = []
    tiles: list[tuple[int, int, np.ndarray]] = []
    cursor = args.width // 2  # start with clear belt so the first bag scrolls in
    next_id = 1

    for path in paths:
        img = cv2.imread(str(path))
        if img is None:
            continue
        ih, iw = img.shape[:2]
        scale = rng.uniform(0.62, 0.92) * H / ih
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)

        y0 = int((H - nh) / 2 + rng.uniform(-0.06, 0.06) * H)
        y0 = max(0, min(H - nh, y0))

        if rng.random() < args.overlap_prob and tiles:
            cursor -= int(rng.uniform(0.15, 0.4) * nw)  # abut / overlap the previous bag
        else:
            cursor += int(rng.gauss(args.gap, args.gap * 0.3))
        cursor = max(cursor, 0)
        x0 = cursor
        tiles.append((x0, y0, img))
        cursor = x0 + nw

        for cls, poly in load_labels(lbl_dir / f"{path.stem}.txt", iw, ih):
            p = poly * scale
            p[:, 0] += x0
            p[:, 1] += y0
            placed.append({"id": next_id, "cls": cls, "poly": p, "source": path.name})
            next_id += 1

    strip_w = cursor + args.width
    canvas = np.ones((H, strip_w, 3), dtype=np.float32)  # 1.0 everywhere = empty belt
    for x0, y0, img in tiles:
        nh, nw = img.shape[:2]
        region = canvas[y0:y0 + nh, x0:x0 + nw]
        region *= to_transmission(img)[: region.shape[0], : region.shape[1]]
    strip = np.clip(canvas * BELT_LEVEL, 0, 255).astype(np.uint8)
    # Bag footprints in strip coords, so downstream analysis can tell how many bags
    # a given box is buried under -- the occlusion depth that superposition creates.
    rects = [{"x": x0, "y": y0, "w": img.shape[1], "h": img.shape[0]} for x0, y0, img in tiles]
    return strip, placed, rects


def velocity_profile(strip_w: int, args: argparse.Namespace, rng: random.Random) -> list[float]:
    """Viewport x per frame: cruise, ramp, occasionally stop and reverse.

    Real operators rock the belt backwards to re-inspect a bag. That is the event that
    actually stresses a tracker -- it violates constant velocity and forces objects to
    leave and re-enter, so a tracker must re-identify rather than just extrapolate.
    """
    end = strip_w - args.width
    xs: list[float] = []
    x, v = 0.0, args.speed
    target = args.speed
    frames_until_event = rng.randint(35, 70)

    while x < end and len(xs) < args.max_frames:
        xs.append(x)
        frames_until_event -= 1
        if frames_until_event <= 0:
            roll = rng.random()
            if not args.no_reverse and roll < 0.32:
                target = -args.speed * rng.uniform(0.4, 0.8)   # reverse
                frames_until_event = rng.randint(12, 28)
            elif roll < 0.55:
                target = 0.0                                    # full stop
                frames_until_event = rng.randint(10, 25)
            else:
                target = args.speed * rng.uniform(0.55, 1.35)   # speed change
                frames_until_event = rng.randint(40, 80)
        v += np.clip(target - v, -2.5, 2.5)                     # acceleration ramp
        x = max(0.0, x + v)
    return xs


def visible_polys(placed: list[dict], vx: float, args: argparse.Namespace) -> list[dict]:
    """Ground truth for one frame: shift into view coords, drop what is mostly off-screen."""
    view = np.array([[0, 0], [args.width, 0], [args.width, args.height], [0, args.height]],
                    dtype=np.float32)
    out = []
    for obj in placed:
        poly = obj["poly"].copy()
        poly[:, 0] -= vx
        if poly[:, 0].max() < 0 or poly[:, 0].min() > args.width:
            continue
        p32 = poly.astype(np.float32)
        area = abs(cv2.contourArea(p32))
        if area <= 1:
            continue
        inter, _ = cv2.intersectConvexConvex(p32, view)
        if inter / area >= args.min_visibility:
            out.append({"id": obj["id"], "cls": obj["cls"], "poly": poly.round(2).tolist()})
    return out


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    np.random.seed(args.seed)

    img_dir, lbl_dir = Path(args.images), Path(args.labels)
    if not img_dir.is_dir():
        raise SystemExit(f"image directory not found: {img_dir}  (run EDA.ipynb to fetch the dataset)")

    # Normalised to a list: a dict keyed by int survives yaml but JSON would turn the
    # keys into strings, so anything reading the GT file back would need to know that.
    raw_names = yaml.safe_load(Path(args.data_yaml).read_text())["names"]
    names = [raw_names[i] for i in range(len(raw_names))] if isinstance(raw_names, dict) else list(raw_names)
    paths = choose_images(img_dir, lbl_dir, args.num_images, not args.no_balance, rng)
    strip, placed, bag_rects = build_strip(paths, lbl_dir, args, rng)
    xs = velocity_profile(strip.shape[1], args, rng)

    out_path = Path(args.output)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             args.fps, (args.width, args.height))
    if not writer.isOpened():
        raise SystemExit(f"could not open video writer for {out_path}")

    frames_gt = []
    for i, vx in enumerate(xs):
        x0 = int(vx)
        frame = strip[:, x0:x0 + args.width].copy()
        if frame.shape[1] < args.width:  # pad the tail so the last frames stay full size
            frame = cv2.copyMakeBorder(frame, 0, 0, 0, args.width - frame.shape[1],
                                       cv2.BORDER_CONSTANT, value=(BELT_LEVEL,) * 3)
        if not args.no_noise:
            gain = np.random.normal(1.0, 0.012)
            noise = np.random.normal(0, 2.0, frame.shape)
            frame = np.clip(frame.astype(np.float32) * gain + noise, 0, 255).astype(np.uint8)
        writer.write(frame)
        frames_gt.append({"frame": i, "objects": visible_polys(placed, x0, args)})
    writer.release()

    gt_path = out_path.with_suffix("").with_name(f"{out_path.stem}_gt.json")
    tracked_ids = {o["id"] for f in frames_gt for o in f["objects"]}
    tracks_meta = {
        str(o["id"]): {"cls": o["cls"], "name": names[o["cls"]], "source": o["source"]}
        for o in placed if o["id"] in tracked_ids
    }
    gt_path.write_text(json.dumps({
        "meta": {"width": args.width, "height": args.height, "fps": args.fps,
                 "frames": len(xs), "seed": args.seed, "source_images": [p.name for p in paths],
                 "bags": bag_rects, "viewport_x": [int(x) for x in xs]},
        "names": names,
        "tracks": tracks_meta,
        "frames": frames_gt,
    }, indent=1))

    speeds = np.diff(xs) if len(xs) > 1 else np.zeros(1)
    counts: dict[str, int] = {}
    for t in tracks_meta.values():
        counts[t["name"]] = counts.get(t["name"], 0) + 1

    print(f"Wrote {out_path}  ({len(xs)} frames, {len(xs) / args.fps:.1f}s at {args.fps:g} fps)")
    print(f"Wrote {gt_path}")
    print(f"\n{len(paths)} bags placed, {len(tracks_meta)} ground-truth tracks "
          f"({sum(len(f['objects']) for f in frames_gt)} box instances)")
    print("Ground truth: " + ", ".join(f"{v}x {k}" for k, v in sorted(counts.items())))
    print(f"\nBelt speed: mean {speeds.mean():+.2f} px/frame, std {speeds.std():.2f}, "
          f"range {speeds.min():+.1f}..{speeds.max():+.1f}")
    print(f"  stopped/reversing on {int((speeds <= 0.5).sum())}/{len(speeds)} frames")
    print(f"\nScore a tracker against it:\n  python track_video.py {out_path} --gt {gt_path}")


if __name__ == "__main__":
    main()
