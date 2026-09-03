# Raqeeb

Weapon detection on X-ray baggage scans. Fine-tunes YOLOv8-OBB on the Sixray dataset
(5 classes: Gun, Knife, Pliers, Scissors, Wrench) using oriented bounding boxes.

## Just want to run the trained model?

No Roboflow account, no `.env`, no Modal needed for this. Just the weights and `ultralytics`.

```bash
git clone https://github.com/khaliddosari/Raqeeb.git
cd Raqeeb
git lfs pull          # pulls best_yolov8s.pt / best_yolov8n.pt (skip if git-lfs isn't installed and just download the file manually)
pip install ultralytics
```

```python
from ultralytics import YOLO

model = YOLO("best_yolov8s.pt")
results = model.predict("path/to/an/image.jpg", save=True)

r = results[0]
for cls, conf in zip(r.obb.cls.tolist(), r.obb.conf.tolist()):
    print(model.names[int(cls)], round(conf, 2))
```

`best_yolov8s.pt` is the current best model (mAP50 0.919). `best_yolov8n.pt` is the
smaller/faster earlier version, kept for comparison.

## Full development setup

Only needed to re-run the notebooks, re-download the dataset, or retrain.

1. Clone the repo and pull LFS files (trained weights):
   ```bash
   git clone https://github.com/khaliddosari/Raqeeb.git
   cd Raqeeb
   git lfs pull
   ```
2. Copy `.env.example` to `.env` and fill in your own Roboflow API key:
   ```bash
   cp .env.example .env
   ```
   Get a key at [roboflow.com](https://roboflow.com) with access to the `sixray-gzyn7`
   project, or ask a teammate to add you to the workspace.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Notebooks and scripts

- **`EDA.ipynb`**: dataset exploration, quality checks, class-imbalance analysis, and
  preprocessing decisions. Downloads the dataset via Roboflow on first run.
- **`Model_Training.ipynb`**: zero-shot baseline (why fine-tuning is needed), fine-tuning
  methodology (class-imbalance oversampling), and final results for two model sizes
  (yolov8n-obb, yolov8s-obb).
- **`modal_train.py`**: the actual GPU training job, run on [Modal](https://modal.com).
  Self-contained: re-downloads the dataset and rebuilds the oversampled training list,
  so it doesn't depend on anything from `EDA.ipynb` having run locally.

## Running training on Modal (repo owner only)

Not needed for inference or reviewing results. One-time setup (per Modal account):
```bash
modal setup
modal secret create roboflow-secret ROBOFLOW_API_KEY="$ROBOFLOW_API_KEY"
```

Launch a run:
```bash
modal run --detach modal_train.py
```
`--detach` matters: without it, the job dies if your terminal disconnects. Add
`--resume-from runs/sixray_yolov8s_obb/weights/last.pt` to continue an interrupted run
instead of restarting.

## Trained weights

`best_yolov8n.pt` and `best_yolov8s.pt` are tracked with Git LFS (`git lfs pull` after
cloning). `best_yolov8s.pt` is the current best model. They're also on the Modal volume:
```bash
modal volume get sixray-data runs/sixray_yolov8s_obb/weights/best.pt ./best_yolov8s.pt
```

## Results

| Metric | Zero-shot baseline | yolov8n-obb | yolov8s-obb (best) |
|---|---|---|---|
| mAP50 | 0.004 | 0.901 | 0.919 |
| mAP50-95 | 0.002 | 0.765 | 0.805 |

See `Model_Training.ipynb` for the full per-class breakdown and methodology.
