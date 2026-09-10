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
3. Install dependencies with [uv](https://docs.astral.sh/uv/) (installs `uv sync` from
   `uv.lock`, so everyone gets the exact same resolved versions):
   ```bash
   uv sync
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

## Voice agent app (`agent/`)

The trained model above is wired into a full incident-response workflow: YOLO detects,
an employee physically verifies, and a Google Gemini voice agent takes it from there --
collecting incident details by voice, generating a structured report, routing it to the
right authority, and placing/handling an outbound Twilio call to request dispatch.
Orchestration and state live in a LangGraph graph (`agent/graph/workflow.py`); YOLO,
Gemini, and Twilio are each confined to a single responsibility (detection, reasoning,
telephony) and only ever exposed through provider interfaces
(`agent/providers/base.py`), so swapping either the LLM or telephony backend never
touches graph/route code.

```
YOLO Detection -> Display -> Employee Verification -> (false? -> END)
  -> Gemini Voice Agent collects & validates incident info
  -> Generate Report -> Determine Authority -> Send Report
  -> Twilio Outbound Call -> Gemini <-> Authority Conversation -> Update Incident -> END
```

### Run it

```bash
uv sync
cp .env.example .env   # fill in GEMINI_API_KEY / TWILIO_* for real mode
uv run uvicorn agent.main:app --reload
```

Open `http://localhost:8000/dashboard/` for the employee dashboard (upload a frame,
verify the detection, then talk to the voice agent through the browser mic).

Set `LLM_PROVIDER=mock` and `TELEPHONY_PROVIDER=mock` (the `.env.example` default) to
run the entire workflow -- including the "Gemini" and "Twilio" steps -- with no API
keys at all, useful for development and CI. Switch both to `gemini`/`twilio` once you
have real credentials; nothing else changes.

`config/authority_mapping.yaml` is the external CLASS -> AUTHORITY -> PHONE ->
REPORT_ENDPOINT table the graph's `determine_authority` node reads; edit it (or the
`AUTHORITY_*` env vars it references) to change routing without touching code.

### Tests

```bash
uv run pytest tests/
```

`tests/test_workflow_mock.py` drives the whole LangGraph workflow end-to-end with the
mock providers, asserting the detection fields are never mutated downstream, the
false-positive branch only triggers on the employee's own decision (via the dashboard
button or an explicit voice flag), missing-field validation loops the collection step,
and the graph reaches `closed` with a complete report and authority response.
