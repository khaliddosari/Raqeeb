# Raqeeb

Weapon detection on X-ray baggage scans. Fine-tunes YOLOv8-OBB on the Sixray dataset
(5 classes: Gun, Knife, Pliers, Scissors, Wrench) using oriented bounding boxes.

## Just want to run the trained model?

No Roboflow account, no `.env`, no Modal needed for this. Just the weights and `ultralytics`.

```bash
git clone https://github.com/khaliddosari/Raqeeb.git
cd Raqeeb
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

## Tracking objects through a video

`track_video.py` runs the detector over a video and links detections across frames, so
each weapon keeps a stable ID as it travels down the belt instead of being re-detected
from scratch every frame:

```bash
pip install ultralytics lap
python track_video.py test_clip.mp4
```

That writes `test_clip_tracked.mp4` (oriented boxes coloured per track, with the ID,
class, confidence and a motion trail) plus `test_clip_tracked_tracks.csv` / `.json`, and
prints a per-track summary:

```
  ID  class      conf  frames     first      last  status
   1  Gun        0.93      53     0.20s     3.67s  confirmed
   6  Knife      0.83      39     0.53s     3.33s  confirmed
  17  Wrench     0.94      57     8.00s    11.73s  confirmed

Distinct threats: 8x Gun, 2x Knife, 6x Pliers, 4x Wrench
```

That last line is the point of tracking: frame-wise detection on this 25s clip fires
857 times, but there are only 20 actual items. Tracking collapses them into one row per
physical object, with the timestamp it entered and left the scanner.

Useful flags:

| Flag | Default | What it does |
|---|---|---|
| `--model` | `best_yolov8s.pt` | swap in `best_yolov8n.pt` for a faster, slightly weaker run |
| `--tracker` | `trackers/raqeeb_botsort.yaml` | or `botsort.yaml` / `bytetrack.yaml` for Ultralytics defaults |
| `--conf` | `0.25` | raise it to cut false tracks, lower it to keep faint weapons |
| `--min-hits` | `2` | how many frames a track must survive to count as a real threat |
| `--min-conf` | `0.5` | peak confidence a track must reach to count as a real threat |
| `--imgsz` | `1280` | inference size; see the resolution finding below before lowering it |
| `--gt` | off | score against ground truth from `make_test_video.py` (see below) |
| `--trail-len` | `20` | motion-trail length in frames; `--no-trails` turns it off |
| `--fps` | source fps | motion-interpolate the finished clip to this rate, e.g. `60` |
| `--show` | off | live preview window while processing |

The clip is written as H.264, which is the only codec of the plausible options that a
browser will play -- the dashboard embeds this file directly, and MPEG-4 Part 2 renders
as a blank player in Chrome, Edge and Firefox.

`--fps` is presentation only. Tracking has already finished by the time it runs, so the
analysed frame count and every metric below are unchanged; it synthesises intermediate
frames purely for smoother playback, keeping the original duration. The belt's motion is
a near-rigid linear scroll, which is the easy case for motion compensation, so the
overlays stay sharp. It needs ffmpeg (`uv sync` installs one) and takes longer than the
tracking pass itself. The dashboard's demo clip is regenerated with:

```bash
python track_video.py test_clip.mp4 --fps 60 --output static/test_clip_tracked.mp4
```

`trackers/raqeeb_botsort.yaml` is BoT-SORT retuned for this footage — mainly turning off
global motion compensation, which helps handheld video but actively hurts a fixed
scanner camera. The file documents the measured before/after.

## Measuring tracking accuracy

`test_clip.mp4` turns out to be a poor test. Measured by phase correlation across all
375 frame pairs, it is a perfectly rigid scroll: −18.66 px/frame with a standard
deviation of **0.015 px**, no vertical motion, no rotation, no scale change. That is
faithful to the modality — real scanners are line-scan devices that build one long strip
as the belt travels — but it is also the easiest possible motion for a tracker. A
constant-velocity Kalman filter predicts it exactly, so the association logic is never
really under test. The clip also contains no Scissors.

No public dataset fixes this: every X-ray security dataset is stills or CT volumes, none
has video. So `make_test_video.py` builds the footage instead, out of the **831 held-out
test images** — and because it propagates their labels frame by frame, the result comes
with ground-truth track IDs:

```bash
python make_test_video.py --seed 7
python track_video.py belt_test.mp4 --gt belt_test_gt.json
```

It injects the belt behaviour that actually stresses a tracker: stop-and-reverse (real
screeners rock the belt back to re-inspect, which breaks constant velocity and forces
objects to leave and re-enter), speed ramps, edge truncation, overlapping bags, and
per-frame gain/noise jitter. Rare classes are sampled first so Scissors — 31 instances
in the whole test split — actually appears. Bags are composited by multiplying
transmissions after normalising each image by its own background, since attenuation is
exponential in thickness; that is what makes an overlap look like superposed material
rather than a pasted rectangle.

`--gt` then reports CLEAR-MOT and IDF1 (`mot_metrics.py`, using exact convex-polygon
intersection because the boxes are oriented):

| | easy `test_clip.mp4` | seed 7 | seed 21 |
|---|---|---|---|
| MOTA | *(no ground truth)* | 0.697 | 0.659 |
| IDF1 | — | 0.827 | 0.801 |
| MOTP | — | 0.847 | 0.841 |
| ID switches | — | 6 | 2 |
| mostly tracked | — | 23/25 | 21/30 |

### What that turned up

The headline finding is an inference bug, not a model weakness, and no amount of
eyeballing the old clip would have surfaced it.

**Thin objects were being lost to inference resolution.** On the belt clip at the
training size of `imgsz=640`, Wrench recall was **0.016** and Scissors **0.038**. The
obvious reading is that the model never learned those classes. It is wrong -- on the
test stills the same weights get Wrench R=0.886 and Scissors R=0.906. The belt frames
are 960x580 and get letterboxed down to 640, on top of bags already appearing smaller
than the training stills showed them, and thin elongated objects are the first thing to
disappear when you shrink an image:

| `--imgsz` | Wrench recall | Scissors recall | Pliers | speed (CPU) |
|---|---|---|---|---|
| 640 | 0.016 | 0.038 | 0.695 | 20.9 fps |
| 960 | 0.543 | 0.453 | 0.761 | 11.0 fps |
| **1280** | **0.814** | **0.604** | 0.746 | 6.4 fps |

Note the direction: the best `imgsz` is *larger* than the frame is wide. You are not
matching the source resolution, you are restoring objects to the scale the model was
trained to see. That is why `--imgsz` now defaults to 1280 rather than the training 640.

End to end on seed 21, that one change gives:

| | imgsz 640 | imgsz 1280 |
|---|---|---|
| MOTA | 0.659 | **0.786** |
| IDF1 | 0.801 | **0.865** |
| missed boxes | 567 | **346** |
| false positives | 143 | **97** |
| mostly tracked | 21/30 | **26/30** |
| distinct-count error | 5 under, 1 over | **2 under, 1 over** |

Misses and false positives both fell, so this was not a precision/recall trade -- it was
strictly free accuracy that the default was giving away.

**Occlusion is not the problem.** Because `make_test_video.py` records every bag
footprint, occlusion depth is exactly known rather than guessed, and recall at stacking
depth 2 (0.971) is *higher* than at depth 1 (0.731) -- objects in overlapping bags were
slightly easier, not harder. Tracks that got lost were, if anything, less occluded than
average. Superposed clutter is not what this model struggles with, and training more
occlusion augmentation would have been wasted GPU time.

**Counting still lags association.** IDF1 ~0.87 with 4 ID switches says identities hold
well, but the distinct-object count -- the number a screening log would record -- is
still off by a few. Confirmation thresholds only trade false alarms against misses here;
they cannot recover an object the detector never saw.

Two caveats on the numbers. A detection of a real weapon that the Sixray annotators never
labelled scores as a false positive, so false-positive counts are an upper bound. And
these are synthetic clips: they establish that the pipeline is resolution-sensitive and
roughly where the knee is, not a production accuracy figure.

## Full development setup

Only needed to re-run the notebooks, re-download the dataset, or retrain.

1. Clone the repo (the trained weights come with it):
   ```bash
   git clone https://github.com/khaliddosari/Raqeeb.git
   cd Raqeeb
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
- **`track_video.py`**: runs the trained detector over a video with multi-object
  tracking (see above). Inference only -- no dataset or Roboflow key needed.
