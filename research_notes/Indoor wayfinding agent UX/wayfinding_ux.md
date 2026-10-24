# UX of Indoor Wayfinding: Apps, Signage, Voice, and Accessibility

Scope note: about 16 web searches and fetches. Several key papers were found only as abstracts or snippets, and some fetches failed (the Pharos PDF and the Regensburg eprint). Items marked "(abstract/snippet only)" were not checked against full text. Items marked "[background, unverified this session]" come from my prior knowledge without a source fetched in this session. The report writer should treat them as hypotheses, not cited facts.

## 1. What leading products and studies do: map-first, step-first, or combined?

### Takeaway
The leading products combine the two. They show a map with a highlighted route plus a list of steps, offer category "Directory" browsing, and have a single toggle for accessible or step-free routing. The evidence does not show map or text winning outright. Voice-only guidance can match a map when the instructions are well written. Many hospital visitors still prefer signs and people over apps.

### Cited Findings
- Google Maps Indoor Live View (Sydney Airport, Nov 2023): users search the venue and tap a **"Directory" button** to browse categories (gates, baggage claim, check-in, retail, dining, restrooms, ATMs). A **Live View** button starts AR walking guidance. There is a **"Wheelchair accessible" preference** (wheelchair, pram and suitcase friendly paths), and **audio prompts can be turned on alongside visual cues** — [Google AU blog](https://blog.google/intl/en-au/products/explore-get-answers/indoor-live-view-sydney-airport/); [Travel Weekly](https://www.travelweekly.com.au/article/google-launches-aussie-first-indoor-live-view-at-sydney-airport/); [Sydney Airport](https://sydneyairport.com.au/sydhub/google)
- Mappedin: the SDK returns the **shortest route by default**. Accessible routing is an explicit flag, `getDirections(a, b, {accessible: true})`, and accessible routes prioritise elevators. Mappedin markets screen-reader compatibility, adjustable text size and WCAG 2.1 AA — [Mappedin dev docs](https://developer.mappedin.com/web/v6/guides/wayfinding/); [Mappedin wayfinding](https://www.mappedin.com/wayfinding/); [Mappedin accessibility blog](https://www.mappedin.com/resources/blog/accessible-indoor-navigation-software/)
- Pointr: search tolerates misspellings, has autocomplete and relevance sorting, and venues can review **search logs** to see what visitors look for. The same maps are deployed on mobile and **on-site kiosks** — [Pointr navigation](https://pointr.tech/solutions/indoor-navigation); [Fitgap review of Pointr Maps](https://us.fitgap.com/products/018043/pointr-maps)
- Rehrl et al. (J. Location Based Services 2014, 48 participants, Salzburg field study) compared voice-only, digital map and AR guidance. **Map and voice-only both beat AR**, and voice and map gave **similar results "given that voice instructions are carefully composed"**. Measures included stops, walking time, NASA-TLX and SUS (abstract only) — [Salzburg Research](https://salzburgresearch.at/?p=14599); [ISPRS 2012 version](https://isprs-archives.copernicus.org/articles/XXXIX-B2/119/2012/isprsarchives-XXXIX-B2-119-2012.pdf)
- Hospital survey (Ženka et al., IJERPH 2021, about 928 patients and visitors, Ostrava): about two-thirds said newcomers may struggle, yet **only 35.2% of men and 29% of women would use a smartphone app**. Only respondents under 40 favoured app navigation. The most-requested improvements were **floor colour strips, more signs and arrows, and more maps**. Recommended architecture: a routing graph with accessibility attributes on edges, a **browser-based app** (no install), **QR codes for indoor positioning**, visual or voice directions, an admin tool for instant updates, and kiosks for people without smartphones — [PMC7908200](https://pmc.ncbi.nlm.nih.gov/articles/PMC7908200)
- UW Northwest hospital interactive map pilot (DNP project, 212 users): 40% of new employees got lost using traditional tools, and most participants still named signs as their preferred aid (small student project) — [Seattle U ScholarWorks](https://scholarworks.seattleu.edu/dnp-projects/112)
- AR vs paper map in a hospital (32 participants): AR was faster, with fewer errors and lower anxiety and workload, but **paper-map users had better spatial memory**. The venue is unverified and the arXiv ID looks unusual, so treat with caution — [arXiv 2601.00001](https://arxiv.org/pdf/2601.00001)
- MapsPeople UX tips: group related POIs under parent categories (for example one "Meeting Rooms" category). People look out of windows to confirm their position, so **outdoor landmarks shown on the indoor map help orientation** — [MapsPeople blog](https://blog.mapspeople.com/3-tips-to-enhancing-the-user-experience-of-your-indoor-maps)

### Inferences
- Use a combined layout: a step list as the primary content (it also works for speech and screen readers) plus a map with the route highlighted. On a phone, a bottom sheet holds the steps and the map sits above.
- Step-free routing should be a persistent, visible profile setting ("Step-free: on"), not a hidden flag. Products default to shortest-path routing, so a wheelchair user who forgets the toggle gets stairs. Store the setting per user and say it out loud in every route ("Step-free route via Lift B").
- Because many visitors distrust apps, it must be a no-install web app reached by a QR code at the entrance, and kiosks at entrances support the same flow.
- Log failed searches so the facility manager can see what people asked for and add synonyms or aliases.

### Gaps
- No controlled study found that directly compares map-first, list-first and combined UIs for indoor routes.
- Apple Maps indoor (IMDF venues), Situm and Mapwize UX docs were not retrieved.

## 2. Turn-by-turn vs landmark-based vs room-number directions; length; spoken vs written

### Takeaway
Landmark-anchored instructions at decision points work best indoors. "Turn right after the second door" and "turn left at the press" beat metric phrasing ("walk 20 m") because they pin down where to act. Show one salient landmark per instruction, not several. People remember turns and decision points and walk straight by default, so instructions should be given only at turns and decision points.

### Cited Findings
- Comparing landmark-based with metric indoor instructions (university campus): landmark-based instructions let users **unambiguously identify the decision point** where direction changes, for example "Turn right after the second door" (snippet) — [MDPI IJGI 6(6):183](https://www.mdpi.com/2220-9964/6/6/183/xml)
- Bauer et al. (Regensburg): an indoor navigation UI showing **one landmark (N=63) vs four landmarks (N=60)**. Showing **only a single prominent landmark** gave higher navigation efficiency (as cited by the Pharos paper; full text not retrieved) — [Regensburg eprint](https://epub.uni-regensburg.de/35320); [Pharos, arXiv 1904.01694](https://arxiv.org/pdf/1904.01694)
- Ohm, Müller & Ludwig (2015): **functional landmarks such as doors and stairs** are suitable for indoor navigation. Users with a good sense of direction did better with a graph-like interface (abstract) — [Springer](https://link.springer.com/doi/10.1007/978-3-319-16787-9_15)
- Outdoor evidence: at some decision points, relative-direction instructions beat landmark ones, so the instruction type should be chosen per decision point (snippet) — [Nottingham repository](https://nottingham-repository.worktribe.com/OutputFile/828188)
- Meilinger et al. 2014 ("When in doubt follow your nose"): navigators **mainly remember information at decision points and turns**, not at intersections where they walk straight. People seem to memorise only the turns and go straight by default, which reduces working-memory load — [Frontiers in Psychology](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2014.01363/full)
- Hierarchical planning: people plan to a broad target area first and then plan the rest in detail once there. That supports chunking ("Go to Hall B, 2nd floor" and then "in Hall B, ...") — [Frontiers, same article](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2014.01363/full); Hölscher, Tenbrink & Wiener 2011 (*Cognition*) — [Bournemouth record](https://staffprofiles.bournemouth.ac.uk/display/journal-article/17059)
- Voice-only guidance is workable, with minimal errors and normal walking time, in a Vienna thesis. Rehrl found voice ≈ map when the instructions are carefully written (abstracts) — [TU Wien repositum](https://repositum.tuwien.at/handle/20.500.12708/13282); [Salzburg Research](https://salzburgresearch.at/?p=14599)

### Inferences
- Instruction template: `[action] [direction] at/after [one salient landmark]`, with the distance optional in brackets. Example: "Turn left at the hydraulic press (about 20 m)." Room numbers are the destination confirmation, not the steering cue ("…the door on your right, R-214").
- Omit "continue straight" steps unless the walk is long or the corridor branches. Merge straight segments into the next turn.
- Chunk long routes by zone or floor ("Part 1 of 3: to Lift B"). This follows hierarchical planning and keeps each spoken chunk short.
- The landmark model needs a "salience" or landmark attribute that the facility manager can set: machines, reception, vending machines, coloured doors, artwork. A first-day visitor cannot use room numbers, but anyone can see "the big yellow press".
- End each route with a confirmation cue ("You'll see the blue door marked R-214. You've arrived.").

### Gaps
- I found no hard study on the optimal number of steps per route or maximum instruction length indoors. The classic outdoor landmark work (May et al. 2003; Tom & Denis 2003, "landmark-based > street-name-based") is only cited second-hand via the Pharos snippet [background, unverified this session].
- No direct indoor comparison of spoken vs written instructions was retrieved.

## 3. 2D plan vs 3D/isometric stacked floors; showing floor changes

### Takeaway
Floor changes are the main cause of disorientation indoors. Both 2D and 3D maps beat no map on cross-floor tasks and do not differ significantly from each other. A third-person 3D view may speed orientation. The safe design is 2D per floor, with the floor change made a distinct, prominent step, plus an optional stacked or cross-section overview.

### Cited Findings
- Hölscher et al. 2006, "Up the Down Staircase" (real multi-level building): **staircase design was a major wayfinding obstacle**. Problem causes included stairway position, vertical incongruence of floors and incomprehensible signage. Experienced users preferred a **"floor strategy"** (get to the target floor first), which went with better performance (abstract and secondary citations) — [Univ. Tübingen PDF](https://uni-tuebingen.de/securedl/sdl-eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3MzE0OTgzNDYsImV4cCI6MTczMTU4ODM0NiwidXNlciI6MCwiZ3JvdXBzIjpbMCwtMV0sImZpbGUiOiJmaWxlYWRtaW4vVW5pX1R1ZWJpbmdlbi9GYWt1bHRhZXRlbi9JbmZvS29nbmkvUEkvT3JnYW5pc2F0aW9uX0FidGVpbHVuZ2VuL0FuZ19Lb2duaXRpb25zcHN5Y2hvX01lZGllbnBzeWNoby9Eb2N1bWVudGUvVG9iaWFzX01laWxpbmdlcl9QdWJsaWthdGlvbmVuL2hvZWxzY2hlcl9ldF9hbF8yMDA2X1VwX3RoZV9Eb3duX1N0YWlyY2FzZS5wZGYiLCJwYWdlIjoxNzUyMzl9.b5A-P8QHaTf8hjaOk5DdZAe4RKtCp9LnpukGj-aQisg/hoelscher_et_al_2006_Up_the_Down_Staircase.pdf) (tokenised link; may expire)
- A later Hölscher review: level changes disorient people about their heading, especially when stairs are offset from the main corridor, enclosed, or involve many turns. **Signage and cross-sectional maps that highlight multilevel connections help** (secondary summary) — [City, Territory and Architecture 2016](https://cityterritoryarchitecture.springeropen.com/articles/10.1186/s40410-016-0038-9)
- Li & Giudice 2013: 2D top-down and 3D bird's-eye maps of a virtual multi-level building **both improved pointing and vertical navigation over no map, with no significant difference between them**. 2D won one paper-based task (snippet) — [UMaine VEMI](https://umaine.edu/vemi/?p=1238)
- Li & Giudice 2012: multi-level layouts are a known obstacle, and they propose **"global indoor landmarks"** visible across floors as a remedy — [UMaine VEMI](https://umaine.edu/vemi/?p=1100)
- Mobile 3D maps (IEEE THMS 2017): a **third-person 3D view gave shorter orientation time and better clarity** than first-person 3D (2D comparison not confirmed; snippet) — [Uniud PDF](https://air.uniud.it/retrieve/e27ce0c4-defb-055e-e053-6605fe0a7873/THMS2017_Mobile3DMaps.pdf)
- Gath-Morad, Grübel, Hölscher et al. 2024 (Sci. Rep., 149 participants, VR): **visibility interacting with prior expectations** strongly affects between-floor wayfinding efficiency — [DOAJ](https://doaj.org/article/bf844b64824145d9aaa45fe44e242539)
- A 2023 ICA abstract: it remains unclear which indoor map design is most effective for pedestrian wayfinding — [ICA Abstracts](https://ica-abs.copernicus.org/articles/6/291/2023/ica-abs-6-291-2023.pdf)

### Inferences
- Default to a 2D plan of the current floor with a clear floor switcher. Show the destination floor as a second map once the user reaches it.
- Make a floor change its own step with its own icon: "Take Lift B up to Floor 2 (level 2 of 3)". Say which way to turn on exiting the lift or stairs, because that is where people lose their heading. Example: "Exit the lift, turn right toward the canteen."
- Show an optional stacked-floor or cross-section mini-diagram during multi-floor routes to show the vertical connection, as the cross-section evidence suggests.
- Follow the "floor strategy" by ordering routes to change floor early, near the entrance, where possible.

### Gaps
- Full-text effect sizes for 2D vs 3D were not obtained. No evidence was found specifically on isometric stacked-floor views.

## 4. Signage design principles and translating them to UI

### Takeaway
Healthcare guidance treats text and numbers as the primary cue and colour as secondary. It calls for high tonal contrast, at most about 5 zone colours, and sans-serif type in two weights. Translated to UI: zone colour plus zone name plus a pictogram, never colour alone. Mirror the physical sign hierarchy so the screen matches what people see on the wall.

### Cited Findings
- NHS trust focus-group material (SaTH 2025), citing the Stirling toolkit and RNIB: **don't use colour as the main wayfinding method**; text and numbers lead, and colour and art support. Target **≥30% LRV difference** between text and background. The ageing eye loses colour discrimination, so **tone matters more than hue**. People can remember **no more than about 5 colours** before differentiating becomes hard — [SaTH NHS PDF](https://www.sath.nhs.uk/wp-content/uploads/2025/06/Signage-Wayfinding-HTP-Focus-Group-5-June-2025.pdf)
- University of Sheffield signage manual: **sans-serif** type (more legible than serif), **two weights: bold for primary, regular for secondary information**. It has a dedicated information-hierarchy section — [Sheffield manual](https://sheffield.ac.uk/media/97691/download)
- Cardiff & Vale UHB: a zoning hierarchy based on nominal colour coding for functional categories — [CAVUHB FOI](https://cavuhb.nhs.wales/about-us/governance-and-assurance/freedom-of-information/disclosure-log/2023/months/august/foi-23-439-wayfinding-best-practice-document-pdf/)
- Foundational UK guidance: DH 2005 "Wayfinding: Effective Wayfinding and Signing Systems" and NHS Scotland **HTM 65** (2007), with sections on symbols and colour (full text not read) — [NHS Scotland HTM 65 archived](https://www.nss.nhs.scot/media/2874/shtm-65-v10-oct-2007-aug-2016-archived.pdf)
- Esri ArcGIS Indoors separates occupants, places (ATMs, restrooms, elevators), landmarks (fountains, art) and objects as category groups — [Esri docs](https://doc.esri.com/en/arcgis-pro/latest/help/data/indoors/points-of-interest-and-categories.html)
- Hospital survey: floor **colour strips** were the most-requested physical aid — [PMC7908200](https://pmc.ncbi.nlm.nih.gov/articles/PMC7908200)

### Inferences
- Sign hierarchy mapped to UI. The classic SEGD taxonomy of identification, directional, informational and regulatory signs is [background, unverified this session].
  - **Identification** = the arrival card: room name, number and photo or landmark.
  - **Directional** = route steps with arrows.
  - **Informational / orientation** = "you are here" map and directory.
  - **Regulatory** = hazard and restricted-zone notices ("PPE required past this line", "staff only").
- Use the building's own zone names, colours and pictograms in the UI, exactly as on the walls ("Follow the green line to Zone C"). Allow at most about 5 zone colours, always paired with a name and number.
- Use a sans-serif UI font with two weights, the destination in bold. DIN and Frutiger are classic signage faces; system sans or open faces like Inter or Atkinson Hyperlegible are reasonable web stand-ins [background, unverified this session]. Use ISO 7001 / AIGA-style public-information pictograms for toilets, lifts, stairs, exits and accessible facilities [background, unverified].

### Gaps
- SEGD, airport (for example ACRP/IATA), and DIN/Frutiger legibility evidence was not retrieved this session.

## 5. Accessibility: WCAG 2.2, step-free presentation, door widths, screen readers, colour-blind-safe routes

### Takeaway
Treat the text step list as the accessible equivalent of the map. Meet 3:1 non-text contrast for the route line, never rely on hue alone, and provide button alternatives to dragging the map. For step-free routing, model door widths, lifts and level changes as edge attributes. Show the lift outage state, because a broken lift makes a route impassable.

### Cited Findings
- **WCAG 1.4.11 Non-text Contrast (AA)**: graphical objects needed to understand content (a route line, the current-position marker) need **≥3:1 against adjacent colours**. When the background varies, test the least-contrasting area — [W3C Understanding 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast); [Digital A11Y](https://www.digitala11y.com/understanding-sc-1-4-11-non-text-contrast/)
- **WCAG 2.5.7 Dragging Movements (AA, new in 2.2)**: any drag function needs a **single-pointer alternative**. The worked example for maps is adding **up/down/left/right pan buttons** — [HK Digital Policy handbook](https://www.digitalpolicy.gov.hk/en/our_work/digital_government/digital_inclusion/accessibility/promulgating_resources/handbook/wcag2aa/9_16_dragging_movements.html); [Missouri AT: what's new in WCAG 2.2](https://at.mo.gov/wp-content/uploads/whats-new-wcag-2.2.pdf)
- Dimensions: a push wheelchair can barely pass an 80 cm corridor, needs **90 cm after a turn**, and level differences should be **<2 cm** (Japanese research project) — [KAKEN](https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-09650677). A widely cited minimum is **760 mm clear door opening entered head-on**, wider if a turn is required (secondary source) — [lintar.untar.ac.id](https://lintar.untar.ac.id/repository/penelitian/buktipenelitian_10392002_7A214255.pdf). Frankfurt criteria: **lift door ≥90 cm** (fully accessible) and **≥80 cm** (largely accessible) — [Frankfurt inklusiv](https://www.frankfurt-inklusiv.de/en/filter?L=1)
- RWTH Aachen: an out-of-order lift or renovation can be **insurmountable** for wheelchair users, and accessibility depends on the specific impairment, which argues for live status ("indoor traffic report") — [RWTH paper](https://publications.embedded.rwth-aachen.de/file/5h)
- Accessible route definition (vendor, not empirical): prefer lifts and ramps over stairs and escalators, and stay within grade and door-width limits — [Ariadne blog](https://www.ariadne.inc/resources/blogs/accessible-wayfinding-routes/)
- Hospital routing graph: add accessibility attributes to edges so wheelchair users go to lifts, not stairs — [PMC7908200](https://pmc.ncbi.nlm.nih.gov/articles/PMC7908200)

### Inferences
- In the data model each edge carries `step_free`, `min_clear_width_cm`, `door_type` (automatic, push, heavy) and `slope`, and each lift carries `status`. The facility manager UI must make lift outages one tap to set, and those routes are recalculated or flagged.
- For a step-free route, state the guarantee and the key vertical link in the summary: "Step-free · via Lift B · all doors ≥ 85 cm". If no step-free route exists, say so explicitly and offer to contact staff. Never silently fall back to stairs.
- For screen readers, the step list is an `<ol>` with each step a full sentence. The map canvas is `aria-hidden` or has a short label pointing to the list. Announce step changes in an `aria-live="polite"` region. Applicable WCAG criteria include 1.1.1 non-text content, 1.3.1 info and relationships, 4.1.3 status messages and 2.4.3 focus order [WCAG criteria names: background, unverified this session].
- Colour-blind-safe route: use a single high-contrast route colour (for example a saturated blue or purple with a white casing) that clears 3:1 against floor fills, and distinguish the route by **width and casing as well as hue**. Mark the current position with a shape (dot plus heading cone), not just colour. This follows the 1.4.1 "use of colour" principle [background, unverified].

### Gaps
- No empirical study was found on wheelchair users' indoor route-presentation preferences, and no tested screen-reader map pattern from W3C was retrieved.

## 6. Voice-first UX for hands-busy navigation

### Takeaway
Keep spoken turns short, keyword-like and one action at a time. Allow barge-in ("stop", "repeat", "next") and confirm what was heard before a long route. Always have a visual fallback. Voice works well only for simple, short exchanges.

### Cited Findings
- NN/g (Budiu & Laubheimer, "Intelligent Assistants Have Poor Usability", 17 participants): assistants work only for **very limited, simple queries with short answers** (secondary coverage) — [NN/g video](https://www.nngroup.com/videos/intelligent-assistants-where/); [Boing Boing summary](https://boingboing.net/2018/07/24/sirius-cybernetics-corp.html)
- Haas et al., CHI 2022, "Keep it short" (72 participants): **short keyword-style responses were rated as useful and likeable as full sentences but more efficient**, especially for commands — [Uni Ulm PDF](https://www.uni-ulm.de/fileadmin/website_uni_ulm/iui.inst.100/1-hci/hci-paper/2022/CHI2022_Keep_it_short.pdf)
- Meta Voice SDK guidelines: **barge-in** lets users interrupt to correct errors or redirect. **Confirmation** gives feedback after a command executes — [Meta voice design](https://developers.meta.com/horizon/design/voice/)
- Practitioner guidance (informal): stop TTS immediately on barge-in, with exceptions for critical confirmations. Keep prompts as short as possible while unambiguous. Use **escalating reprompts** (nudge, then example, then help) without repeating identical words. After 2–3 failures, fall back to a visual or human channel — [conversational-ui reference](https://cdn.jsdelivr.net/npm/@hegemonart/get-design-done@1.60.4/reference/conversational-ui.md); [Meta voice SDK overview](https://developers.meta.com/horizon/resources/voice-sdk-design-overview)
- Voice-only navigation matches map performance **if instructions are carefully composed** — [Salzburg Research](https://salzburgresearch.at/?p=14599)

### Inferences
- Turn-taking for the technician:
  1. Confirm the destination: "Compressor room, Hall C. Starting."
  2. Speak one step at a time: "Left at the press."
  3. Wait for "next", "ok" or a positional trigger before the next step.
  4. Support "repeat", "back", "where am I", "how far" and "stop".
- Put the landmark at the end of the phrase for audio ("Turn left… at the press") or use the keyword form. Avoid distances the user can't measure. Avoid reading the whole route aloud; at most give a preview such as "3 steps, about 2 minutes, one lift."
- Confirmation: short echo for destinations, explicit confirm only when ambiguous ("Two 'Lab 3's: Building A or B?").
- Use Web Speech API push-to-talk or a wake button with large hit targets. A noisy factory floor needs an on-screen text echo of every spoken step.

### Gaps
- No indoor-specific voice navigation study on barge-in or step timing was found. Factory-noise ASR accuracy was not researched.

## 7. Onboarding for people who don't know room names

### Takeaway
Lead with a category directory and natural-language "nearest X" search, not a room-number field. Big products open with Directory/category browsing and fuzzy search with aliases, and anchor "you are here" with a QR code at the entrance.

### Cited Findings
- Google Indoor Live View: **Directory button → categories** (gates, restrooms, dining, ATMs …) → Live View — [Google AU blog](https://blog.google/intl/en-au/products/explore-get-answers/indoor-live-view-sydney-airport/)
- Pointr: **fuzzy, misspelling-tolerant search, autocomplete**, multilingual, and search-log analytics — [Pointr](https://pointr.tech/solutions/indoor-navigation)
- MapsPeople: group POIs under **parent categories**, and show **outdoor landmarks** to confirm position — [MapsPeople](https://blog.mapspeople.com/3-tips-to-enhancing-the-user-experience-of-your-indoor-maps)
- Esri Indoors: category groups such as "Places + Things" (restrooms, elevators, ATMs) and landmarks — [Esri](https://doc.esri.com/en/arcgis-pro/latest/help/data/indoors/points-of-interest-and-categories.html)
- Hospital recommendation: **QR codes indoors for positioning**, kiosks at entrances and junctions, and a browser app — [PMC7908200](https://pmc.ncbi.nlm.nih.gov/articles/PMC7908200)
- Campus signage gap: building letters were not linked to department names, which shows the problem of codes without meaning — [PMC7908200](https://pmc.ncbi.nlm.nih.gov/articles/PMC7908200)

### Inferences
- First screen: "Where do you need to go?" with chips for Reception, Toilets, Coffee, Meeting rooms, Exit, First aid, and "Find a person". Show an "I'm at: Main entrance (scanned)" pill. Add a step-free toggle and a mic button.
- Every room record has aliases (functions, people, team names, "the big press"). The agent resolves "nearest coffee" by category plus graph distance from the current location, and answers with the closest option and an alternative.
- If the start location is unknown, ask one question with landmark choices ("What can you see? Reception desk / yellow press / Lift B"), or ask the user to scan the nearest QR sign.

### Gaps
- No usability study comparing category-first and search-first entry for indoor apps was found.
