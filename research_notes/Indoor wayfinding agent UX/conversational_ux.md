# Conversational UX for a task-oriented agent over a building graph (where/route questions + building edits)

Rubric under test: "does it ask only what it needs, show what it understood, give directions a person can follow".

## 1. When to ask a clarifying question vs act on the most likely interpretation

### Takeaway
Ask only when the ambiguity changes the action AND guessing wrong is costly. Otherwise act on the best reading and say what you assumed. LLMs tend to ask too little (they make up missing arguments), but bad or unnecessary questions also hurt satisfaction. Make each question rare, specific, and easy to answer.

### Cited Findings
- CLAM (Kuhn, Gal, Farquhar, ICML 2023) uses a few-shot prompt to (1) decide whether a question is ambiguous, (2) if so, write a clarifying question, then (3) answer. The extra clarifying turn "significantly increases" QA accuracy on ambiguous questions "without affecting unambiguous questions". This is a selective-clarification pattern you can build with prompting alone. — [CLAM, arXiv 2212.07769](https://arxiv.org/abs/2212.07769v2); [OATML summary](https://oatml.cs.ox.ac.uk/publications/20230220_Kuhn_CLAM.html)
- CLAMBER (Zhang et al., ACL 2024): current LLMs have "limited practical utility" at spotting and clarifying ambiguous queries, even with chain-of-thought and few-shot prompting. Ambiguity detection should not be left to the model's free judgment. — [CLAMBER](https://arxiv.org/html/2405.12063v2)
- Value of Information framework (Dong et al., arXiv 2601.06407, Jan 2026): ask only when the expected utility gain from the question outweighs the user's cognitive cost, weighing "task risk, query ambiguity, and user effort". It matches or beats tuned confidence-threshold baselines, and is up to 1.36 utility points better when interruptions are costly. — [arXiv 2601.06407](https://www.arxiv.org/abs/2601.06407)
- ClarifyMT-Bench reports an "under-clarification bias" across ten LLMs that gets worse as the dialogue gets deeper. Related work finds LLM agents fabricate missing tool arguments instead of asking. (Reported via search summary; primary paper not opened.) — [search-surfaced summary, AgentAbstain arXiv 2607.10059](https://arxiv.org/pdf/2607.10059)
- Practitioner guidance (blog, not peer reviewed) names the opposite failure: asking permission for low-stakes, reversible decisions when a sensible default exists. — [Clarification Budgets blog](https://tianpan.co/blog/2026-05-01-clarification-budgets-ask-vs-guess-agent)
- Zou et al. (ACM TOIS 2023, large user study): high-quality clarifying questions improve performance and satisfaction. Low- and mid-quality ones are harmful, and in that case letting users proceed without a question "may be preferred". — [Users Meet Clarifying Questions](https://research.tudelft.nl/en/publications/users-meet-clarifying-questions-toward-a-better-understanding-of-)
- Zou et al. (IPM 2023, 89 participants): an earlier low-quality question suppresses later interaction. The authors conclude "always showing all CQs may be risky". — [Asking Clarifying Questions: to benefit or to disturb users](https://dare.uva.nl/id/2cbf36e0-24e3-4be3-bc5c-01e332c33c9c)
- Evidence on how clarification affects UX is mixed. A Kiesel-line thesis (2018) reports user experience "does not decrease" when the system asks. Ghosh and Shah found the overall search experience degraded with system clarifications. — [Bahrami 2018 thesis](https://downloads-cf.webis.de/theses/papers/bahrami_2018.pdf); conflicting: cited in [Rahmani et al. 2024](https://arxiv.org/pdf/2402.01934)
- Options vs open questions:
  - Alexa: you can read out "up to 5 distinctive, one-word list items without confusing most listeners". Longer items should be read one at a time. Put the most relevant option first, ask for the choice after the options, and accept ordinals, synonyms, and partial names. — [Alexa Haus: Lists pattern](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists)
  - Alexa also says long option lists create high cognitive load. — [Alexa Haus: Be brief](https://developer.amazon.com/alexa/alexa-haus/design-principles/be-brief)
  - The "max 3 options" rule of thumb comes from course notes, not from Amazon. — [course notes](https://leetusman.com/cui_spring2021/week9)
- The UK DfE AI-search redesign found users were overwhelmed and guided them "through a series of questions, asking one at a time". — [DfE design history](https://design-histories.education.gov.uk/find-user-insights/how-we-designed-and-refined-our-ai-search-experience)
- Microsoft HAX G10 "Scope services when in doubt": when uncertain, disambiguate or degrade gracefully rather than act wrongly. — [HAX Toolkit](https://www.microsoft.com/en-us/haxtoolkit/product-category/email/page/6)

### Inferences (implementable rules)
- **R1 Ask-gate (system prompt):** Before every tool call, the agent answers three questions: (a) Does the request map to more than one graph node or action? (b) Would the candidate interpretations produce materially different routes or edits? (c) Is the action an edit, or otherwise irreversible or costly? Ask only if (a) and (b) are both true, or if (a) and (c) are both true. Otherwise act on the top candidate and state the assumption inline ("Taking you to Room 2.14 in the East wing.").
- **R2 Resolve from the graph before asking:** If the graph or context removes the ambiguity, don't ask. For example, only one "Room 214" exists, or the user's current floor or wing makes one candidate nearest. Rank candidates by proximity to the user's location or last-mentioned place.
- **R3 Closed questions with options:** When you must ask, offer 2-4 concrete options taken from the graph (max 5, most likely first). Render them as tappable chips/cards and highlight them on the map. Offer "something else" as an escape. Never ask an open "What do you mean?".
- **R4 One question per turn,** and never more than one clarification round for a where/route query. After that, act on the best guess and label it.
- **R5 Never fabricate:** Never invent a room, edge, or parameter to fill a gap (LLMs show under-clarification and fabrication bias). Missing required edit parameters must be asked or defaulted explicitly.

### Gaps
- No found study gives an optimal number of options for chat UIs (as opposed to voice). The "3" or "5" figures come from voice design.
- Kiesel et al. SIGIR 2018 full text was not verified.

## 2. Grounding and confirmation: showing what the system understood, especially before edits

### Takeaway
Use implicit confirmation by default: weave the resolved entities into the answer. Reserve explicit yes/no confirmation for edits that are hard to undo. For building edits, show a preview or diff on the map before committing, then confirm what changed and offer undo.

### Cited Findings
- Google Conversation Design defines three levels of confirmation:
  - **Explicit:** the user must respond (yes/no). Use it "rarely": when misunderstanding is costly (names, addresses, messages sent on the user's behalf) or the action is hard to undo (deleting data, transactions).
  - **Implicit:** restate what was understood and move on. It is "common" for parameters (e.g. "for 2 people sitting together") and for actions. Acknowledge completed actions unless self-evident, because otherwise users "may not trust that the details were set".
  - **None:** for global commands like stop or cancel, or simple high-confidence input. Don't say "Ok, yes."
  — [Google: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations?hl=en)
- Google: allow one-step corrections ("No, 7 AM"). Let users change any parameter and ask only for the new value rather than restarting the dialog. — [Google: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations?hl=en)
- Microsoft HAX Guidelines for Human-AI Interaction (Amershi et al., CHI 2019) are 18 guidelines grouped into "Initially", "During interaction", "When wrong", and "Over time". — [Microsoft Research project page](https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/); DOI 10.1145/3290605.3300233
- HAX G16 "Convey the consequences of user actions" has these patterns: feedforward (before the action), feedback (immediately after), reminders of past consequential actions. — [HAX Toolkit G16 patterns](https://www.microsoft.com/en-us/haxtoolkit/library/example,pattern/11,16,18/28/)
- HAX G9 "Support efficient correction" has patterns including rich edits, **undoing automated actions**, and batch edits. — [HAX Toolkit](https://www.microsoft.com/en-us/haxtoolkit/library/example,pattern/11,18/28/)
- HAX G11 "Make clear why the system did what it did" and G1/G2 "Make clear what the system can do / how well" (titles from the HAX guideline set). — [HAX Toolkit](https://www.microsoft.com/en-us/haxtoolkit/library/pattern/11,18/)
- Alexa list preambles should "repeat the customer's request, or state an assumption Alexa made". This is implicit confirmation in practice. — [Alexa Haus: Lists](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists)
- Clark & Brennan (1991), "Grounding in Communication": participants work toward mutual belief that an utterance has been understood, with effort set by the cost of misunderstanding and the medium. This is the theoretical basis for graded confirmation. (From prior knowledge; not re-fetched this session.) — [Clark & Brennan 1991, APA](https://psycnet.apa.org/record/1991-98452-006)

### Inferences (implementable rules)
- **R6 Echo resolved entities on every answer:** Name the canonical node (name + floor + wing/ID) and any active constraint, e.g. "Step-free route from Main Entrance to Lab 3.02 (Floor 3)". This is implicit grounding at almost no cost.
- **R7 Edit protocol (preview, confirm, commit, receipt, undo):**
  1. The agent builds a proposed change set (add/remove/rename node or edge, attribute changes).
  2. Render it as a diff: a text summary plus ghosted or colored map overlay (green = added, red = removed, amber = changed).
  3. Ask a single explicit confirmation only if the change is destructive (deletes, merges, bulk edits, or anything that breaks connectivity, such as removing the only accessible route). Otherwise apply it and announce it.
  4. After commit, give a short receipt ("Renamed 'Room 1.05' to 'Quiet Room'. Undo") and keep an undo stack.
- **R8 Feedforward on side-effects:** Before an edit, warn about consequences found from the graph, e.g. "Removing this door makes Room 2.10 unreachable" or "This removes the only step-free path to Floor 2" (HAX G16).
- **R9 Don't over-confirm:** No "Did you mean X?" when the user's words exactly match one node. No echoing "OK, yes".

### Gaps
- No empirical study found comparing preview/diff vs explicit yes/no for LLM-driven structured edits. The rules above extrapolate from HAX and Google guidance.

## 3. Error recovery: nonexistent rooms, misspellings, mid-task changes of mind

### Takeaway
Never just say "not found". Offer the closest real matches as options, escalate help on repeated failure, and let users change one parameter without restarting.

### Cited Findings
- Google No Match handling:
  - **1st attempt:** a brief apology plus a concise re-ask. Don't repeat the prompt verbatim.
  - **2nd attempt:** assume the user is stuck and add options, examples, visual information, or "your best guess".
  - **After 2 failures:** close gracefully and point to another way to finish the task, with no vague promises.
  - **Error caps:** no more than 3 errors in a row. Track error count and type.
  - **System and invalid-request errors:** be transparent, explain why, and offer next steps (e.g. "That date has already passed. Would you like … later this week?").
  — [Google: Errors](https://developers.google.com/assistant/conversation-design/errors)
- Google: support one-step corrections and changing any parameter without restarting the dialog. — [Google: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations?hl=en)
- HAX G9 "Support efficient correction" and G8 "Support efficient dismissal". — [HAX Toolkit](https://www.microsoft.com/en-us/haxtoolkit/library/example,pattern/11,18/28/)
- Alexa: accept selections by ordinal, natural language, synonyms, and partial titles. — [Alexa Haus: Lists](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists)

### Inferences (implementable rules)
- **R10 Fuzzy resolution tool:** Resolve names against node names, aliases, room numbers, and types (e.g. "toilet", "WC", "restroom") with fuzzy matching.
  - **One match above a high threshold:** use it and implicitly confirm the corrected spelling ("Room 2.14 (I read '2.41' as 2.14)", only if it differs).
  - **2-4 plausible matches:** offer them as chips.
  - **No match:** say so plainly, then offer the nearest category matches ("There's no 'Room 9.01'; this building has floors 0-4. Did you mean 0.91 or 1.09?").
- **R11 Room doesn't exist + edit intent:** If the user asks to route to or edit a nonexistent room, distinguish "not in the model" from "misspelled". For edits, offer "Create it?" as an option. Never silently create it.
- **R12 Mid-task change:** Treat "actually, to the cafeteria instead" or "avoid stairs" as a parameter update on the current task. Recompute, re-render the map, and state only what changed ("Updated: now step-free, +40 m"). Don't restart the dialog.
- **R13 Repeated failure:** On the 2nd failure, show a map picker or category list ("tap the room on the map"). Pointing is often easier than naming.

### Gaps
- No LLM-specific study on fuzzy entity resolution UX for indoor maps was found.

## 4. Remembering user constraints (accessibility needs) across turns; privacy

### Takeaway
Keep stated constraints (step-free, avoid stairs, needs elevator) in visible session memory and apply them silently on later turns. Show them as a removable chip so the user can see and change them. Treat disability or health information as sensitive: session-scoped by default, persisted only with explicit consent, and always editable or deletable.

### Cited Findings
- HAX G12 "Remember recent interactions": keep short-term memory so users can refer back efficiently. — [HAX Toolkit search result](https://www.microsoft.com/en-us/haxtoolkit/library/example,pattern/4,11,12,16,18/all/61/)
- HAX G13 "Learn from user behavior" and G17 "Provide global controls" (guideline titles in the HAX set). — [Microsoft Research project page](https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/)
- An audit of ChatGPT memory found over 95% of memories were implicitly extracted without explicit user agency or real-time confirmation. The authors call for consent-driven memory with granular controls. — [arXiv 2609.14697](https://arxiv.org/pdf/2609.14697)
- An interview study (N=40) on LLM memory privacy found low privacy awareness was the main challenge, and proactive privacy control was the most common user need. — [arXiv 2410.14931](https://arxiv.org/html/2410.14931v1)
- Memory lifecycle work flags explicit consent for retention and verifiable deletion as requirements, and calls health categories especially risky. — [arXiv 2609.10413](https://arxiv.org/pdf/2609.10413)
- A practitioner guide: GDPR-style duties (lawful basis, data minimisation, erasure) make consent, visibility, correction, and deletion requirements for memory. — [Nakrani, memory systems guide](https://alpeshnakrani.com/books/memory-systems/privacy-consent-deletion-and-governance/)

### Inferences (implementable rules)
- **R14 Constraint slot:** Store `constraints: {step_free, avoid_stairs, …}` in session state when the user states one. Echo it once ("Got it, I'll keep routes step-free"). Then apply it to every later route without re-asking, and mention it briefly in each route header (implicit confirmation, R6).
- **R15 Visible and removable:** Show active constraints as chips above the chat or map. One tap removes one. The user can also say "stairs are fine now".
- **R16 Don't infer disability:** Record only constraints the user states explicitly. Don't ask why. Keep them session-only unless the user opts in to "remember for next time". Never include them in logs or analytics.
- **R17 Conflict handling:** If no route satisfies a constraint, say so explicitly and offer the least-bad alternative with the violation marked ("No step-free route: the only way is 6 steps at X. Show it anyway?"). This is a case where an explicit question is warranted.

### Gaps
- No disability-specific guidance on AI memory was found. The rules extrapolate from health-data privacy work and GDPR special-category principles.

## 5. Mixed-initiative and multimodal (chat + map) grounding

### Takeaway
The map is a second grounding channel:
- Every entity the agent mentions should be highlighted on the map.
- Every map selection should flow into the chat context.
- Options should appear in both places at once.
Little LLM-specific research exists; the guidance comes from older multimodal-map work and NN/g findings on site-specific chatbots.

### Cited Findings
- NN/g on site-specific chatbots: helpful ones clearly state their capabilities, offer relevant prompt suggestions, and quickly signal they know what users are looking at. Users want quick answers, not conversation. — [NN/g author page summary (Maria Rosala)](https://www.nngroup.com/articles/author/maria-rosala/)
- NN/g diary study (18 participants, 6 conversation types): suggested follow-up prompts are valuable for most conversation types. — [Simon Willison summary of NN/g study](https://www.simonwillison.net/2023/Nov/23/6-types-of-conversations-with-generative-ai)
- IMAIA (2025): an LLM map assistant where users click a map view and converse about it, with answers grounded in text knowledge plus the visual context. — [arXiv 2507.06993](https://arxiv.org/pdf/2507.06993)
- Speech plus pointing on maps ("How far is this town from here?") is an established multimodal deixis pattern. — [Sonntag, DFKI MobileHCI 2007](https://www.dfki.de/~daso02/mobilehci2007.pdf)
- A gesture and speech large-display study: deictic gestures were mainly used to select or locate map objects. The sample was small (n=7). — [arXiv cs/0105026](https://arxiv.org/pdf/cs/0105026)
- Alexa, on screen devices: read little or none of the list aloud, and show the options with a hint of what to say. On-screen and spoken output should complement each other, not duplicate. — [Alexa Haus: Lists](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists)
- HAX G4 "Show contextually relevant information". — [HAX Toolkit (LLM category)](https://www.microsoft.com/en-us/haxtoolkit/application-type/llm/page/9)

### Inferences (implementable rules)
- **R18 Single source of truth:** Chat and map read and write the same state (selected node, candidate set, current route, pending edit diff). Every agent tool result returns node IDs, and the UI highlights them. If the user clicks a node, inject "user selected node X" into the agent context so "take me there" resolves without a question.
- **R19 Clarify in both views:** Clarification options appear as chips in chat and as numbered pins on the map, with matching numbers or colors. Selecting either one resolves the question.
- **R20 Route card:** Show a compact summary card in chat (destination, floor changes, distance or time, active constraints) next to the drawn route. Steps are expandable (progressive disclosure), and tapping a step pans the map to it.
- **R21 Starter chips:** Show 3-4 suggested prompts that reveal capabilities ("Where's the nearest accessible toilet?", "Add a door between…") (HAX G1, NN/g). After an answer, show 2-3 follow-up chips ("Avoid stairs", "Show on floor 2").

### Gaps
- No controlled study found on chat/map synchronization for LLM agents specifically.

## 6. Voice and conversation design guidelines: brevity, progressive disclosure, readback; directions people can follow

### Takeaway
Lead with the answer, keep it brief, chunk long content, and give stepwise directions anchored on landmarks. Use readback (implicit confirmation) for key parameters. For blind or low-vision users, real-time, step-by-step, landmark-rich instructions beat a full route given up front.

### Cited Findings
- Alexa "Be brief": long lists of options create high cognitive load, so use concise language. — [Alexa Haus: Be brief](https://developer.amazon.com/alexa/alexa-haus/design-principles/be-brief)
- Alexa lists:
  - Users have "about 8 seconds" to understand the options, decide, and answer.
  - Paginate long lists, tell users where they are, and support "next / more / go back / repeat".
  - Pause 350-400 ms between spoken items.
  — [Alexa Haus: Lists](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists)
- Alexa voice design guide: don't prompt with a menu of options; tell users what's possible so they can answer naturally. — [Alexa Voice Design Guide](https://developer.amazon.com/fr/designing-for-voice/what-alexa-says/)
- Google: implicitly confirm parameters so the response has context. Explicitly confirm messages or values where errors are costly. — [Google: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations?hl=en)
- Wayfinding research:
  - Verbal descriptions of local geometry are enough for accurate indoor learning and wayfinding, and blindfolded-sighted users did no worse than with visual input. — [Giudice, UMaine VEMI](https://umaine.edu/vemi/publication/wayfinding-without-vision-learning-real-virtual-environments-using-dynamically-updated-verbal-descriptions)
  - Real-time updated instructions supported route guidance better than instructions given only up front. The authors recommend minimizing memory demands. — [UMaine VEMI, Wayfinding with Words](https://umaine.edu/vemi/?p=1114)
  - Adding local landmarks to turn-by-turn instructions improved blind navigators' satisfaction and confidence. Visually impaired people's route recall includes more "milestones". — [White Rose / CHI paper](https://eprints.whiterose.ac.uk/197458/1/acmchi.pdf); [Strathclyde study](https://strathprints.strath.ac.uk/id/eprint/2660)
  - Instructions built from visually impaired people's descriptions led to lower workload, fewer deviations, and faster times for visually impaired participants. — [Strathclyde, wayfinding directions for VI people](https://strathprints.strath.ac.uk/id/eprint/2660)

### Inferences (implementable rules)
- **R22 Answer-first format:** Use one summary line (destination, floor, distance or time, constraint), then numbered steps. Keep it to 7 steps or fewer per screen; collapse or group the rest.
- **R23 Step grammar:** "[Action] [direction] [at landmark] [until landmark]", e.g. "Turn left at the reception desk, then take the lift to Floor 2." Use landmarks and floor changes, not just meters or cardinal directions. Use relative directions (left/right) only when the start orientation is known; otherwise anchor on a landmark ("with the main doors behind you").
- **R24 Progressive disclosure:** Give the full step list on request. Offer "step-by-step mode" (one step at a time with "next / repeat") for voice or low-vision use.
- **R25 Readback before destructive edits only:** Read back the exact change ("Delete the corridor between 2.10 and 2.12?"). For routes, the implicit header suffices.

### Gaps
- Gaunet's (2004) verbal-guidance rules for pedestrians were referenced but not retrieved.
- Apple HIG for Siri was not fetched this session, so no Apple-specific citations are included.

## 7. Evaluation rubrics resembling "asks only what it needs / shows what it understood / directions a person can follow"

### Takeaway
No public rubric found matches this exactly. The closest validated set is Microsoft's 18 HAX guidelines, which map well onto the three rubric clauses. Research on clarification quality (Zou et al.) and on value-of-information supplies the "only what it needs" criterion.

### Cited Findings
- HAX's 18 guidelines were distilled from 150+ (another account says 160+) recommendations and validated in a 4-step process, including user evaluation. They are grouped by Initially / During interaction / When wrong / Over time. — [Microsoft Research](https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/); [VT course summary](https://wordpress.cs.vt.edu/cs6724s20/?p=345)
- Benchmarks for clarification behavior: CLAMBER, AskBench, HumanEvalComm, and ClarifyMT-Bench. Existing studies rarely test whether agents ask *when it matters for the action*. — [AgentAbstain arXiv 2607.10059](https://arxiv.org/pdf/2607.10059); [CLAMBER](https://arxiv.org/html/2405.12063v2)
- Rahmani et al. (2024) define "useful" clarifying questions as those that lead to higher user satisfaction. — [arXiv 2402.01934](https://arxiv.org/pdf/2402.01934)

### Inferences (self-check rubric to use in testing)
- **Asks only what it needs:**
  - % of turns with a clarifying question on unambiguous prompts (target: about 0).
  - % of truly ambiguous prompts where it asked or stated an assumption (target: about 100).
  - Average clarification rounds per task (≤1).
  - No fabricated rooms or edges.
- **Shows what it understood:**
  - Every answer names the resolved node(s) and active constraints.
  - Every mentioned node is highlighted on the map.
  - Every edit shows a diff, a receipt, and undo.
- **Directions a person can follow:**
  - Answer-first summary, numbered landmark-anchored steps, floor changes called out, and constraints honored.
  - Test with someone who has never seen the map.

### Gaps
- No hackathon or industry rubric with this exact wording was found.
- No published scoring scale for "directions a person can follow" for LLM wayfinding agents was found.
- Exact verbatim text of all 18 HAX guidelines could not be extracted this session (PDF not parseable). Titles cited here are those surfaced on HAX Toolkit pages: G1, G4, G8, G9, G10, G11, G12, G16, G17. G13 and G2 are from prior knowledge of the guideline set and should be verified.