- **`make_test_video.py`**: synthesises belt footage from the held-out test split with
  ground-truth track IDs, so tracking can be scored rather than eyeballed.
- **`mot_metrics.py`**: CLEAR-MOT and IDF1 for oriented boxes.
- **`diagnose_recall.py`**: attributes detector misses to occlusion depth, object size
  and class, so a fix can be aimed at the actual cause rather than guessed at.
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

`best_yolov8n.pt` and `best_yolov8s.pt` are committed directly to the repo, so a plain
clone gets them. `best_yolov8s.pt` is the current best model. They're also on the Modal
volume:
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
an employee physically verifies, and a voice agent takes it from there -- collecting
incident details by voice, generating a structured report, routing it to the right
authority, and placing/handling an outbound call to request dispatch. Orchestration and
state live in a LangGraph graph (`agent/graph/workflow.py`); detection, reasoning and
telephony are each confined to a single responsibility and only ever exposed through
provider interfaces (`agent/providers/base.py`), so swapping either backend never
touches graph or route code.

```
YOLO Detection -> Display -> Employee Verification -> (false? -> END)
  -> Voice Agent collects & validates incident info
  -> Generate Report -> Determine Authority -> Send Report
  -> Outbound Call -> Agent <-> Authority Conversation -> Update Incident -> END
```

### Providers

Two axes, chosen independently by environment variable and resolved in
`agent/providers/factory.py`:

