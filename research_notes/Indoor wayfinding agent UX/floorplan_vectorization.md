# Floor Plan Image Vectorization and Reconstruction into Structured Building Models (as of Oct 2026)

Context: hackathon feature "build a building from floor plans in minutes". Current pipeline is a flat-colour plan PNG, then OpenCV colour-region segmentation, then doors as dots, then a graph, with a VLM reading room labels via set-of-mark. It works perfectly on clean generated plans and is weaker on OSM-derived and Swiss Dwellings plans. Judges' inputs are unknown (could be clean renders or real scans).

## State of the art learned models (RoomFormer, PolyRoom, FRI-Net, HEAT, Raster-to-Graph, Raster2Seq, FloorplanVLM, CubiCasa5k), accuracy, runtime, code, licences

### Takeaway
Raster2Seq (SIGGRAPH 2026, MIT, checkpoints on Hugging Face including a CubiCasa5K one) is the strongest open-weight raster-plan-to-polygon model today: Room F1 88.7 on real CubiCasa5K plans and 99.6 on clean binary Structured3D. Its corner and angle accuracy on real plans is still modest (59.4 and 37.4), and it runs at 256x256. FloorplanVLM (Beike, Qwen2.5-VL-3B) shows the fine-tuned-VLM-to-JSON direction works, but no weights are confirmed released. For a 1-2 day hackathon, keep the OpenCV pipeline as the primary path and add Raster2Seq (cubicasa5k checkpoint) as an optional "real/scanned plan" fallback only if its GPU/CUDA setup goes smoothly.

