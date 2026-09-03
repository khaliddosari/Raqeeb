"""Fine-tune a YOLO-OBB model on the Sixray dataset using a Modal GPU container.

Mirrors the logic in Model_Training.ipynb section 2 (dataset download, weighted
oversampling for class imbalance, fine-tune, evaluate) but runs on a remote GPU
instead of locally.

Setup (one-time):
    modal secret create roboflow-secret ROBOFLOW_API_KEY="$ROBOFLOW_API_KEY"

Usage:
    modal run modal_train.py                          # default: yolov8s-obb, 100 epochs
    modal run modal_train.py --epochs 1                # quick timing/sanity check
    modal run modal_train.py --model yolov8n-obb.pt     # back to the nano run
    modal run --detach modal_train.py                  # survives a local terminal disconnect
    modal run --detach modal_train.py --resume-from runs/sixray_yolov8s_obb/weights/last.pt
"""

import modal

app = modal.App("sixray-yolo-training")

volume = modal.Volume.from_name("sixray-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install("ultralytics", "roboflow", "python-dotenv", "pyyaml")
)

VOL_PATH = "/data"
DATASET_DIR = f"{VOL_PATH}/dataset"
RUNS_DIR = f"{VOL_PATH}/runs"

ROBOFLOW_WORKSPACE = "khalid-abdullah-al-dosari"
ROBOFLOW_PROJECT = "sixray-gzyn7"
ROBOFLOW_VERSION = 1


@app.function(
    image=image,
    gpu="A100-40GB",  # cheapest is "T4" (~$0.59/hr), mid is "L4"/"A10" (~$0.80-1.10/hr)
    timeout=5400,  # 1.5h safety cap
    volumes={VOL_PATH: volume},
    secrets=[modal.Secret.from_name("roboflow-secret")],
)
def train(
    model_name: str = "yolov8s-obb.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = -1,
    patience: int = 20,
    close_mosaic: int = 15,
    resume_from: str = "",  # path within the volume to a last.pt, e.g. "runs/sixray_yolov8s_obb/weights/last.pt"
):
    # batch=-1 -> Ultralytics AutoBatch: profiles the GPU at startup and picks the
    # largest batch that fits ~60% of VRAM. The calibration run only used 1.84GB of
    # the L4's 22.5GB at batch=16 -- autobatch fixes that on any GPU tier.
    import os
    import random
    from collections import Counter

    import yaml
    from roboflow import Roboflow
    from ultralytics import YOLO

    # --- 1. Dataset (cached on the volume across runs) ---
    if not os.path.exists(os.path.join(DATASET_DIR, "data.yaml")):
        rf = Roboflow(api_key=os.environ["ROBOFLOW_API_KEY"])
        project = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)
        project.version(ROBOFLOW_VERSION).download("yolov8-obb", location=DATASET_DIR)
        volume.commit()
        print(f"Downloaded dataset to {DATASET_DIR}")
    else:
        print(f"Dataset already cached at {DATASET_DIR}")

    with open(os.path.join(DATASET_DIR, "data.yaml")) as f:
        data_yaml = yaml.safe_load(f)
    class_names = data_yaml["names"]

    # --- 2. Weighted oversampling for class imbalance ---
    train_img_dir = os.path.join(DATASET_DIR, "train", "images")
    train_lbl_dir = os.path.join(DATASET_DIR, "train", "labels")
    stem_to_file = {os.path.splitext(f)[0]: f for f in os.listdir(train_img_dir)}

    stem_to_classes = {}
    class_counts = Counter()
    for stem in stem_to_file:
        lbl_path = os.path.join(train_lbl_dir, stem + ".txt")
        classes = []
        if os.path.exists(lbl_path):
            with open(lbl_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        classes.append(int(parts[0]))
        stem_to_classes[stem] = classes
        class_counts.update(classes)

    max_count = max(class_counts.values())
    inv_freq = {c: max_count / n for c, n in class_counts.items()}

    weighted_paths = []
    for stem, classes in stem_to_classes.items():
        weight = max((inv_freq[c] for c in classes), default=1.0)
        reps = max(1, round(weight))
        weighted_paths.extend([os.path.join(train_img_dir, stem_to_file[stem])] * reps)

    random.seed(42)
    random.shuffle(weighted_paths)

    weighted_list_path = os.path.join(DATASET_DIR, "train_weighted.txt")
    with open(weighted_list_path, "w") as f:
        f.write("\n".join(weighted_paths))

    print(f"Train images: {len(stem_to_file)} -> oversampled to {len(weighted_paths)}")

    # --- 3. Training data.yaml ---
    train_yaml_path = os.path.join(DATASET_DIR, "data_train.yaml")
    train_yaml = {
        "train": weighted_list_path,
        "val": os.path.join(DATASET_DIR, "valid", "images"),
        "test": os.path.join(DATASET_DIR, "test", "images"),
        "names": class_names,
    }
    with open(train_yaml_path, "w") as f:
        yaml.safe_dump(train_yaml, f, sort_keys=False)
    volume.commit()

    # --- 4. Fine-tune ---
    run_name = f"sixray_{os.path.splitext(model_name)[0].replace('-', '_')}"

    if resume_from:
        # Resume reconstructs the trainer from the checkpoint's own saved args
        # (data path, epochs, imgsz, batch, patience, close_mosaic, project/name) --
        # all of which are absolute paths inside this same volume, so they still
        # resolve correctly in a fresh container.
        model = YOLO(os.path.join(VOL_PATH, resume_from))
        model.add_callback("on_fit_epoch_end", lambda trainer: volume.commit())
        model.train(resume=True)
    else:
        model = YOLO(model_name)
        model.add_callback("on_fit_epoch_end", lambda trainer: volume.commit())
        model.train(
            data=train_yaml_path,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            patience=patience,
            close_mosaic=close_mosaic,
            device=0,
            project=RUNS_DIR,
            name=run_name,
            exist_ok=True,
            seed=42,
        )
    volume.commit()

    # --- 5. Evaluate on the held-out test split ---
    best_weights = os.path.join(RUNS_DIR, run_name, "weights", "best.pt")
    best_model = YOLO(best_weights)
    metrics = best_model.val(data=train_yaml_path, split="test", plots=True)
    volume.commit()

    r = metrics.results_dict
    print("\nFine-tuned model on Sixray test set:")
    print(f"  Precision : {r['metrics/precision(B)']:.3f}")
    print(f"  Recall    : {r['metrics/recall(B)']:.3f}")
    print(f"  mAP50     : {r['metrics/mAP50(B)']:.4f}")
    print(f"  mAP50-95  : {r['metrics/mAP50-95(B)']:.4f}")

    return best_weights


@app.local_entrypoint()
def main(
    model_name: str = "yolov8s-obb.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = -1,
    patience: int = 20,
    close_mosaic: int = 15,
    resume_from: str = "",
):
    weights_path = train.remote(
        model_name=model_name,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        patience=patience,
        close_mosaic=close_mosaic,
        resume_from=resume_from,
    )
    relative = weights_path.replace(f"{VOL_PATH}/", "")
    print(f"\nDone. Weights persisted in the Modal volume at: {weights_path}")
    print("Pull them to this machine with:")
    print(f"  modal volume get sixray-data {relative} ./best.pt")