| | `LLM_PROVIDER` | `TELEPHONY_PROVIDER` |
|---|---|---|
| no credentials | `mock` | `mock` |
| production | `gemini`, `openai` | `twilio`, `signalwire` |

The LLM choice changes how call audio is routed, which is the most consequential
difference in the app:

- **`gemini`** -- Twilio streams the call into our own Media Stream WebSocket at
  `/ws/twilio-media/{incident_id}`, and `agent/voice/authority_call_session.py` bridges
  it to Gemini Live, resampling between Twilio's 8kHz mu-law and Gemini's 16kHz-in /
  24kHz-out PCM.
- **`openai`** -- Twilio instead dials `sip:$OPENAI_PROJECT_ID@sip.api.openai.com`
  directly, so call audio never reaches this server at all. OpenAI announces the call
  through a `realtime.call.incoming` webhook at `/api/openai/webhook`, matched back to
  the incident via an `X-Incident-Id` SIP header. No resampling happens on this path:
  the Realtime API speaks G.711 mu-law at 8kHz, exactly what Twilio Media Streams
  already carry (`wants_raw_telephony_audio` in `agent/providers/base.py`).

`signalwire` is a drop-in for `twilio` -- its Compatibility API mirrors Twilio's, and
both reuse the same webhook routes.

The employee-facing browser-mic session (`/ws/employee/{incident_id}`) is
provider-agnostic and works with whichever LLM is selected.

### Run it

The dashboard is a separate Vite + React app under `frontend/`, and its build output is not
committed, so it has to be built once before the server has anything to serve:

```bash
uv sync
cp .env.example .env

cd frontend && npm install && npm run build && cd ..

uv run uvicorn agent.main:app --reload
```

Open `http://localhost:8000/dashboard/` for the employee dashboard (upload a frame,
verify the detection, then talk to the voice agent through the browser mic).

Skipping the build is the usual first stumble: FastAPI mounts `frontend/dist` only when it
exists, so without it `/dashboard/` is simply a 404 with no hint as to why.

While working on the UI, run the Vite dev server instead and use `http://localhost:5173`.
It serves `frontend/src` directly with hot reload and proxies API and WebSocket calls to
port 8000, so you do not rebuild on every change:

```bash
cd frontend && npm run dev
```

`.env.example` selects the mock providers, so that runs the entire workflow -- report
generation, authority routing and the "call" included -- with no API keys at all. That
is what the test suite and day-to-day development use.

Going live is a matter of filling credentials and switching the two provider variables;
no code changes. The app validates the combination at startup (`validate_settings()` in
`agent/config.py`) and refuses to boot while anything required is missing, naming each
one. That is deliberate: there is no silent fallback to the mocks, because a dispatch
system that quietly stops phoning anyone is a worse failure than one that will not
start. What each combination requires:

| Setting | Requires |
|---|---|
| `LLM_PROVIDER=gemini` | `GEMINI_API_KEY` |
| `LLM_PROVIDER=openai` | `OPENAI_API_KEY`, `OPENAI_WEBHOOK_SECRET` |
| `LLM_PROVIDER=openai` + `TELEPHONY_PROVIDER=twilio` | also `OPENAI_PROJECT_ID` (the SIP destination) |
| `TELEPHONY_PROVIDER=twilio` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| `TELEPHONY_PROVIDER=signalwire` | `SIGNALWIRE_PROJECT_ID`, `SIGNALWIRE_TOKEN`, `SIGNALWIRE_SPACE_URL`, `SIGNALWIRE_PHONE_NUMBER` |

Any non-mock telephony provider also needs `PUBLIC_BASE_URL` pointing at a publicly
reachable HTTPS origin with no trailing slash (`ngrok http 8000` locally), since the
provider calls back into this server. `LLM_PROVIDER=openai` additionally needs a webhook
registered at platform.openai.com for `realtime.call.incoming`, pointing at
`$PUBLIC_BASE_URL/api/openai/webhook`; the `whsec_...` it issues is
`OPENAI_WEBHOOK_SECRET`. Requests are rejected outright when that secret is unset,
rather than verified against an empty key.

`config/authority_mapping.yaml` is the external CLASS -> AUTHORITY -> PHONE ->
REPORT_ENDPOINT table the graph's `determine_authority` node reads; edit it, or set the
`AUTHORITY_*` variables it references, to change routing without touching code. Its
defaults are deliberately unreachable -- an unassignable placeholder number and an
`example-authority.local` endpoint that short-circuits delivery -- so a fresh clone
cannot phone or file against anyone real. Point them at your own number first: once
telephony is not `mock`, a confirmed detection places a genuine call.

### Tests

```bash
uv run pytest tests/
```

`tests/test_workflow_mock.py` drives the whole LangGraph workflow end-to-end with the
mock providers, asserting the detection fields are never mutated downstream, the
false-positive branch only triggers on the employee's own decision (via the dashboard
button or an explicit voice flag), missing-field validation loops the collection step,
and the graph reaches `closed` with a complete report and authority response.
