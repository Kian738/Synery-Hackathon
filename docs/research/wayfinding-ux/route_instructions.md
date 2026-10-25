# Route Instruction Generation and Cognitive Wayfinding for Indoor Buildings

Scope note: These notes use about 18 search and fetch calls. Several primary PDFs (Raubal & Winter 2002, Klippel & Winter 2005, NavCog3, Fellner 2017 IJGI) could not be read in full. Fetches either returned binary PDF data or were blocked with HTTP 403. Claims about those papers therefore come from abstracts, bibliographic pages, or secondary summaries, and each one is flagged where that applies. One full text was read: Nourin et al. 2024 (arXiv HTML). It is the strongest source here on spoken length.

## 1. Landmark salience models and how to compute salience from available data

### Takeaway
The standard model, Raubal & Winter (2002), splits landmark salience into visual, semantic and structural parts and adds them up with weights. Later work adds visibility on approach (Winter 2003; Nothegger et al. 2004) and the observer's context and task (Caduff & Timpf 2008). For indoor graphs with typed objects, you can approximate this from size, how rare the object category is near the decision point, line of sight, and position relative to the turn.

### Cited Findings
- Raubal & Winter, "Enriching Wayfinding Instructions with Local Landmarks" (GIScience 2002, LNCS 2478, pp. 243–259) proposes formal measures of a feature's landmark salience. The values of these measures go through hypothesis tests to extract landmarks from datasets, and the extracted landmarks are added to geometry-based instructions. The worked example is Vienna. — [Univ. Münster CRIS](https://cris.uni-muenster.de/portal/en/publication/16971808); [DOI](https://www.doi.org/10.1007/3-540-45799-2_17)
- The three dimensions, according to a secondary source:
  - **Visual salience:** facade area, shape, colour, visibility.
  - **Semantic salience:** cultural or historical importance.
  - **Structural salience:** position relative to intersections and boundaries.
  — summarised in [arXiv 1907.05289](https://arxiv.org/pdf/1907.05289) (secondary; I could not verify against the original full text)
- Known limitation: Raubal & Winter score salience at single decision points, independent of the route. Winter (2003) added *advance visibility*, meaning how visible a landmark is to a person approaching the decision point. — [arXiv 1907.05289](https://arxiv.org/pdf/1907.05289); see also Winter "Route adaptive selection of salient features" (COSIT 2003) — [Springer](https://www.springerprofessional.de/route-adaptive-selection-of-salient-features/14272238)
- Nothegger, Winter & Raubal (2004) added visibility to the definition. Winter et al. (2005) asked people to rank facades by prominence and found that **visibility and colour** were significant. — reported via search summary of [Caduff dissertation / related literature](https://www.geo.uzh.ch/geo/dam/jcr:e76a0a6d-da55-425f-a952-df7f62f25191/2007_Dissertation_Caduff.pdf) (secondary; not verified in the original)
- Caduff & Timpf (2008, *Cognitive Processing* 9(4):249–267) model salience in three parts:
  - **Perceptual salience:** stimulus-driven, passive attention.
  - **Cognitive salience:** informed, active attention.
  - **Contextual salience:** depends on modality and task.
  They argue salience is not inherent to a feature. It depends on the observer's physical and cognitive viewpoint and on the surrounding objects. Their evaluation found the framework reasonably accurate for perceptually distinct objects. — [DOI 10.1007/s10339-007-0199-2](https://www.doi.org/10.1007/s10339-007-0199-2)
- Klippel & Winter (COSIT 2005, LNCS 3693, pp. 347–362), "Structural Salience of Landmarks for Route Directions", formalises the structural salience of point-like objects by their **position along the route**. It extends wayfinding choreme theory, with the aim of automatically placing landmarks in route directions. — [WUR record](https://research.wur.nl/en/publications/structural-salience-of-landmarks-for-route-directions); [Unpaywall](https://unpaywall.org/10.1007%2F11556114_22)
- Klippel, Richter & Hansen ("Structural Salience as a Landmark", Mobile Maps 2005) argue that anything that stands out from its background can serve as a landmark, and that structural features can stand in for street names. — [search summary, SFB/TR8 records](https://cindy.informatik.uni-bremen.de/www3/www.sfbtr8.spatial-cognition.de/aigaion/index.php/publications/show/312.html)
- Indoors, Fellner et al. (2017, ISPRS IJGI 6:183) generate landmark-based indoor instructions automatically from spatial databases. A campus case study produced mostly correct instructions with landmarks. — [TU Wien cartography](https://cartography.tuwien.ac.at/?p=2952); [WU research page](https://research.wu.ac.at/de/publications/turn-left-after-the-wc-and-use-the-lift-to-go-to-the2nd-floor-gen-3/)

### Inferences
- A computable indoor salience score for a candidate object *o* at decision point *d*:
  `S(o,d) = w_v·Visual(o) + w_s·Semantic(o) + w_st·Structural(o,d) + w_vis·AdvanceVisibility(o,d)`
  - **Visual:** normalised footprint or height (big machines are better than small sensors), plus distinct colour or shape if known.
  - **Semantic / uniqueness:** inverse frequency of the object's category within the visible set at *d*, for example `1 − (count_same_category_visible / count_visible)`. A unique "red press" beats "a cabinet" when there are 10 cabinets. Meaningful names score higher, such as "coffee machine" or "fire extinguisher".
  - **Structural:**
    - Highest when the object sits at the decision point itself.
    - Higher on the side of the turn ("on your left, turn left") and just before the turn rather than after it.
    - Lower when it sits mid-segment. It is still useful there as a confirmation landmark.
  - **Advance visibility:** line of sight from the approach segment, for example the fraction of sampled points over the last N metres of approach with an unobstructed ray to *o*.
- The weights are not standardised in the sources I accessed. Treat them as tunable, starting with structural and visibility weighted highest, since what matters most is identifying the decision point.

### Gaps
- I could not get the exact formulas or weights of Raubal & Winter 2002 or the position taxonomy of Klippel & Winter 2005. The PDFs were not readable through fetch.
- I found no source validating salience weights for indoor industrial objects such as machines.
- Ohm et al. (2015, *J. Ambient Intelligence & Smart Environments*), reported in a search summary, found "functional" indoor landmarks such as doors and stairs suitable for navigation. I did not retrieve a URL or the full text.

## 2. Chunking, segment aggregation, decision points and which turns to mention

### Takeaway
Route directions should be built as decision-point/action pairs and then *chunked*: consecutive elementary actions merge into higher-order instructions. Examples are "take the second right", "go to the end of the corridor" and "follow until the lifts". Richter & Klippel's GUARD treats this as an optimisation that picks the instruction sequence easiest to conceptualise.

### Cited Findings
- Klippel's wayfinding choremes are conceptual primitives of route directions, derived partly from sketch-map analysis. The theory separates functional elements (actions) from structural elements (objects), and the behavioural evidence shows people combine choremes. — [Theory of Wayfinding Choremes, SFB/TR8](https://cindy.informatik.uni-bremen.de/www3/www.sfbtr8.spatial-cognition.de/en/project/interaction/i2-mapspace/research/theory-of-wayfinding-choremes/index.html); [Penn State record](https://pure.psu.edu/en/publications/wayfinding-choremes/)
- Klippel, Hansen, Richter & Winter, "Urban granularities", define *spatial chunking* as combining elementary route information into higher-order elements, which changes granularity. Their data structure follows the hierarchical organisation of spatial knowledge. — [WUR](https://research.wur.nl/en/publications/urban-granularities-a-data-structure-for-cognitively-ergonomic-ro/); [Unpaywall](https://unpaywall.org/10.1007%2FS10707-008-0051-6)
- Richter & Klippel, "A Model for Context-Specific Route Directions" (LNAI 3343, 2005, pp. 58–78), and Richter's 2008 dissertation (GUARD):
  - A route is a sequence of decision-point/action pairs.
  - Directions are generated by optimisation, selecting the instructions that most ease conceptualisation.
  - Chunking merges consecutive instructions, and landmarks are used.
  - The output is a sequence of chunks, one instruction each.
  — [Context-Specific Route Directions project](https://cindy.informatik.uni-bremen.de/www3/www.sfbtr8.spatial-cognition.de/en/project/interaction/i2-mapspace/research/context-specific-route-directions/index.html); [Penn State](https://pure.psu.edu/en/publications/a-model-for-context-specific-route-directions/)
- Chunking rules adapted from Klippel, as summarised in Nourin et al. 2024:
  - **Numerical chunking:** count decision points, for example "take the second turn".
  - **Structural chunking:** go "till the escalators" or to the end of a structure.
  - **Landmark chunking:** point, linear or area landmarks, including global landmarks that let you skip intermediate decision points.
  - **Cue words:** "then" and "continue" at segment boundaries, plus pauses, reinforce chunking.
  — [Nourin, Pramanick & Sarkar 2024, arXiv 2408.15367](https://arxiv.org/html/2408.15367v1)
- Denis-derived guidelines quoted in the same paper:
  - Limit the number of statements.
  - Avoid redundancy and over-specification.
  - Refer to visible, permanent, relevant landmarks.
  - Prefer determinate descriptions.
  - Clearly link actions to landmarks.
  — [arXiv 2408.15367](https://arxiv.org/html/2408.15367v1)
- Landmark-based instructions such as "Turn right after the second door, and use the elevator to go to the second floor" help users identify unambiguously the decision point where they must change direction, compared with metric instructions. — [WU Vienna research page](https://research.wu.ac.at/de/publications/turn-left-after-the-wc-and-use-the-lift-to-go-to-the2nd-floor-gen-3/)

### Inferences
- A decision point is any node where the route has more than one plausible continuation: corridor junctions, door choices, stair or lift lobbies.
- **Mention:**
  - every direction change at a decision point;
  - every "go straight" at a decision point where a turn is plausible, such as a T-junction or a corridor crossing;
  - every mode change: door, stairs, lift, floor.
- **Don't mention** straight passes through nodes with no alternative branch. Fold them into a chunk.
- **Merge** consecutive "straight" segments into one instruction, ended by a salient landmark or structural feature ("until the end of the corridor", "until you reach the lifts").
- **Use counting** ("second door on the left") only when the count is 3 or less and every counted item is clearly identifiable. Counting longer sequences is error-prone. This is an inference: I found no indoor study putting a number on the limit.

### Gaps
- I found no full-text GUARD cost function.
- I found no quantitative study of how accurately people count doors indoors.

## 3. Indoor-specific findings: corridors, lifts and stairs, floor changes, door counting, room numbers vs landmarks

### Takeaway
Indoor evidence favours landmark-enriched instructions over purely metric ones, with doors, stairs, lifts and toilets as natural landmarks. I found no clean head-to-head study of room-number and landmark instructions. Floor changes are a distinct high-risk step and should be stated explicitly: mode, direction, target floor, and what to do on exit.

### Cited Findings
- Fellner et al. (2017) automatically generate landmark-based indoor routing instructions from spatial databases. A campus case study produced mostly correct instructions containing landmarks. — [TU Wien](https://cartography.tuwien.ac.at/?p=2952)
- Compared with purely metric instructions, landmarks raise the quality of indoor route instructions (thesis comparison). — [UNIGIS master thesis](https://unigis.at/files/Mastertheses/Full/103050.pdf)
- Category-based landmark example: "turn left after the WC and use the lift to go to the 2nd floor". Landmarks help pick out the correct decision point unambiguously. — [WU research](https://research.wu.ac.at/de/publications/turn-left-after-the-wc-and-use-the-lift-to-go-to-the2nd-floor-gen-3/)
- Münzer & Stahl (Spatial Cognition 2008 poster) studied learning visual route instructions indoors:
  - Critical errors differed significantly between instruction conditions (Kruskal-Wallis χ²(2)=6.835, p<.05).
  - In the naturalistic setting, participants also used environmental cues such as room numbers.
  — [DFKI PDF](https://www.dfki.de/fileadmin/user_upload/import/5372_Muenzer_Stahl_SC08PosterSubmissionSpringerFormat.pdf)
- Gondorf & Jian (Bremen) studied written instructions in a multilevel building. Adding structural or architectural information selectively helps people build a cognitive map and infer return paths. — [CEUR-WS Vol-759 paper07](https://ceur-ws.org/Vol-759/paper07.pdf)
- All four routes in Nourin et al. 2024 included a stair or lift floor change. Short (4-segment) descriptions had the highest success rate, 85%. — [arXiv 2408.15367](https://arxiv.org/html/2408.15367v1)
- Commercial indoor routing APIs, such as Woosmap, model level changes explicitly: stairs, escalators, elevators, ramps. Mapsted supports avoiding stairs and preferring lifts. — [Woosmap indoor directions](https://developers.woosmap.com/products/indoor-api/guides/direction-service/); [Mapsted](https://developer.mapsted.com/mobile-sdk/overview/wayfinding/)

### Inferences
- Use room numbers as **confirmation and destination cues**, not as the main guidance. People do read them, per Münzer & Stahl, but they are small and hard to see from a distance (low advance visibility). Prefer a large salient object or structural feature at the decision point, and add the room number when it is posted at the turn.
- **Floor-change template:**
  1. "Take the lift / stairs [landmark: next to X] **up/down** to **floor N**."
  2. "When you come out, turn left / right [toward landmark]."
  The exit orientation is the classic disorientation point in multilevel buildings.
- Corridors are linear landmarks. "Follow this corridor to the end" chunks many doors into one step.

### Gaps
- I found no controlled study comparing room-number, landmark and metric instructions indoors with outcome measures. Hölscher et al.'s multi-level building wayfinding work is relevant, but I did not retrieve it.
- I found no quantitative data on door-counting accuracy.

## 4. Spoken directions: length per instruction, how many at once, metres vs steps

### Takeaway
Give at most about 4 segments of a route at once. Each segment should be a single orientation + action + landmark triplet, with a pause between segments. Longer spoken descriptions (6–8 segments) slowed navigation significantly. For blind users, step counts did better than feet or time. For sighted users, prefer landmarks to any metric.

### Cited Findings
- Nourin, Pramanick & Sarkar (2024), from the full text:
  - **Participants:** 27 first-time visitors (non-native English speakers), 80 trials in an office building.
  - **Conditions:** 4, 6 and 8 segments. A segment is an *orientation + action + landmark* triplet, treated as one working-memory chunk, with 2-second pauses between segments.
  - **Success:** 85% (4 segments), 65% (6) and 67% (8). The difference was not significant, χ²(2)=3.30, p=.19.
  - **Total duration:** differed significantly, F(2,59)=7.15, p=.002. Means were 92.3, 103.2 and 154.1 (units not stated).
  - **Walking pace:** significant, p=.009.
  - **Confidence:** fell from 4.09 to 3.78 as length increased (not significant).
  - **Conclusion:** the authors suggest 4 segments is ideal, citing Cowan's limit of about 4 chunks.
  - **Caveat:** most effects are "trends" in a small sample.
  — [arXiv 2408.15367](https://arxiv.org/html/2408.15367v1)
- Meilinger, Knauff & Bülthoff (2008): encoding route knowledge interfered with both a verbal and a spatial secondary task, so route learning loads working memory. — [Meilinger et al. 2008 (Tübingen)](https://uni-tuebingen.de/securedl/sdl-eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3MzE0OTgzNDYsImV4cCI6MTczMTU4ODM0NiwidXNlciI6MCwiZ3JvdXBzIjpbMCwtMV0sImZpbGUiOiJmaWxlYWRtaW4vVW5pX1R1ZWJpbmdlbi9GYWt1bHRhZXRlbi9JbmZvS29nbmkvUEkvT3JnYW5pc2F0aW9uX0FidGVpbHVuZ2VuL0FuZ19Lb2duaXRpb25zcHN5Y2hvX01lZGllbnBzeWNoby9Eb2N1bWVudGUvVG9iaWFzX01laWxpbmdlcl9QdWJsaWthdGlvbmVuL21laWxpbmdlcl9ldF9hbF8yMDA4X3dvcmtpbmdfbWVtb3J5X2luX3dheWZpbmRpbmcucGRmIiwicGFnZSI6MTc1MjM5fQ.Wt3caJhnOA23pt0G3dfXM--VnCNUCyL8xiPDe7VzY-c/meilinger_et_al_2008_working_memory_in_wayfinding.pdf) (signed link; may expire)
- Kalia, Legge, Roy & Ogale (2010): users with visual impairments found routes better when distances were given as **number of steps** rather than walking time or feet. — [Kalia et al. 2010 PDF](https://legge.dl8.umn.edu/sites/legge.psych.umn.edu/files/2020-08/Kalia%20Legge%20Roy%20Ogale%202010%20Assessment%20of%20indoor%20route%20finding%20technology%20for%20visually-impaired%20people.pdf)
- Anacta, Wang & Schwering (2014) compared verbal instructions with sketch maps. Participants added landmarks and streets that were not in the verbal instructions, which suggests people reconstruct routes around landmarks. — [Münster CRIS](https://cris-portal.uni-muenster.de/portal/en/publication/20640022)

### Inferences
- **Spoken mode:**
  - Deliver the route incrementally: the next 1–2 steps in-situ, or at most about 4 chunks for an up-front overview.
  - Re-prompt at each decision point.
  - Each instruction should be one sentence, roughly ≤15 words, with one action. The word count is an inference from the one-triplet-per-segment design, not a measured threshold.
- **Written mode:** you can show the whole chunked list, but keep the same chunk structure (numbered steps).
- **Distances:**
  - For sighted users, use metres only for long featureless stretches, and round them ("about 20 m").
  - For blind users, use steps, or metres with a step conversion calibrated per user.

### Gaps
- I found no study isolating the best words per spoken instruction.
- I found no direct metres-vs-steps comparison for sighted indoor users.

## 5. LLM-based route description generation and automatic followability evaluation

### Takeaway
LLMs on their own are unreliable at spatial planning. Use them to *verbalise* a route that has already been computed and annotated with landmarks, not to plan it. Text-overlap metrics (BLEU, ROUGE, METEOR, CIDEr) are poor proxies for instruction quality. Evaluate by *execution*: have a follower agent or a human follow the instruction and measure whether it ends at the goal and how closely it tracks the path.

### Cited Findings
- Zhao et al. (EACL 2021), "On the Evaluation of Vision-and-Language Navigation Instructions":
  - With human wayfinders, neural R2R instruction generators were on par with or only slightly better than a **template-based generator**, and far worse than humans.
  - BLEU, ROUGE, METEOR and CIDEr are ineffective for grounded navigation instructions.
  - A learned instruction–trajectory compatibility model correlated best with human wayfinding outcomes.
  - SPICE is recommended for system ranking when references exist.
  — [ACL Anthology](https://aclanthology.org/2021.eacl-main.111/); [arXiv 2101.10504](https://arxiv.org/abs/2101.10504v1)
- MacMahon (2007): of 1,520 human-written route instructions, human followers succeeded only about two-thirds of the time. The MARCO follower agent reached 88% of human performance on the highest-rated instructions. — [MacMahon PhD, UT Austin](https://cs.utexas.edu/users/qr/papers/MacMahon-PhD-07.html)
- GROKE (ACL 2026, arXiv 2601.07375) is a training-free, vision-free LLM framework that evaluates navigation instructions against OSM data. It uses an agent's execution success and trajectory fidelity as followability proxies and reports a 68.5% reduction in navigation error versus heuristic baselines on Map2Seq. — [arXiv 2601.07375](https://web3.arxiv.org/pdf/2601.07375)
- GIST (arXiv 2604.15495) uses an LLM-as-judge on five communication criteria, including egocentric clarity, landmark utility and cognitive load. It argues BLEU and ROUGE correlate poorly with grounded route following. — [arXiv 2604.15495](https://arxiv.org/pdf/2604.15495)
- Chen et al., "Can LLMs plan paths in the real world?": GPT-4, Gemini and Mistral made many errors on turn-by-turn and landmark-based route generation, so the authors judged them unreliable path planners. — [arXiv 2411.17912](https://arxiv.org/html/2411.17912v2)
- "Beyond Prompts" benchmark: an LLM converts the response into structured JSON, which is then executed to check whether the endpoint matches. This is a cheap automatic followability check. — [arXiv 2409.20222](https://arxiv.org/pdf/2409.20222)
- Indoor LLM work:
  - **Coffrini et al.** generate instructions from map images with ChatGPT. The accuracy reported differs between paper versions: an average of 50.54% correct in early versions versus 86.59% in v4. Performance depended more on the number of POIs and on visual clutter than on layout complexity. — [arXiv 2503.11702](https://arxiv.org/abs/2503.11702v4)
  - **Floorplan2Guide** parses floor plans into a knowledge graph. Few-shot prompting beat zero-shot, but the evaluation used one sighted participant. — [arXiv 2512.12177](https://arxiv.org/pdf/2512.12177)
  - **Agentic floor-plan parsing** notes that multi-floor support needs elevator and stair logic. — [arXiv 2604.23970](https://arxiv.org/pdf/2604.23970)

### Inferences
- **Recommended pipeline:**
  1. Run a deterministic graph planner.
  2. Do deterministic landmark selection and chunking into a structured instruction plan (JSON).
  3. Have an LLM render the plan into natural spoken or written text, under constraints: no new facts, every landmark from the plan.
  4. Run automatic verification by **back-translation**: a second LLM or rule parser converts the text back into an action sequence, which is executed on the graph and must reach the goal via the same decision points.
  5. Run hallucination checks, for example that every mentioned entity exists in the graph and is visible at that step.
- Zhao et al. show a strong template generator is competitive. Keep a template fallback.

### Gaps
- I found no published study evaluating LLM-verbalised indoor instructions with real followers against a template baseline.
- Touchdown and Talk2Nav were not researched in depth within the call budget.

## 6. Accessibility variants (blind and low-vision users)

### Takeaway
For blind and low-vision (BLV) users:
- Give turn-by-turn instructions at short range.
- Use step counts.
- Use landmarks that can be perceived without vision: tactile paving, doors, floor-surface changes, sounds.
- Optionally use clock-face directions, but only after a brief tutorial.
- Warn about hazards such as stairs.

### Cited Findings
- NavCog3 (Sato et al., ASSETS 2017 / ACM TACCESS 2019) is a beacon-based smartphone turn-by-turn assistant. Besides turn-by-turn instructions, it tells users about landmarks such as tactile paving and nearby points of interest. It was evaluated in a five-storey, three-building shopping mall. — [IBM Research](https://research.ibm.com/publications/navcog3-an-evaluation-of-a-smartphone-based-blindindoor-navigation-assistant-with-semantic-features-in-a-large-scale-environment); [Ewha record](https://pure.ewha.ac.kr/en/publications/navcog3-an-evaluation-of-a-smartphone-based-blindindoor-navigatio/)
- Original NavCog (MobileHCI 2016):
  - announces nearby POIs and accessibility issues, for example "stairs ahead";
  - gives instructions as speech or as non-verbal clicks that rise in pitch as the user nears the next waypoint.
  — [CMU RI](https://ri.cmu.edu/publications/navcog-a-navigational-cognitive-assistant-for-the-blind)
- Kalia et al. (2010): step counts beat feet and time for visually impaired users. — [Kalia et al. 2010](https://legge.dl8.umn.edu/sites/legge.psych.umn.edu/files/2020-08/Kalia%20Legge%20Roy%20Ogale%202010%20Assessment%20of%20indoor%20route%20finding%20technology%20for%20visually-impaired%20people.pdf)
- A Münster 2017 study, "Increasing the density of local landmarks in wayfinding instructions for the visually impaired", found that adding local landmarks to turn-by-turn audio improved satisfaction and confidence. The landmarks were features that blind travellers detect spontaneously while moving. — [Münster CRIS](https://cris-portal.uni-muenster.de/portal/en/publication/23084917)
- An inertial phone-in-pocket indoor wayfinding app announces a landmark with its side (left or right) once the user is within about 2 m, using a shorter trigger distance than for junction alerts. — [arXiv 2401.08021](https://arxiv.org/pdf/2401.08021)
- Clock-face directions:
  - A 2010 audio-GPS study reportedly found "12 o'clock = straight ahead" more intuitive for blind users than cardinal directions or left/right.
  - Clock directions need a learning period and are harder under time pressure.
  - Touvigation (2026) taught a body-anchored clock convention with a short audio tutorial.
  — [a11y-paradise glossary (secondary aggregator)](https://a11y-paradise.onrender.com/glossary/69ad9423ad441d9f3b300d83); [Touvigation, arXiv 2609.21828](https://arxiv.org/pdf/2609.21828)

### Inferences
- **BLV mode should:**
  - give one instruction at a time, triggered by position;
  - use steps;
  - use clock-face directions for non-orthogonal turns, only if the user opted in or has done the tutorial;
  - use tactile or auditory landmarks: door frames, carpet-to-tile changes, the hum of a machine, handrails;
  - always pre-announce stairs, escalators and lifts, including the lift button side and floor-announcement cues;
  - avoid purely visual landmarks such as colour or signage.
- For BLV users, salience must be recomputed with perceptual channels other than vision: tactile, auditory, olfactory. This is the "contextual/modality" component in Caduff & Timpf.

### Gaps
- I could not verify the primary 2010 clock-face study. The source was an aggregator.
- Clew (an AR path-retracing app) was not specifically documented in the sources I found.
- I found no NavCog3 quantitative results; the PDF was not readable.

## 7. Synthesis: concrete algorithm sketch and cited rule list

### Takeaway
Build the route deterministically, enrich and chunk it with explicit salience scoring, render it with templates or a constrained LLM, and verify it by execution.

### Cited Findings (rules; each cites its basis)
- **R1.** Represent the route as decision-point/action pairs, and generate instructions only at decision points and mode changes. — [Richter & Klippel 2005](https://pure.psu.edu/en/publications/a-model-for-context-specific-route-directions/)
- **R2.** Chunk consecutive straight segments into one instruction, ended by a structural feature or landmark ("to the end of the corridor", "until the lifts"). — [Klippel et al., Urban granularities](https://research.wur.nl/en/publications/urban-granularities-a-data-structure-for-cognitively-ergonomic-ro/); [Nourin et al. 2024](https://arxiv.org/html/2408.15367v1)
- **R3.** Use numerical chunking ("second door on the left") only for small counts. Prefer a landmark at the turn when one exists. — [Nourin et al. 2024 (Klippel chunking rules)](https://arxiv.org/html/2408.15367v1); [WU landmark vs metric](https://research.wu.ac.at/de/publications/turn-left-after-the-wc-and-use-the-lift-to-go-to-the2nd-floor-gen-3/) (the "≤3" limit is an inference)
- **R4.** Anchor each turn to the most salient landmark at the decision point. Score it on visual, semantic/uniqueness and structural (position) salience. — [Raubal & Winter 2002](https://cris.uni-muenster.de/portal/en/publication/16971808); [Klippel & Winter 2005](https://research.wur.nl/en/publications/structural-salience-of-landmarks-for-route-directions)
- **R5.** Favour landmarks visible on approach (advance visibility). — [Winter 2003 via arXiv 1907.05289](https://arxiv.org/pdf/1907.05289)
- **R6.** Salience depends on the observer and the task. Compute it per user modality (sighted vs BLV). — [Caduff & Timpf 2008](https://www.doi.org/10.1007/s10339-007-0199-2)
- **R7.** Only refer to visible, permanent, relevant landmarks. Avoid redundancy and over-specification, and link each action clearly to its landmark. — [Denis guidelines via Nourin et al. 2024](https://arxiv.org/html/2408.15367v1)
- **R8.** Prefer landmark-based over purely metric indoor instructions. — [UNIGIS thesis](https://unigis.at/files/Mastertheses/Full/103050.pdf); [WU](https://research.wu.ac.at/de/publications/turn-left-after-the-wc-and-use-the-lift-to-go-to-the2nd-floor-gen-3/)
- **R9.** Give no more than about 4 segments at once in spoken directions. Each segment is orientation + action + landmark, separated by pauses or cue words ("then"). — [Nourin et al. 2024](https://arxiv.org/html/2408.15367v1)
- **R10.** State floor changes explicitly, with mode, direction and target floor, and add selective architectural or structural information to support a mental map. — [Gondorf & Jian](https://ceur-ws.org/Vol-759/paper07.pdf); [Woosmap level-change model](https://developers.woosmap.com/products/indoor-api/guides/direction-service/)
- **R11.** Use room numbers as secondary confirmation cues, because people do use them. — [Münzer & Stahl 2008](https://www.dfki.de/fileadmin/user_upload/import/5372_Muenzer_Stahl_SC08PosterSubmissionSpringerFormat.pdf)
- **R12.** For BLV users:
  - give distances in steps;
  - mention landmarks that can be perceived without vision, such as tactile paving;
  - pre-announce hazards ("stairs ahead");
  - announce landmarks with their side within about 2 m.
  — [Kalia et al. 2010](https://legge.dl8.umn.edu/sites/legge.psych.umn.edu/files/2020-08/Kalia%20Legge%20Roy%20Ogale%202010%20Assessment%20of%20indoor%20route%20finding%20technology%20for%20visually-impaired%20people.pdf); [NavCog](https://ri.cmu.edu/publications/navcog-a-navigational-cognitive-assistant-for-the-blind); [arXiv 2401.08021](https://arxiv.org/pdf/2401.08021); [Münster 2017](https://cris-portal.uni-muenster.de/portal/en/publication/23084917)
- **R13.** Offer clock-face directions to BLV users only with a short tutorial. — [Touvigation](https://arxiv.org/pdf/2609.21828); [a11y glossary](https://a11y-paradise.onrender.com/glossary/69ad9423ad441d9f3b300d83)
- **R14.** Do not let the LLM plan the path. Have it verbalise a precomputed, structured plan. — [Chen et al. arXiv 2411.17912](https://arxiv.org/html/2411.17912v2)
- **R15.** Evaluate instructions by execution (endpoint success, trajectory fidelity) or with a reference-free compatibility or judge model, not BLEU or ROUGE. Keep a template baseline. — [Zhao et al. 2021](https://aclanthology.org/2021.eacl-main.111/); [GROKE](https://web3.arxiv.org/pdf/2601.07375); [GIST](https://arxiv.org/pdf/2604.15495); [Beyond Prompts](https://arxiv.org/pdf/2409.20222)

### Inferences (algorithm sketch)
```
INPUT: path P = [n0..nk] over graph G (nodes: room|door|corridor|junction|stair|lift; edges with geometry, floor),
       landmarks L (type, position, footprint, height, floor, perceptual tags), user profile U (sighted|BLV, units), mode (spoken|written)

1. ANNOTATE STEPS
   for each node ni on P:
     heading_in, heading_out -> turn angle θ -> qualitative direction
        (straight |θ|<30°, slight 30–60°, turn 60–135°, sharp >135°; BLV: clock hour round(θ/30))
     is_decision = degree(ni) > 2 with alternative non-trivial branch, OR mode/floor change, OR door passage
2. LANDMARK CANDIDATES per decision point d
   C = landmarks within radius r (e.g. 5–8 m) on same floor with line-of-sight to d
   for o in C: S = w1*size_norm(o) + w2*uniqueness(o,C) + w3*structural(o,d,turn_side)
                   + w4*advance_visibility(o, approach segment) + w5*permanence(o)
     structural: at-turn & on turn side=1.0; at-turn opposite side=0.8; before turn=0.7; after turn=0.5; mid-segment=0.3
     uniqueness = 1 - (same-category count in C -1)/|C|
     BLV: replace visual terms with tactile/auditory perceptibility; drop non-perceivable o
   anchor(d) = argmax S if S > τ else None
3. CHUNK
   merge consecutive non-decision or 'straight' steps into one segment; terminate segment at next turn/mode change.
   terminal descriptor priority: anchor landmark > structural end ("end of corridor", "the lifts")
        > ordinal count of identical items if count<=3 > rounded metric distance (steps for BLV).
   add a confirmation landmark mid-segment if segment > ~30 m (inference).
4. FLOOR CHANGE TEMPLATE
   "Take the {lift|stairs} [next to X] {up|down} to floor N. When you come out, turn {dir} toward {landmark}."
5. PLAN JSON -> RENDER
   templates (baseline) or LLM with constraints: one action per sentence, only plan entities, cue words "then".
   spoken: emit ≤4 segments up front, then re-prompt per decision point; written: numbered list of all segments,
   destination confirmation with room number.
6. VERIFY
   back-parse rendered text -> action sequence -> simulate on G; require goal reached via same decision points;
   check every mentioned entity exists & is visible; optionally LLM-judge for clarity/landmark utility/cognitive load.
   on failure: fall back to template output.
```
- The thresholds (30°/60°/135° angle bands, structural weights, 5–8 m radius, 30 m confirmation interval) are engineering defaults I chose. They are not taken from the cited sources.

### Gaps
- None of the specific numeric weights or thresholds above is validated in the literature I accessed. They need empirical tuning, for example with the execution-based evaluation in R15.
