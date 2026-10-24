# Keep the graph deterministic, make the talk grounded

The highest-scoring design for "talk to your building" locks every fact into code and uses the LLM for two jobs only: understanding the request and putting a precomputed plan into words. That split protects the 55% automated-correctness score and also earns most of the 25% interaction score. The evidence says LLMs are unreliable path planners ([Chen et al.](https://arxiv.org/html/2411.17912v2)). They also tend to under-clarify and to make up missing arguments ([AgentAbstain summary](https://arxiv.org/pdf/2607.10059)). A strong template generator matched neural route-instruction generators when tested with human followers ([Zhao et al. 2021](https://aclanthology.org/2021.eacl-main.111/)). So, ranked by rubric impact per hour of work:

1. A fuzzy entity resolver over names, aliases and categories, with a strict "never invent a room" rule.
2. A rule-based gate for when to ask a question, with options taken from the graph.
3. An answer-first route card that repeats back the resolved destination and any active constraints.
4. Landmark-anchored, chunked steps, with each floor change as its own step and at most about 4 spoken segments at a time.
5. Step-free routing that persists for the session.
6. A small eval harness: code graders for correctness, per-dimension binary judges for the rubric.

The parts that look impressive are worth doing only after those six work: a floor-plan builder, AR, and a benchmark dashboard. A QR-anchored, Android-only "glance AR" moment and the existing OpenCV plan pipeline are the right size for 1–2 days. Learned plan-reconstruction models and cloud positioning (VPS) are not. Much of the underlying evidence comes from small studies or vendor guidance, and the specific thresholds below are engineering defaults to tune, not validated constants.

## Correctness comes from code; the LLM only parses and verbalises

The automated 55% will almost certainly check the resolved destination, the route and whether constraints were honoured. All three should come out of deterministic code. Frontier models do read plan semantics, but they lack "robust internal geometric representations." On FloorplanQA, Claude Sonnet 4 scored 99.8% on pair distance but 0.2% on a free-space task ([FloorplanQA](https://arxiv.org/html/2507.07644v2)). The architecture that follows:

- **Parser.** The LLM turns the utterance into a structured intent: `{destination_ref, origin_ref, constraints, intent_type}`.
- **Resolver.** A deterministic resolver maps each reference to node IDs.
- **Solver.** A deterministic solver returns the path.
- **Instruction planner.** A deterministic planner builds an instruction plan in JSON.
- **Rendering.** The LLM turns that plan into text, adding no new facts. A template fallback covers any output that fails verification ([route-instruction synthesis, R14–R15](https://aclanthology.org/2021.eacl-main.111/)).

**The resolver carries the most weight for both correctness and interaction.** It matches against room names, numbers, aliases ("the big press", team names, people) and categories ("toilet / WC / restroom"), and its output decides the next move:

- **One strong match.** Act on it. If the spelling was corrected, say so in passing.
- **2–4 plausible matches.** Offer them as options.
- **No match.** Say so plainly and suggest the nearest real alternatives, instead of a bare "not found" ([Google: Errors](https://developers.google.com/assistant/conversation-design/errors)).
- **"Nearest X".** Pick by category plus graph distance from the current location.

Two hard rules apply. **Never fabricate a room, edge or parameter**: if a required value is missing, ask for it or state an explicit default. **Never fall back silently to stairs** when step-free routing fails. Products default to shortest-path routing and make accessible routing an explicit flag ([Mappedin docs](https://developer.mappedin.com/web/v6/guides/wayfinding/)), so a stated constraint that later turns get wrong is a correctness bug, not a UX issue.

A mid-dialogue change ("actually, the cafeteria", "avoid stairs") updates one parameter of the current task. It does not restart the dialogue. Google's guidance is to let users change any parameter and ask only for the new value ([Google: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations?hl=en)). The agent recomputes and reports only the difference ("Updated: now step-free, +40 m").

## Ask rarely, ask concretely, and always show what was understood

The rubric clause "asks only what it needs" penalises both failure modes, and the research covers both. A prompt-only selective-clarification pattern (detect ambiguity, then ask, then answer) "significantly increases" accuracy on ambiguous questions "without affecting unambiguous questions" ([CLAM](https://arxiv.org/abs/2212.07769v2)). But LLMs are poor at judging ambiguity on their own, even with chain-of-thought ([CLAMBER](https://arxiv.org/html/2405.12063v2)). Low-quality clarifying questions also hurt satisfaction, and they suppress later interaction ([Zou et al. TOIS](https://research.tudelft.nl/en/publications/users-meet-clarifying-questions-toward-a-better-understanding-of-); [Zou et al. IPM](https://dare.uva.nl/id/2cbf36e0-24e3-4be3-bc5c-01e332c33c9c)).

So the decision to ask should come from the graph, not from the model's free judgment. **Ask only when the request maps to more than one node AND the candidates lead to materially different routes, or when the action is a destructive edit.** First try to remove the ambiguity with context: the user's floor or wing, the nearest candidate, or the last place mentioned. When a question is needed, make it one closed question per turn. Offer 2–4 options taken from the graph, most likely first, plus a "something else" choice. Alexa guidance puts the limit at about five short spoken items ([Alexa Lists](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists)). Allow at most one clarification round for a route query. After that, act on the best guess and label it as a guess.

"Shows what it understood" is cheapest to earn through **implicit confirmation**: work the resolved entities into the answer itself. Google reserves explicit yes/no confirmation for actions that are costly or hard to undo, and warns that users may not trust details that were never acknowledged ([Google: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations?hl=en)). Every route answer should therefore open with a header line like "Step-free route · Main Entrance → Lab 3.02 (Floor 3) · via Lift B · ~2 min". Every node the agent mentions should be highlighted on the map, and a node the user taps should feed back into the agent's context, so that "take me there" needs no question.

Building edits get a stricter protocol, adapted from Microsoft's HAX guidelines on conveying consequences and supporting undo ([HAX G16](https://www.microsoft.com/en-us/haxtoolkit/library/example,pattern/11,16,18/28/); [HAX G9](https://www.microsoft.com/en-us/haxtoolkit/library/example,pattern/11,18/28/)):

1. **Preview.** Show the proposed change as a diff, both as a text summary and as a map overlay: green for added, red for removed, amber for changed.
2. **Warn.** Point out graph consequences ahead of time, for example "this removes the only step-free path to Floor 2".
3. **Confirm explicitly only for destructive changes**: deletes, merges, bulk edits, or anything that breaks connectivity.
4. **Commit.** Return a one-line receipt with an Undo option.

When the user names a room that does not exist and asks to edit it, offer "Create it?" rather than creating it silently.

**Accessibility needs should go into a visible, removable constraint slot.** Echo the constraint once ("Got it, I'll keep routes step-free"), apply it on every later route without asking again, and show it as a chip that can be dismissed. Record only what the user says outright, keep it for the session by default, and leave it out of logs. A memory audit found over 95% of ChatGPT memories were extracted implicitly, without the user's agency ([arXiv 2609.14697](https://arxiv.org/pdf/2609.14697)), and health-related categories carry particular risk ([arXiv 2609.10413](https://arxiv.org/pdf/2609.10413)). If no route satisfies a constraint, say so explicitly and offer the least-bad option with the violation marked. That case does warrant a question.

Error recovery should escalate along Google's pattern ([Google: Errors](https://developers.google.com/assistant/conversation-design/errors)):

- **First miss.** A short re-ask.
- **Second miss.** Options, plus "tap it on the map".
- **Never** more than three errors in a row.

## Directions people can follow: landmarks, chunks and explicit floor changes

This is the rubric clause where the research is most specific. People mainly remember turns and decision points and walk straight by default ([Meilinger et al. 2014](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2014.01363/full)). That argues for giving instructions only at decision points and mode changes, and folding straight passes into the next turn. Landmark-anchored phrasing ("turn right after the second door") lets people pick out the decision point where metric phrasing does not ([WU Vienna / Fellner et al.](https://research.wu.ac.at/de/publications/turn-left-after-the-wc-and-use-the-lift-to-go-to-the2nd-floor-gen-3/)). Showing **one** prominent landmark per instruction was more efficient than showing four ([Bauer et al. via Pharos](https://arxiv.org/pdf/1904.01694)).

Room numbers should confirm a step, not steer it. People do read them ([Münzer & Stahl](https://www.dfki.de/fileadmin/user_upload/import/5372_Muenzer_Stahl_SC08PosterSubmissionSpringerFormat.pdf)), but they are hard to see from a distance, so the cue to turn should be a large object or structural feature, with the room number kept for the arrival line.

Landmark choice can be computed. The salience literature splits a landmark's prominence into visual, semantic and structural parts ([Raubal & Winter 2002](https://cris.uni-muenster.de/portal/en/publication/16971808)), with visibility on approach added later ([Winter 2003 via arXiv 1907.05289](https://arxiv.org/pdf/1907.05289)). A workable score per candidate object at each decision point adds up four terms:

- **Size:** normalised footprint.
- **Uniqueness:** one minus the share of visible objects in the same category, so a unique red press beats one cabinet among ten.
- **Structural position:** highest for an object at the turn and on the turn side, lowest for one mid-segment.
- **Visibility on approach.**

The weights are not standardised in the sources and need tuning. Chunking then merges straight runs into one instruction that ends at a landmark or structure ("to the end of the corridor", "until the lifts"). Counting ("second door") is used only for small counts ([Klippel chunking via Nourin et al.](https://arxiv.org/html/2408.15367v1); [Richter & Klippel](https://pure.psu.edu/en/publications/a-model-for-context-specific-route-directions/)).

**Floor changes are the main point of failure indoors.** Staircase design was a major obstacle in a real multi-level building, and experienced users went to the target floor first ([Hölscher et al. 2006](https://cityterritoryarchitecture.springeropen.com/articles/10.1186/s40410-016-0038-9)). Make each floor change its own step that states the mode, the direction, the target floor, and what to do on exiting: "Take Lift B up to Floor 2. When you come out, turn right toward the canteen." Where routes are equally good, prefer ones that change floor early.

Spoken length has one direct study. With 27 first-time visitors, 4-segment descriptions reached **85% success versus 65–67% for 6–8 segments**, and total time differed significantly (p=.002) ([Nourin et al. 2024](https://arxiv.org/html/2408.15367v1)). The sample was small and the success difference was not significant, but the direction matches working-memory limits. Short keyword-style voice responses were rated as useful as full sentences and were more efficient ([Haas et al. CHI 2022](https://www.uni-ulm.de/fileadmin/website_uni_ulm/iui.inst.100/1-hci/hci-paper/2022/CHI2022_Keep_it_short.pdf)). Real-time step-by-step delivery beat giving the whole route up front for non-visual navigation ([UMaine VEMI](https://umaine.edu/vemi/?p=1114)).

That leads to the following output formats:

| Mode | Format |
|---|---|
| Written | Summary header, then a numbered list of chunked steps (about 7 or fewer visible), ending with an arrival cue that includes the room number |
| Spoken overview | At most 4 segments, each one action plus a landmark in about 15 words or fewer, joined with "then", plus a preview like "3 steps, about 2 minutes, one lift" |
| Spoken step mode | One step at a time, with "next / repeat / back / where am I / stop" |
| Blind / low-vision | Step counts instead of metres ([Kalia et al. 2010](https://legge.dl8.umn.edu/sites/legge.psych.umn.edu/files/2020-08/Kalia%20Legge%20Roy%20Ogale%202010%20Assessment%20of%20indoor%20route%20finding%20technology%20for%20visually-impaired%20people.pdf)), landmarks that can be perceived without sight, and stairs announced in advance ([NavCog](https://ri.cmu.edu/publications/navcog-a-navigational-cognitive-assistant-for-the-blind)) |

**Verification:** run every LLM-rendered instruction set through a second step that parses the text back into an action sequence. Execute that sequence on the graph. It must reach the goal through the same decision points, and every entity it names must exist. If it fails, fall back to the template text. This "execute the text" check follows the evidence that BLEU/ROUGE-style overlap metrics fail for navigation instructions while execution-based checks track human success ([Zhao et al.](https://aclanthology.org/2021.eacl-main.111/); [Beyond Prompts](https://arxiv.org/pdf/2409.20222)). It also gives the eval harness a followability metric that runs without gold answers.

## A list-plus-map UI in 2D, styled like the building's own signs

No controlled study shows a map beating a list for indoor routes. Voice-only guidance matched a map "given that voice instructions are carefully composed," and both beat AR in a 48-person field study ([Rehrl et al.](https://salzburgresearch.at/?p=14599)). Leading products combine a highlighted map, a step list, a category Directory and an accessibility toggle ([Google Indoor Live View](https://blog.google/intl/en-au/products/explore-get-answers/indoor-live-view-sydney-airport/)). The recommended layout:

- A step list as the primary content. It also serves speech and screen readers.
- The map above it, or a bottom sheet holding the steps on a phone.
- Tapping a step pans the map to that step.

**Use 2D per floor, not 3D.** 2D and 3D maps both improved multi-level navigation over no map, with no significant difference between them ([Li & Giudice 2013](https://umaine.edu/vemi/?p=1238)). Cross-sectional views that highlight connections between levels help ([Hölscher review](https://cityterritoryarchitecture.springeropen.com/articles/10.1186/s40410-016-0038-9)). So a small stacked-floor diagram during multi-floor routes is the high-value 3D-ish feature. A full 3D viewer adds creativity points but no correctness or rubric points.

Visual design should borrow from healthcare signage guidance ([SaTH NHS](https://www.sath.nhs.uk/wp-content/uploads/2025/06/Signage-Wayfinding-HTP-Focus-Group-5-June-2025.pdf); [Sheffield manual](https://sheffield.ac.uk/media/97691/download)):

- Text and numbers lead; colour is secondary.
- At most about 5 zone colours, always paired with a zone name.
- High tonal contrast, because tone matters more than hue for ageing eyes.
- Sans-serif type in two weights, with the destination in bold.

On screen, the signage hierarchy maps to:

- an **arrival card** for identification (name, number, landmark);
- **arrow steps** for direction;
- a **you-are-here map and directory** for orientation;
- **notices** for regulatory or hazard information.

For accessibility, the route line and position marker need **3:1 non-text contrast** ([WCAG 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast)). The route should be distinguished by width and casing as well as hue. Map dragging needs pan buttons as a single-pointer alternative ([WCAG 2.5.7](https://www.digitalpolicy.gov.hk/en/our_work/digital_government/digital_inclusion/accessibility/promulgating_resources/handbook/wcag2aa/9_16_dragging_movements.html)). Edges should carry `step_free`, `min_clear_width_cm` and lift `status`, because a lift that is out of order can make a route impassable ([RWTH](https://publications.embedded.rwth-aachen.de/file/5h)). Width thresholds of roughly 80–90 cm come from several secondary sources ([Frankfurt inklusiv](https://www.frankfurt-inklusiv.de/en/filter?L=1)).

**Onboarding for people who know no room names** should open with category chips rather than a room-number field: Reception, Toilets, Coffee, Meeting rooms, Exit, First aid, Find a person. Add a mic button, a step-free toggle, and an "I'm at: Main entrance" pill set by a QR scan. This mirrors Google's Directory button and Pointr's misspelling-tolerant autocomplete ([Pointr](https://pointr.tech/solutions/indoor-navigation)). Show 3–4 starter prompts that reveal what the agent can do, and 2–3 follow-up chips after each answer ([NN/g via Willison](https://www.simonwillison.net/2023/Nov/23/6-types-of-conversations-with-generative-ai)). When the start point is unknown, ask one landmark question: "What can you see? Reception / yellow press / Lift B".

Make it a no-install web app. Only about a third of hospital visitors said they would use a smartphone app, and the same study recommends a browser app with QR positioning and kiosks ([Ženka et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC7908200)).

**"Voice counts"** means push-to-talk (the Web Speech API is enough), barge-in ("stop", "repeat") that cuts speech off immediately ([Meta voice design](https://developers.meta.com/horizon/design/voice/)), a text echo of every spoken step for noisy floors, and the step mode described above. Implicit confirmation in voice is a short echo of the destination ("Compressor room, Hall C. Starting.").

## Plan reconstruction and AR: keep the cheap path, cut the expensive ones

**Floor plans.** The existing colour-segmentation pipeline is the right primary path. On colour-coded plans, pixel counting reached 5.68% error on room area against about 43% for open VLMs ([Aliyev & Barsi](https://pp.bme.hu/ci/article/view/44138)). The VLM should do what it is good at: label regions marked with set-of-mark numbers, and check door-to-room connectivity ("list every door and the two marked rooms it connects"). Preprocessing helps. Stripping furniture and dimensions, recolouring doors with IDs and repeating room labels improved VLM floor-plan navigation significantly ([Binghamton, arXiv 2409.12842](https://arxiv.org/html/2409.12842v2)). Apply these steps to the weaker OSM and Swiss Dwellings inputs.

Raster2Seq is the strongest open-weight fallback for real scans. It scores Room F1 88.7 on CubiCasa5K, uses an MIT licence and ships Hugging Face checkpoints, but its corner F1 is only 59.4 and it takes 256×256 inputs ([arXiv 2602.09016](https://arxiv.org/html/2602.09016v1); [HF](https://huggingface.co/haopt/Raster2Seq)). It is worth one timeboxed attempt on a Linux GPU, not on Windows. Skip RoomFormer, HEAT and PolyRoom, which target density maps and need compiled CUDA ops ([RoomFormer](https://github.com/ywyue/RoomFormer)).

**Scale** has no benchmarked method. The practical recipe has three parts:

1. Take the median door-opening width in pixels and assume about 0.85 m.
2. Cross-check against OCR'd area or dimension text, or against PDF page size plus DPI ([arXiv 2607.00015](https://arxiv.org/pdf/2607.00015)).
3. Always show the estimate and let the user override it with one known wall length or total area ([practitioner guidance](https://www.sweethome3d.com/support/forum/printthread_thread,7906)).

For **multi-floor stacking**, match stair and lift polygons across floors and solve for a translation (and scale if needed) on their centroids, with a manual drag-to-align fallback. Elevators and stairs as vertical anchors is the pattern in both a patent and a CAD-to-robot pipeline ([USPTO 11593535](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11593535); [arXiv 2507.00552](https://arxiv.org/pdf/2507.00552)). The matched cores become vertical graph edges directly.

**AR and localization.** WebXR `immersive-ar` works reliably only in Chrome on ARCore Android. iPhone Safari lacks it ([MultiSet docs](https://docs.multiset.ai/webxr-sdk)), and WebXR is not an Interop 2026 focus area ([WebKit](https://webkit.org/blog/17818/announcing-interop-2026/)). 8th Wall's hosted platform is gone and its open-source release excludes SLAM and VPS ([Road to VR](https://www.roadtovr.com/niantic-webar-platform-8th-wall-open-source/)). BLE and WiFi positioning give 2–5 m at best, and browser access to them is experimental or absent ([ISPRS 2020](https://isprs-archives.copernicus.org/articles/XLIII-B1-2020/193/2020/isprs-archives-XLIII-B1-2020-193-2020.pdf); [Web Bluetooth](https://pub.dev/documentation/flutter_web_bluetooth/0.2.4/js_web_bluetooth/Bluetooth/requestLEScan.html)).

**QR codes at known nodes are the only localization that fits the timeline.** Scanning one sets the start node in the agent, which removes the "where are you?" question entirely. On Android the same scan seeds the AR origin, and three.js chevrons are drawn along the solved polyline. Published AR indoor prototypes use exactly this "QR initialisation plus anchors" pattern ([IJACSA 2025](https://thesai.org/Downloads/Volume16No4/Paper_6-Evaluating_User_Acceptance_and_Usability_of_AR.pdf)).

Use AR for short glances at decision points, not for walking with the phone held up. AR reduced errors and anxiety in a hospital, but users kept less spatial memory than with a paper map ([Liu et al.](https://arxiv.org/abs/2601.00001v1)), and Google's Live View warns users against walking with the phone raised ([Business Insider](https://www.businessinsider.nl/google-maps-live-view-ar-ios-android-2019-8)). Treat AR as a 10% demo and creativity item with an iOS fallback (2D map plus compass arrow), never as part of the core flow.

## Build the eval harness to mirror the grader, then add the dashboard

The harness should copy the split in the grading:

- **Code graders** for whatever is automated.
- **Binary LLM judges**, one per rubric clause.
- **Humans** only for calibration.

That matches Anthropic's guidance to prefer deterministic graders and to calibrate model graders against humans ([Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). It runs in four layers:

1. **Solver property tests.** The route is connected, has the right endpoints, respects step-free constraints, and is deterministic. Gate at 100%.
2. **Parser field-level exact match** on train/dev buildings.
3. **End-to-end dialogues with simulated users.** Each simulated user has a hidden goal, and the final route is graded on state, as in tau-bench ([tau-bench](https://export.arxiv.org/abs/2406.12045)). Report pass^k to expose nondeterminism: at 75% per-trial success, pass^3 is only about 42% ([Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
4. **Rubric judges** for "asked only when needed", "echoed the resolved entities", and "steps were followable".

Simulated users are too cooperative and too uniform, which inflates agent success ([arXiv 2603.11245](https://arxiv.org/html/2603.11245v1)). Script personas deliberately:

- an ambiguous destination;
- a typo or a room that does not exist;
- a change of mind mid-dialogue;
- a wheelchair user;
- a terse user;
- an off-topic request.

The hidden "Sunday" building has no gold answers, so **split by building**: run leave-one-building-out over train and dev, and keep test-building strings out of prompts and alias tables. Add metamorphic checks that need no gold answers:

- A paraphrased request must produce the same parse.
- Adding "avoid stairs" must never produce a route with stairs.
- Swapping origin and destination must reverse the route at equal cost.

These come from the general metamorphic-testing literature ([arXiv 2603.13173](https://arxiv.org/abs/2603.13173)). They are proposals, not a published wayfinding protocol.

LLM judges need care. GPT-4 agreed with humans 85% of the time on non-tie pairs, but position bias was severe in weaker judges ([Zheng et al.](https://arxiv.org/html/2306.05685v4)). Reference-guided judging cut failures from 70% to 15% on maths questions. Practice for the judges:

- Use binary pass/fail per dimension with a written critique, not 1–5 scales.
- Use the critiques as few-shot examples.
- Report true-positive and true-negative rates separately against your own labels ([Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)).
- Swap positions for any A/B comparison.

Realistically, the team can label 30–60 transcripts in a few hours. That is enough to catch a broken judge but gives wide confidence intervals (below 60 examples, "the confidence intervals are often too wide"). Show error bars, clustered by building ([Miller 2024](https://www.anthropic.com/research/statistical-approach-to-model-evals)).

The **benchmark admin dashboard** should implement the views the mature tools share ([Inspect](https://inspect.aisi.org.uk/log-viewer.html); [Braintrust](https://www.braintrust.dev/docs/evaluate/compare-experiments); [LangSmith](https://docs.langchain.com/langsmith/annotation-queues)), in this priority order:

| Priority | View | Why it matters in 1–2 days |
|---|---|---|
| P0 | Runs table: git SHA, prompt/model version, split, accuracy ± CI, pass^k, latency, cost | Shows progress in the demo; catches regressions |
| P0 | Per-sample drill-down: transcript, parse vs gold, solver I/O, **route drawn on the floor plan**, judge verdicts with rationale | Where every fix gets found; the route overlay is a strong demo visual |
| P0 | Filter/slice by building, query type, persona, constraint, failure category | Error analysis by category is the most effective improvement loop |
| P1 | Baseline-vs-candidate comparison with per-item green/red deltas, sorted by regression | Proves a prompt change helped without hurting other items |
| P1 | Epoch view grouping the k trials per item and flagging mixed outcomes | Finds the nondeterministic items |
| P2 | Binary annotation queue per rubric dimension, plus a judge calibration page (TPR/TNR, disagreements) | Turns human labels into trustworthy judges |
| P3 | Dataset versioning, a test-split access log, suite-health saturation warnings, CI PR comment | Good hygiene; impresses judges but is not needed to score |

## Ranked implementation checklist

The ranking weighs expected points (55/25/10/10) against hours. Items 1–9 are the core for day 1. Items 10–16 are day 2. Items 17 onward are stretch work.

1. **Fuzzy resolver** over names, numbers, aliases and categories, plus "nearest X" by graph distance. Three outcomes: one match → act; 2–4 → options; none → nearest real alternatives. Never fabricate. *(correctness + rubric)*
2. **Strict LLM → JSON intent parser** with the deterministic solver behind it. The LLM never plans paths. *(correctness)*
3. **Persistent constraint slot** (step-free / avoid stairs) applied on every turn, shown as a chip, and stated in each route header. Explicit "no step-free route exists" handling. *(correctness + rubric)*
4. **Ask-gate rule** in code and prompt: ask only when the request is ambiguous and the candidates give materially different routes, or when an edit is destructive. One closed question with 2–4 graph options. At most one round. *(rubric: asks only what it needs)*
5. **Answer-first route header** echoing resolved origin, destination, floor and constraints, plus map highlighting of every mentioned node. *(rubric: shows what it understood)*
6. **Deterministic instruction planner**: decision points only, straight runs chunked, one salient landmark per turn, floor change as its own step with exit orientation, room number at arrival. *(rubric: followable directions)*
7. **Template renderer** as the baseline, with optional LLM polish constrained to plan entities. *(followable, safe)*
8. **Solver property tests and parser exact-match tests** on train/dev, building-split. *(protects the 55%)*
9. **Parameter-update handling** for mid-task changes ("avoid stairs", "actually X"), reporting only the difference. *(rubric + correctness)*
10. **Voice**: push-to-talk, speaking of at most 4 segments, step mode with next/repeat/stop, barge-in, and a text echo. *(rubric: voice counts)*
11. **Onboarding screen** with category chips, starter prompts, a QR "I'm at" pill, and a one-question landmark fallback for an unknown start. *(rubric + demo)*
12. **Back-parse verification** of rendered instructions on the graph, falling back to the template on failure. *(correctness of text + eval metric)*
13. **Simulated-user E2E suite** with adversarial personas, state-based success and pass^k, plus 3 binary rubric judges calibrated on 30–60 hand labels. *(lets you tune the 25%)*
14. **Dashboard P0 views**: runs table, drill-down with route overlay, slicing. *(demo + dev speed)*
15. **2D floor map** with a signage-style design: 3:1 route contrast, pan buttons, zone colour plus name, and a stacked-floor mini-diagram on multi-floor routes. *(demo + accessibility)*
16. **Building-edit protocol**: diff preview, consequence warning, confirmation only when destructive, receipt plus undo. *(rubric if edits are graded)*
17. **Floor-plan builder hardening**: Binghamton-style preprocessing, VLM connectivity check, door-width scale estimate with user override, core-based floor stacking. *(creativity + demo)*
18. **Dashboard P1–P2**: comparison deltas, epoch view, annotation and judge calibration. *(polish)*
19. **QR-seeded WebXR glance-AR** on Android Chrome with chevrons and a 2D/compass fallback on iOS. *(creativity + demo)*
20. **Stretch**: timeboxed Raster2Seq fallback for scanned plans, blind/low-vision mode (step counts, non-visual landmarks), live lift-outage toggle.

## Conclusion

The rubric's three interaction clauses are not separate features. Each is a visible side effect of the same deterministic core. "Asks only what it needs" falls out of a resolver that knows when candidates truly diverge. "Shows what it understood" falls out of echoing resolved node IDs and constraints. "Directions a person can follow" falls out of a planner that picks decision points and landmarks before any language model touches the text. So the team should spend almost no effort on prompt-crafting the agent's personality and nearly all of it on the resolver, the instruction planner and the tests that pin them down. That same investment also secures the 55%.

The main uncertainty is how the hidden-building grader phrases its queries and what it counts as correct. Leave-one-building-out testing, adversarial personas and metamorphic paraphrase checks are the only defences available without gold answers. AR, 3D and learned plan reconstruction belong in the last hours as demo flourishes: the evidence says they win attention, not wayfinding performance.