### Cited Findings
**Raster2Seq (Phung & Averbuch-Elor, Cornell; arXiv 2602.09016, Feb 2026; SIGGRAPH'26)**
- It frames reconstruction as seq2seq: rooms, windows and doors become labeled polygon sequences, decoded autoregressively with learnable anchors in image space — [arXiv](https://arxiv.org/pdf/2602.09016)
- Room/Corner/Angle F1 on Structured3D-B: Raster2Seq 99.6/98.3/92.7; PolyRoom 98.9/96.0/91.9; FRI-Net 96.5/85.4/83.3; RoomFormer 95.1/91.7/83.2; HEAT 94.7/84.5/79.6. Raster2Seq also scores Room semantic 76.9 and Window&Door 98.5 (vs RoomFormer 74.2 / 94.1) — [arXiv HTML Table 1](https://arxiv.org/html/2602.09016v1)
- Room/Corner/Angle F1 on CubiCasa5K (real plans): Raster2Seq 88.7/59.4/37.4; RoomFormer 83.5/55.5/34.1; FRI-Net 77.1/50.8/38.0; HEAT 78.2/53.7/32.3; PolyRoom 54.1/37.1/23.0. Semantic: Raster2Seq 63.8 vs RoomFormer 63.0. Window&Door: RoomFormer 78.5 vs Raster2Seq 77.8 — [arXiv HTML](https://arxiv.org/html/2602.09016v1)
- Room/Corner/Angle F1 on the Raster2Graph dataset: Raster2Seq 97.0/80.3/66.6; Raster2Graph 95.0/78.3/67.3; HEAT 95.9/79.7/50.9; RoomFormer 91.9/74.5/51.1; FRI-Net 91.5/72.3/52.8; PolyRoom 56.9/42.4/23.8 — [arXiv HTML](https://arxiv.org/html/2602.09016v1)
- All experiments use a fixed 256x256 input. Training takes about 1-2 days on one A6000. KV caching is used to speed up generation. The authors flag out-of-distribution, in-the-wild data as needing improvement, and evaluate zero-shot on WAFFLE (about 20K scraped real plans, about 100 annotated) — [arXiv HTML](https://arxiv.org/html/2602.09016v1)
- Weights are MIT-licensed on Hugging Face. Checkpoints: `s3d-bw` (99.6), `cubicasa5k` (88.7), `raster2graph` (97.0), `raster2graph-512` (98.1), `s3d-density` (99.1). Code is at github.com/Cornell-VAILab/Raster2Seq. Usage: `python eval.py --checkpoint hf:cubicasa5k`, or `snapshot_download(repo_id="haopt/Raster2Seq")` — [Hugging Face model card](https://huggingface.co/haopt/Raster2Seq)

**Follow-on analysis (He Zhang, arXiv 2608.25608, Aug 2026)**
- This paper reuses the Raster2Seq backbone and compares autoregressive "emit geometry" readout with detection readout (junction and centerline heatmaps assembled into a graph). On real scans, detection beats sequence decoding on every wall metric: +2.7 wall F1 at tolerance 0.05 and +5.1 at 0.015. On clean vector renders inside the training style, sequence decoding is 5-8 points better. Under full domain shift, detection with calibrated thresholds stays ahead. Fusing the two families deterministically adds 7 points of wall F1 — [arXiv abstract](https://arxiv.org/abs/2608.25608)
- It releases ResPlan-FP (16,998 plans, CC BY 4.0), corrected CubiCasa5K annotations, an "edit-cost" metric, and code at github.com/Cyprinus12138/fpvec-lab — [arXiv abstract](https://arxiv.org/abs/2608.25608)

**FloorplanVLM (Beike; arXiv 2602.06507, Feb 2026)**
- Built on Qwen2.5-VL-3B. It outputs a JSON sequence ordered "structure first, semantics second": walls (ID, endpoints, thickness, curvature, nested openings), then rooms that reference wall IDs. Coordinates are normalized to a 1024 longest edge, 1,391 custom tokens compress keys, and outputs average about 3,000 tokens — [arXiv HTML](https://arxiv.org/html/2602.06507)
- Training is SFT on Floorplan-2M (from more than 20M raw vector plans on an industrial platform), then GRPO on Floorplan-HQ-300K. On FPBench-2K it reports 96.10% validity, 0.9252 exterior-wall IoU, 0.8920 Room IoU, 0.8249 Room F1 and 0.7333 Opening F1. It handles slanted walls and arcs — [arXiv HTML](https://arxiv.org/html/2602.06507)
- There is no comparison against GPT, Gemini or Claude, nor against RoomFormer and similar models. No latency figure is given; it is only described as slower than lightweight CNNs. Only FPBench-2K is said to be open-sourced, and weights and training data are not stated as released — [arXiv HTML](https://arxiv.org/html/2602.06507)
- A community Qwen2.5-VL-3B checkpoint trained with GRPO on CubiCasa5K, citing the paper, is listed (third-party, not official) — [Friendli model page](https://friendli.ai/models/mudasir13cs/qwen25-vl-3b-floorplan-grpo)

**RoomFormer (Yue et al., CVPR 2023)**
- It jointly predicts room polygons, room types, doors and windows using two-level queries, and is faster than previous methods — [CVPR paper](https://openaccess.thecvf.com/content/CVPR2023/html/Yue_Connecting_the_Dots_Floorplan_Reconstruction_Using_Two-Level_Queries_CVPR_2023_paper.html)
- The code is MIT-licensed with checkpoints, but trained on Structured3D and SceneCAD (point-cloud density maps). It was tested on Linux with Python 3.8, PyTorch 1.9 and CUDA 11.1. It needs compiled Deformable-DETR CUDA ops and a BoundaryFormer differentiable rasterizer. No dedicated inference script exists, only eval scripts — [GitHub](https://github.com/ywyue/RoomFormer)

**CubiCasa5K baseline model**
- About 5,000 plans with more than 80 object categories as polygons in SVG. A pretrained multi-task model (`model_best_val_loss_var.pkl`, on Google Drive) works with `eval.py` — [GitHub](https://github.com/CubiCasa/CubiCasa5k)

**Classical/non-learning baseline evidence**
- On colour-coded residential plans, a classical pixel-counting baseline reached 5.68% MAPE for per-room area, versus about 43% MAPE (R² ≈ 0.71) for three open-source VLMs — [Periodica Polytechnica (Aliyev & Barsi)](https://pp.bme.hu/ci/article/view/44138)

### Inferences
- Our colour-segmentation pipeline is effectively the "pixel counting" approach, which beats VLMs badly on clean colour plans. Keep it as the primary path for clean renders.
- For real scans (CubiCasa-style), Raster2Seq's `cubicasa5k` checkpoint is the most practical open-weight drop-in: MIT licence, Hugging Face hosted, and it outputs room polygons with semantics plus doors and windows. Its 256x256 input will lose detail on large or multi-unit plans. Expect about 59% corner F1, so polygons will need snapping and orthogonalization post-processing.
- RoomFormer, HEAT and PolyRoom were primarily built for density maps (point-cloud projections), and PolyRoom collapses on CubiCasa5K (54.1 Room F1). They are not worth hackathon time.
- Compiled CUDA ops (deformable attention) on Windows are a likely time sink. If attempted, run on a Linux GPU box or Colab. This is inferred from RoomFormer's dependencies; Raster2Seq's exact dependencies were not verified.
- FloorplanVLM's design (wall graph first, then rooms referencing walls, with normalized integer coordinates) is a good schema to copy when prompting a frontier VLM, even though the weights are not available.

### Gaps
- No runtime numbers were found for Raster2Seq (Appendix E.4 not read) or FloorplanVLM.
- Raster2Seq's exact install requirements and whether it runs on CPU or Windows were not verified.
- Licences for HEAT, PolyRoom, FRI-Net and Raster-to-Graph code were not verified. Raster-to-Graph appears in Computer Graphics Forum 43(2) (Eurographics 2024) per [EG digital library](https://diglib7.eg.org/bitstream/handle/10.1111/cgf15007/v43i2_03_15007.pdf), but its code and licence were not checked.
- No benchmark of Raster2Seq on OSM-derived or MSD-style plans was found.

## Can frontier VLMs (Claude, GPT, Gemini, Qwen-VL) directly output room polygons/JSON from a plan image?

### Takeaway
No reliable published benchmark shows zero-shot frontier VLMs producing accurate room polygons from plan images. The evidence says they read semantics (room names, counts, connectivity) reasonably well but are weak at metric geometry. Use the VLM for labels, topology and verification, and leave geometry to CV or a specialist model. That is exactly what the current set-of-mark design does.

### Cited Findings
- On FloorplanQA (text-serialized layouts, no images), 15 LLMs including GPT-5, Claude Sonnet 4 and Gemini 2.5 Flash were tested. Claude Sonnet 4 scored 99.8% on pair distance (kitchen) but only 0.2% on free space (living room) and 5% on Max Box (HSSD). The authors conclude LLMs "lack robust internal geometric representations" and recommend pairing them with external geometry solvers — [arXiv 2507.07644](https://arxiv.org/html/2507.07644v2)
- "VLMs can parse floor plan maps" (Binghamton) used GPT-4o and Claude 3.5 Sonnet to produce JSON door-level navigation plans. On processed maps, hard-task success was GPT-4o 0.24/0.84/0.22 and Claude 0.68/0.66/0.34 across three domains. Raw maps scored far worse — [arXiv 2409.12842](https://arxiv.org/html/2409.12842v2)
- The preprocessing tricks that helped: remove dimensions, furniture and window symbols; make wall thickness uniform; colour doors yellow with unique door IDs; and use "dense labeling", meaning repeated room labels in large open areas and near doors (GPT-4o t=10.72, p<0.0001). Asking the model to first list all door-room connections also helped. Accuracy drops on larger maps — [arXiv 2409.12842](https://arxiv.org/html/2409.12842v2)
- Three open-source VLMs estimating room areas on colour-coded plans got MAPE ≈ 43%, versus 5.68% for pixel counting — [Periodica Polytechnica](https://pp.bme.hu/ci/article/view/44138)
- An informal April 2026 test of ChatGPT Thinking, Claude Sonnet 4.6 and Gemini Thinking on a two-storey house found ChatGPT most consistent on door counts. Claude matched doors and windows exactly on a masked/simplified version. Gemini was least stable and hallucinated rooms. Simplified colour representations helped Claude notably — [ArchitectsWhoCode](https://architectswhocode.com/can-ai-really-read-a-floor-plan/)
- An informal Gemini 2.0 test extracted room names and areas accurately but missed bathrooms, and forcing JSON output seemed to hurt reasoning — [Gwyllim Substack](https://gwyllim.substack.com/p/reasoning-about-plans-with-language)
- FloorplanVLM shows a 3B VLM can produce valid wall/room JSON 96% of the time, but only after SFT on millions of plans plus GRPO — [arXiv 2602.06507](https://arxiv.org/html/2602.06507)

### Inferences
- The best VLM role in our pipeline: (1) label CV-extracted regions via set-of-mark with numbered marks (already done); (2) verify adjacency and doors ("list every door and which two marked rooms it connects"); (3) act as a fallback classifier for ambiguous regions. Don't let the VLM emit coordinates except as coarse hints. If it must, use a labelled grid overlay and ask for cell IDs rather than pixels. This trick is inferred and has no benchmark evidence.
- Applying the Binghamton preprocessing (strip furniture and dimensions, recolour doors, dense labels) before the VLM call should help on OSM and MSD plans.

### Gaps
- No peer-reviewed 2026 benchmark was found comparing GPT-5.x, Claude 4.x, Gemini 2.5/3 and Qwen3-VL on room-polygon IoU from plan images. No evidence was found for grid-overlay or tiling gains on floor plans specifically.

## Scale estimation without a scale bar

### Takeaway
There is no strong dedicated paper. Practical approaches are (1) OCR of dimension or area text matched to pixel lengths and areas, (2) PDF page size plus DPI metadata, (3) known-size priors such as doors (about 0.8-0.9 m interior leaf, which is our assumption) and typical rooms, and (4) asking the user for one dimension. For a hackathon, use "user enters one wall length or total area" with automatic door-width and OCR estimates as defaults.

### Cited Findings
- A patch-based extraction method normalizes plans to a common metres-per-pixel scale using a scale-detection step that reads a dimension line or derives scale from pixel size — [MDPI ISPRS IJGI 2021](https://www.mdpi.com/2220-9964/10/12/828)
- Lv et al. (CVPR 2021) compute room scales by detecting key points (dimension-line endpoints) and running cluster analysis. They note that combining OCR'd room-area text with segmentation introduces errors from mis-segmented pixels — [CVPR 2021](https://openaccess.thecvf.com/content/CVPR2021/papers/Lv_Residential_Floor_Plan_Recognition_and_Reconstruction_CVPR_2021_paper.pdf) (search snippet only, full paper not read)
- A 2026 compliance-check framework derives scale from the PDF page's physical size plus rasterization DPI, and OCRs printed scale labels such as "1:100" — [arXiv 2607.00015](https://arxiv.org/pdf/2607.00015) (snippet only)
- Practitioner advice: derive one wall length from total floor area, then cross-check with standard objects such as door width, kitchen counter and tub width. US door labels are often like 3′0″. This is approximate, not construction-grade — [Sweet Home 3D forum](https://www.sweethome3d.com/support/forum/printthread_thread,7906); [CodeSignal lesson](https://codesignal.com/learn/courses/measuring-space-at-home/lessons/reading-scaling-floor-plans)

### Inferences
- Robust recipe: take the median detected door-opening width in pixels and assume about 0.85 m to get a scale. Cross-check with OCR'd room-area text (m² labels are common on European and MSD-style plans) and use the median ratio. Show the estimate and let the user override it with one known dimension. Door-width priors vary by region and door type, so expect ±15-20% error (my estimate, not sourced).

### Gaps
- No paper benchmarked door-width-based or standard-room-size-based scale inference error.

## Datasets for training and testing

### Takeaway
For quick testing on "real" plans, CubiCasa5K (scanned-style Finnish plans), ResPlan / ResPlan-FP (CC BY 4.0, the most permissive) and MSD (Swiss, our weak domain) are the most relevant. Most others are non-commercial or academic-only, which is fine for a hackathon demo but matters for any product.

### Cited Findings
- **CubiCasa5K**: about 5,000 plans, more than 80 categories, SVG polygons — [GitHub](https://github.com/CubiCasa/CubiCasa5k). Kaggle lists the licence as CC BY-NC-SA 3.0 IGO — [Kaggle](https://www.kaggle.com/datasets/qmarva/cubicasa5k). The repo LICENSE text was not read. In Raster2Seq's split, the original split is 4,199/399/399 and splitting multi-floor images gives 6,281 samples — [Raster2Seq](https://arxiv.org/html/2602.09016v1)
- **ResPlan**: 17,000 residential vector-graph plans. The arXiv paper and Kaggle stats table say data CC BY 4.0 and code MIT, but another Kaggle section says CC BY-NC-SA 4.0 (conflict) — [arXiv 2508.14006](https://arxiv.org/pdf/2508.14006); [Kaggle](https://www.kaggle.com/datasets/resplan/resplan). **ResPlan-FP** (16,998 plans, CC BY 4.0, frozen splits) — [arXiv 2608.25608](https://arxiv.org/abs/2608.25608)
- **MSD (Modified Swiss Dwellings, ECCV 2024)**: more than 5.3K floor plans covering more than 18.9K apartments, derived from Swiss Dwellings. Non-residential plans and furniture-like geometry (bathtubs, stairs) were removed. "Code and data are open", but the licence was not found — [arXiv 2407.10121](https://arxiv.org/pdf/2407.10121)
- **Structured3D**: 3,000/250/250 scenes with 16 room types, as used by Raster2Seq — [Raster2Seq](https://arxiv.org/html/2602.09016v1). A secondary source says it is non-commercial (unverified) — [search result via ResearchGate](https://www.researchgate.net/publication/346667546_Structured3D_A_Large_Photo-Realistic_Dataset_for_Structured_3D_Modeling)
- **Raster2Graph dataset**: 9,803/500/499 train/val/test, 12 classes — [Raster2Seq](https://arxiv.org/html/2602.09016v1)
- **WAFFLE**: about 20K internet floor plans, about 100 annotated (zero-shot eval) — [Raster2Seq](https://arxiv.org/html/2602.09016v1)
- **Zillow Indoor Dataset (ZInD)**: under the ZInD Terms of Use, academic use only. Commercial use requires a 500-word-minimum proposal to Zillow. Code is Apache — [GitHub zillow/zind](https://github.com/zillow/zind)
- **RPLAN**: more than 80K real Chinese residential buildings; licence not confirmed by search — [Layout review arXiv 2504.09694](https://arxiv.org/pdf/2504.09694)
- **MLSTRUCT-FP**: floor-plan images with wall annotations in JSON — [GitHub](https://github.com/MLSTRUCT/MLSTRUCT-FP)
- **FPBench-2K**: 2,000-sample benchmark, to be open-sourced by the FloorplanVLM authors — [arXiv 2602.06507](https://arxiv.org/html/2602.06507)

### Inferences
- For a hackathon test set, take about 20 plans each from CubiCasa5K (scan-like), MSD (our weak domain) and our clean generator. Score room count, room F1 at IoU 0.5 and door-graph correctness. This would tell in hours whether adding Raster2Seq is worth it.

### Gaps
- Licences for MSD, RPLAN and Structured3D, and R2V (Liu et al. ICCV 2017, about 870 annotated plans from my memory, unverified), were not confirmed from primary pages.

## Multi-floor alignment (stairs and lift cores)

### Takeaway
There is no standard published algorithm for registering scanned multi-floor plans. The practical approach is anchor-based alignment: detect stair and lift polygons on each floor and solve a similarity transform (translation, plus scale if needed) that best overlaps them. Optionally refine with an outline/footprint overlap optimization. A manual "drag to align" fallback is sensible for a demo.

### Cited Findings
- A patent describes identifying elevators, stairs, pillars and fire-escape ladders as vertical anchor points to stack floor plans — [USPTO 11593535](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11593535)
- A robot-navigation pipeline from CAD files finds regions tagged elevator or stairs to connect floors. It assumes CAD files share an origin but adds automatic registration for layer misalignment — [arXiv 2507.00552](https://arxiv.org/pdf/2507.00552)
- SYNBUILD-3D aligns each floor plan bitmap to the building footprint bitmap by optimizing translation and x/y scale to minimize gaps and overhang — [arXiv 2508.21169](https://arxiv.org/pdf/2508.21169)
- A multi-unit plan reconstruction paper models stairs as equal-height polygons without orientation, which limits 3D quality — [arXiv 2408.01526](https://arxiv.org/pdf/2408.01526)
- MANSION (multi-floor generation) places stair and elevator cores at corners bounded by two exterior walls with integer-quantized core boxes. This is generation rather than registration, but it is a useful structural prior — [arXiv 2603.11554](https://arxiv.org/pdf/2603.11554)

### Inferences
- Implementation for the demo: (1) per floor, get the outer-wall outline (largest contour) and the stair/lift polygons, via VLM labels such as "stair" or "lift"; (2) match cores across floors by type and size; (3) estimate the transform with RANSAC/least squares on core centroids, or IoU-maximize outlines when only one core exists; (4) create vertical graph edges between matched cores with traversal costs. This fits a wayfinding graph directly.

### Gaps
- No benchmark or open-source tool for multi-floor plan registration from images was found.
