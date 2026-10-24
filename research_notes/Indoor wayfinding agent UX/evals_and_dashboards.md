# Evaluation Harness Design for LLM Agents and Benchmark/Eval Admin Dashboards

Context: indoor navigation agent = deterministic route solver + LLM parser/chat. Gold answers exist for train/dev, none for test. A hidden "Sunday" building is used for final scoring. Conversational quality is graded by humans against a rubric.

## LLM-as-a-judge reliability for multi-turn conversational agents

### Takeaway
Strong LLM judges can match human-human agreement (~80-85% on non-tie pairwise votes), but they show measurable position, verbosity, and self-preference biases. They must be calibrated against a human expert's binary labels on a held-out split, with TPR/TNR reported separately, before anyone trusts them. Rubric-based absolute grading works when a reference answer and an explicit rubric are supplied. Pairwise grading with position swapping is more robust for A/B comparisons.

### Cited Findings
- **MT-Bench / Chatbot Arena agreement:** GPT-4 pairwise judge vs. humans reaches 85% agreement on non-tie votes, versus 81% for human vs. human. Including ties, the figures are 66% (GPT-4-human) vs. 63% (human-human), against a 33% random baseline. — [Zheng et al. 2023, Judging LLM-as-a-Judge](https://arxiv.org/html/2306.05685v4)
- **Single-answer vs. pairwise grading:** GPT-4 single-answer grading and pairwise grading agree with each other 97% of the time. Single-answer grading agrees less with humans once ties are included (60% vs. 66%). — [Zheng et al. 2023](https://arxiv.org/html/2306.05685v4)
- **Position bias:** Under the default prompt, swap consistency was GPT-4 65.0% (30% biased toward the first position), GPT-3.5 46.2%, and Claude-v1 23.8% (75% biased toward the first position). — [Zheng et al. 2023](https://arxiv.org/html/2306.05685v4)
- **Verbosity bias:** A "repetitive list" attack fooled Claude-v1 and GPT-3.5 91.3% of the time and GPT-4 8.7% of the time. — [Zheng et al. 2023](https://arxiv.org/html/2306.05685v4)
- **Self-enhancement bias:** GPT-4 rated its own win rate about 10% higher than humans did, and Claude-v1 about 25% higher. The authors say their data was too limited to confirm the bias conclusively. — [Zheng et al. 2023](https://arxiv.org/html/2306.05685v4)
- **Mitigations:**
  - Swap the two positions and count a win only if it holds in both orders (otherwise call it a tie).
  - Few-shot judging raised GPT-4's consistency from 65.0% to 77.5%.
  - On math questions, the judge failure rate fell from 70% (default prompt) to 30% with chain-of-thought and to 15% with reference-guided judging.
  - Humans found GPT-4's judgments reasonable in 75% of the cases where it disagreed with them.

  — [Zheng et al. 2023](https://arxiv.org/html/2306.05685v4)
- **G-Eval:** Chain-of-thought plus a form-filling paradigm reached a Spearman correlation of 0.514 with humans on summarization. — [G-Eval, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.153); per-dimension and ablation numbers (for example, CoT removed → 0.500) come only from secondary blogs and are unverified: [cekura](https://www.cekura.ai/discover/g-eval), [Galileo](https://galileo.ai/blog/g-eval-metric)
- **Prometheus:** A 13B evaluator reached Pearson 0.897 with humans on 45 custom rubrics, vs. GPT-4 at 0.882 and ChatGPT at 0.392. Its parity with GPT-4 depends on supplying both the score rubric and a reference answer. — [Prometheus, arXiv 2310.08491](https://arxiv.org/abs/2310.08491v2)
- **Prometheus ablation (unverified):** One secondary summary reports that removing the reference answer is the largest ablation drop (0.847 → 0.626). — [HF discussion](https://huggingface.co/datasets/rl-llm-wiki/knowledge-base/discussions/218)
- **Multiple judges (PoLL):** A panel of three smaller models from disjoint families beat a single GPT-4 judge across 3 judge settings and 6 datasets. It reduced intra-model (self-preference) bias and was about 7-8x cheaper. These are the authors' own claims, and I found no independent replication. — [Verga et al. 2024, Replacing Judges with Juries](https://arxiv.org/abs/2404.18796v2)
- **Rubric design (Hamel Husain):**
  - Use binary pass/fail judgments by one "principal domain expert", each with a written critique. "Being too terse is a common mistake."
  - Avoid 1-5 scales and multi-metric dashboards.
  - The expert critiques become few-shot examples in the judge prompt.
  - In the Honeycomb case, hand iteration reached >90% agreement in three iterations.

  — [Hamel Husain, Creating a LLM-as-a-Judge That Drives Business Results](https://hamel.dev/blog/posts/llm-judge/)
- **Judge validation metrics:** Report True Positive Rate and True Negative Rate separately, because raw agreement misleads on imbalanced data. For example, an always-Pass judge scores 95% agreement when 5% of cases fail. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- **Splits for the judge prompt itself:**
  - Train: 10-20% of labeled data, used as few-shot examples.
  - Dev: about 40-45%, used for iteration.
  - Test: about 40-45%, run once after the prompt is frozen.
  - Aim for 30-50 examples per label in each of dev and test.
  - Aim for about 100 examples per failure mode. "Below 60 examples, the confidence intervals are often too wide."

  — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- **Anthropic guidance on graders:**
  - Model graders are "non-deterministic" and require "calibration with human graders".
  - Give the judge an escape hatch (return "Unknown").
  - Grade each rubric dimension with a separate judge.
  - Prefer deterministic graders, use LLM graders where needed, and use humans sparingly for validation.

  — [Anthropic, Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Multi-turn agents:** Anthropic recommends combining state checks on the outcome, transcript constraints (such as turn limits), and LLM rubrics for interaction quality. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Inferences
- **Route correctness:** The deterministic solver output (route, destination, accessibility constraints) should be graded with code, never with a judge. LLM judges should cover only the conversational-quality dimensions of the human rubric.
- **One judge per dimension:** Each human-rubric dimension should get its own binary judge (for example "asked a clarifying question when the destination was ambiguous" or "did not invent rooms"). Each judge is validated against the humans' labels with TPR/TNR on a frozen test split.
- **Pairwise judging for A/B:** When comparing two agent versions, pairwise judging with both orderings (a tie unless the preference holds in both) is the bias-mitigated choice.
- **Multiple judges:** A small cross-family panel is a cheap hedge against self-preference when the agent and the judge come from the same model family.

### Gaps
- No direct numbers were found on LLM-judge agreement specifically for multi-turn task-oriented dialogue quality (MT-Bench covers only two turns). The tau-bench paper uses state-based checks, not judges.
- The G-Eval per-dimension and ablation figures were not verified against the primary PDF.
- No independent replication of PoLL was found.

## User simulators for evaluating task-oriented agents

### Takeaway
tau-bench pairs an LLM-simulated user with a tool-using agent and grades the final database state against an annotated goal state. It reports pass^k to measure consistency. Recent work with real humans shows LLM user simulators are too cooperative and too uniform, which inflates agent success. Simulated users therefore need adversarial personas and periodic validation against real humans.

### Cited Findings
- **tau-bench design:** An LM simulates the user in dynamic conversations with an agent that has domain API tools and policy guidelines. Evaluation compares the end database state with an annotated goal state. gpt-4o succeeds on under 50% of tasks, and its pass^8 is below 25% in the retail domain. — [Yao et al. 2024, tau-bench](https://export.arxiv.org/abs/2406.12045); [Sierra blog](https://sierra.ai/blog/benchmarking-ai-agents)
- **pass@k vs. pass^k:** pass^k is the probability that all k trials succeed, and pass@k the probability that at least one does. With a 75% per-trial success rate, pass^3 ≈ 42%. Use pass^k for customer-facing agents that need consistency. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Sim2Real gap:** The full tau-bench protocol was run with 451 real humans and compared against 31 LLM simulators. The simulators were excessively cooperative and stylistically uniform, and lacked realistic frustration and ambiguity. This creates an "easy mode" that inflates agent success above the human baseline. Higher general model capability did not yield more faithful simulation. — [arXiv 2603.11245](https://arxiv.org/html/2603.11245v1) (read via search summary only, not full text)
- **ConvApparel:** Found a significant realism gap across all simulators. Data-driven simulators beat prompted ones, especially under counterfactual validation. — [ConvApparel, arXiv 2602.16938](https://arxiv.org/html/2602.16938v1)
- **MirrorBench:** Argues that user-proxy agents must be evaluated for human-likeness separately from task completion. — [MirrorBench, arXiv 2601.08118](https://arxiv.org/html/2601.08118v1)
- **Prompt-based simulators:** Prompt-based LLM simulators beat rule-based ones on goal fulfillment but produce stilted conversations. — [arXiv 2309.13233](https://arxiv.org/pdf/2309.13233)
- **Multi-turn evals need a second LLM:** Multi-turn evals "often require a second LLM to simulate the user". — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Synthetic data structure:** Synthetic data should be structured by dimensions (features × scenarios × personas). Only the inputs should be synthetic, and the responses must come from the real system. Keep generating until no new failure modes appear. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)

### Inferences
- **Simulator personas:** For wayfinding, personas should include:
  - an ambiguous destination ("the cafe" when there are two)
  - mid-dialogue goal change
  - accessibility needs (wheelchair, no stairs)
  - wrong or partial room names and typos
  - a terse user
  - a frustrated or non-cooperative user
  - non-native phrasing
  - out-of-scope requests

  This counters the "too cooperative" bias.
- **Scoring:** Simulated users should carry a hidden goal (target room plus constraints). Success is computed on the final resolved route by the solver, using state-based grading as in tau-bench, not by a judge. Report pass^k (for example k=4) to expose parser nondeterminism.
- **Validate the simulator:** Have a human play a sample of the same scenarios, then compare the success-rate gap.

### Gaps
- I read only the abstracts and summaries of the 2026 simulator-realism papers. Their exact metrics should be verified.
- No wayfinding-specific simulator literature was found.

## Benchmark hygiene: splits, contamination, metamorphic/property testing, statistics, CI gates

### Takeaway
Treat evals as experiments:
- Report standard errors, using clustered SEs when items share a source (here, a building).
- Hold out whole groups (buildings).
- Freeze the test split and touch it once.
- Use metamorphic and paraphrase invariance tests where gold is absent.
- Gate CI on regression suites that sit near 100%, with thresholds rather than all-or-nothing for stochastic graders.

### Cited Findings
- **Standard errors:** Report the standard error of the mean with each score, and a 95% CI of ±1.96·SE. When questions are clustered (several questions per passage), use cluster-robust SEs, because assuming independence understates error. The paper also gives formulas for comparing two models and for planning eval size. — [Miller 2024, Adding Error Bars to Evals (Anthropic)](https://www.anthropic.com/research/statistical-approach-to-model-evals); [arXiv 2411.00640](https://arxiv.org/pdf/2411.00640)
- **Small-sample judge validation:** "Below 60 examples, the confidence intervals are often too wide to support a useful conclusion." — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- **Capability vs. regression evals:**
  - Capability evals start at a low pass rate.
  - Regression evals should sit near 100%, and capability tasks graduate into them.
  - "An eval at 100% tracks regressions but provides no signal for improvement."
  - Start with "20-50 simple tasks drawn from real failures."
  - Balance positive and negative cases: "One-sided evals create one-sided optimization."
  - Isolate trials in clean environments, grade outcomes rather than paths, and guard against bypasses.
  - If a 0% pass rate persists, suspect the task.

  — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Error analysis first:** Before building metrics, read real outputs, group failures into named categories, and prioritize by frequency. Write a test case for each fixed error. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/); [Lenny's Newsletter summary](https://www.lennysnewsletter.com/p/evals-error-analysis-and-better-prompts)
- **Metamorphic testing:**
  - It exposes faulty behavior without explicit oracles (labels).
  - One catalogue lists 191 metamorphic relations for NLP tasks, 36 of which were implemented and run as about 560K tests across 3 LLMs. — [Cho, Ruberto, Terragni, arXiv 2511.02108](https://www.arxiv.org/pdf/2511.02108)
  - On agent reasoning, a study used 8 semantic-preserving transformations including paraphrase. Model scale did not predict robustness: the best model had 79.6% invariant responses. — [arXiv 2603.13173](https://arxiv.org/abs/2603.13173)
- **Promptfoo in CI:** The official GitHub Action (`promptfoo/promptfoo-action`) runs before/after evals on PRs that change prompts and posts the comparison as a PR comment. Model-graded assertions are non-deterministic, so use pass-rate thresholds rather than demanding 100%. — [promptfoo GitHub](https://github.com/promptfoo/promptfoo); [Medium: regression evals in CI with promptfoo](https://medium.com/@alexrodriguesj/testing-llm-prompts-like-code-regression-evals-in-ci-cd-with-promptfoo-5242b4dcb9be)
- **Phoenix dataset splits and versioning:** Phoenix supports dataset splits (train/validation/test). Every experiment pins a dataset version, and examples track their source spans. — [Phoenix splits release note](https://arize.com/docs/phoenix/release-notes/10-2025/10-20-2025-splits); [Phoenix experiments](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments)

### Inferences
- **Group-held-out splits:** Split by building, never by query. All queries from a building belong to one split, which mimics the hidden "Sunday" building. Use leave-one-building-out cross-validation over train+dev to estimate generalization to an unseen building.
- **Clustered SEs:** Compute cluster-robust SEs with building (or floor) as the cluster. With few buildings, these CIs will be wide, and the dashboard should show that honestly.
- **Test split with no gold:** For the test split, use oracle-free checks:
  - **Metamorphic relations:**
    - Paraphrasing the request must yield the same parsed destination and constraints.
    - Swapping origin and destination yields the reverse route with equal cost on undirected graphs.
    - Adding "avoid stairs" never produces a route with stairs.
    - Renaming a room label consistently should not change the route topology.
    - Adding an irrelevant clause should not change the parse.
  - **Property-based tests on the solver:**
    - The route is connected.
    - It starts and ends at the right nodes.
    - It respects accessibility flags.
    - Its cost is ≤ any random valid path.
    - It is deterministic for identical inputs.

  These checks are my design proposals based on the metamorphic-testing literature above, not taken from a specific source.
- **Anti-overfitting:** Freeze the dev set after rubric creation and log every test-split touch in the dashboard. Keep a "never seen" adversarial paraphrase set generated after the prompt freeze.
- **CI gates:**
  - The regression suite (solver properties plus parser exact-match on canonical cases) must be at or near 100% to merge.
  - Stochastic LLM metrics gate on "not significantly worse than baseline", using paired per-item differences and SE, rather than on an absolute value.

### Gaps
- No source was found on contamination specific to custom/private benchmarks. The general principle is to keep hidden-building data out of prompts, few-shot examples, and retrieval indices.
- I did not verify the exact paired-difference and power-analysis formulas in Miller 2024 beyond the summary; consult arXiv 2411.00640.

## What views developers need in eval dashboards (tool survey)

### Takeaway
The recurring core across tools:
- a run list with summary metrics
- per-sample drill-down showing the full transcript, tool calls, scorer explanation, and metadata
- filter/sort by score and metadata
- baseline-vs-candidate comparison with per-row deltas, sorted by regression, with text diff
- grouping across repeated epochs to see inconsistency
- dataset versioning and splits
- cost, latency, and token tracking
- human annotation queues (single and pairwise) feeding judge calibration

### Cited Findings
- **Inspect AI (UK AISI) log viewer:**
  - A main view with the results summary and sample list. Each sample drills into Messages (the full history, including tool calls), Scoring (input, target, extracted answer, scorer explanation), and Metadata (data recorded by solvers, tools, and scorers).
  - An Info panel with dataset, solver, scorer, git revision, and token usage.
  - An answers column to spot scorer extraction failures.
  - A filter by score (for example, Incorrect only).
  - Sorting by sample to group results across epochs and reveal inconsistency.
  - Log history, a live view during runs, and a static bundle for hosting.
  - Cross-run comparison is pushed to the EvalLog API and dataframes rather than the viewer.

  — [Inspect log viewer docs](https://inspect.aisi.org.uk/log-viewer.html)
- **Braintrust:**
  - Set a baseline experiment and align test cases across runs. Each row gets a score delta, green for improvement and red for regression.
  - "Sort by regressions" surfaces the most affected test cases.
  - A diff mode shows base→comparison, comparison→base, or expected→output, with character-level diffs in the detail panel.
  - An aggregate layout shows overall improvement.
  - Human pairwise preferences per row appear as a Pairwise score (average or wins/losses).

  — [Braintrust compare experiments docs](https://www.braintrust.dev/docs/evaluate/compare-experiments)
- **LangSmith annotation queues:**
  - Single-run queues show one run or thread at a time, optionally with assertions.
  - Pairwise annotation queues show two runs side by side for reviewers to pick the better one (or mark them equivalent) against defined rubric items.
  - You can select two experiments and send them to a pairwise queue, with automatic pairing and reviewer assignment.

  — [LangSmith annotation queues docs](https://docs.langchain.com/langsmith/annotation-queues); [changelog](https://changelog.langchain.com/announcements/ann_IO03AUm0nvBuO)
- **Arize Phoenix:** Datasets of examples (inputs plus optional reference outputs), linked to their source spans. Dataset versioning, with every experiment tracking its version. Experiments record latency, error rate, cost, and scores. Supports repetitions, splits, and annotations/feedback on spans. — [Phoenix experiments docs](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments); [splits](https://arize.com/docs/phoenix/release-notes/10-2025/10-20-2025-splits); [client package](https://arize.com/docs/phoenix/release-notes/08-2025/08-28-2025-new-arize-phoenix-client-package)
- **Promptfoo:** Before/after comparison posted to the PR, with a link to a web viewer. — [promptfoo GitHub](https://github.com/promptfoo/promptfoo)
- **Data viewer design:** Remove friction. A simple custom web app beats a spreadsheet. Put all context on one screen: user metadata, system state, and tools to verify correctness. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- **Read transcripts:** They distinguish real agent failures from a grader rejecting valid solutions. "Failures should seem fair." — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Inferences — Concrete admin panel ("Benchmark Lab") feature list
1. **Runs table:**
   - Columns: run id, git SHA, model/prompt version, split, timestamp, headline metrics with 95% CI (clustered by building), pass^k, cost, latency p50/p95, and tokens.
   - Pattern from [Inspect](https://inspect.aisi.org.uk/log-viewer.html) and [Phoenix](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments); CIs per [Miller 2024](https://www.anthropic.com/research/statistical-approach-to-model-evals).
2. **Run comparison (baseline vs. candidate):**
   - Per-item deltas colored green/red, sort by regression, and a paired-difference summary with SE and significance.
   - Text diff for the parser JSON and chat replies, and a route diff (highlight changed segments on the floor map).
   - Pattern from [Braintrust](https://www.braintrust.dev/docs/evaluate/compare-experiments).
3. **Per-sample drill-down:**
   - Chat transcript, the parser's structured output vs. gold, solver input/output, and the route rendered on the floorplan.
   - Every judge verdict with its rationale, metamorphic-variant results, and metadata.
   - Everything on one screen, per [Inspect](https://inspect.aisi.org.uk/log-viewer.html) and [Hamel](https://hamel.dev/blog/posts/llm-judge/).
4. **Epoch/consistency view:** Group the k trials of the same item, flag items with mixed outcomes, and show pass^k. Sources: [Inspect](https://inspect.aisi.org.uk/log-viewer.html), [tau-bench](https://export.arxiv.org/abs/2406.12045).
5. **Slicing:**
   - Filter and group by building, floor, query type (room / amenity / person / ambiguous), persona, accessibility constraint, language/paraphrase family, split, and failure category.
   - A per-slice metrics table with CIs.
   - Pattern from [Inspect](https://inspect.aisi.org.uk/log-viewer.html) score filter and [Phoenix](https://arize.com/docs/phoenix/release-notes/10-2025/10-20-2025-splits) splits; the slice dimensions are my proposal.
6. **Failure taxonomy / clustering:**
   - Open-code failures with free-text notes, then roll them up into named categories with frequency counts to prioritize fixes.
   - Per [Hamel](https://hamel.dev/blog/posts/llm-judge/) and the [Lenny's summary](https://www.lennysnewsletter.com/p/evals-error-analysis-and-better-prompts).
   - Automated embedding clustering is optional; I found no verified source for it in these tools (see Gaps).
7. **Annotation queues:**
   - Single-item binary pass/fail with a required critique, per rubric dimension.
   - Pairwise A/B queue (both orders, blinded to version) for conversational quality.
   - Reviewer assignment, with labels feeding judge calibration.
   - Sources: [LangSmith](https://docs.langchain.com/langsmith/annotation-queues), [Hamel](https://hamel.dev/blog/posts/llm-judge/).
8. **Judge calibration page:**
   - For each judge, TPR/TNR vs. human labels on the dev and frozen test splits, with CI and sample counts.
   - A confusion matrix, a list of disagreements to inspect, and the judge prompt version history.
   - Sources: [Hamel](https://hamel.dev/blog/posts/llm-judge/), [Zheng et al.](https://arxiv.org/html/2306.05685v4).
9. **Dataset manager:**
   - Versioned datasets with split labels (train/dev/test) locked by building.
   - Provenance (real, synthetic, or a metamorphic variant of item X), and a "promote failing production case to test" action.
   - Source: [Phoenix](https://arize.com/docs/phoenix/release-notes/10-2025/10-20-2025-splits).
10. **Test-split access log / holdout guard:** The test (and hidden-building) score is revealed only on explicit request, and every reveal is logged with a counter. This is a design proposal motivated by Hamel's "run test once after freezing" advice ([Hamel](https://hamel.dev/blog/posts/llm-judge/)).
11. **Suite health:**
    - Capability vs. regression suites.
    - Saturation warning when a suite is at 100%.
    - Flags for items failing 0/k for all versions ("suspect the task").
    - Balance of positive and negative cases.
    - Source: [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
12. **CI integration:** A PR comment with the before/after summary linking to the comparison view, and gate status. Pattern from [promptfoo](https://github.com/promptfoo/promptfoo).
13. **Live run view:** Streaming results and incremental metrics while a run executes. Source: [Inspect](https://inspect.aisi.org.uk/log-viewer.html).

### Gaps
- I did not fetch docs for OpenAI Evals, W&B Weave, or HELM, nor Phoenix's embedding/UMAP clustering features, so feature claims about them are omitted. Failure clustering via embeddings is therefore unsourced here.
- No user studies were found on which dashboard views developers actually use most. The list above is a convergence of tool features plus practitioner advice, not empirical usage data.

## Concrete eval harness protocol (synthesis)

### Takeaway
This is a layered protocol:
- deterministic code graders for the solver and parser
- state-based success for simulated multi-turn dialogues
- calibrated binary LLM judges per rubric dimension
- humans as the gold standard for conversational quality

All of it uses building-level held-out splits, clustered CIs, pass^k, metamorphic tests where gold is missing, and CI regression gates.

### Cited Findings
- Prefer code graders, use LLM graders where needed, and keep humans for calibration; combine outcome state checks, transcript constraints, and rubric judges for multi-turn agents. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- State-based goal checking with LLM-simulated users, plus pass^k. — [tau-bench](https://export.arxiv.org/abs/2406.12045)
- Judge calibration protocol: binary labels plus critiques, train/dev/test splits for the judge, TPR/TNR. — [Hamel Husain](https://hamel.dev/blog/posts/llm-judge/)
- Clustered standard errors and CIs. — [Miller 2024](https://www.anthropic.com/research/statistical-approach-to-model-evals)
- Pairwise grading with swapped positions, and reference-guided judging. — [Zheng et al. 2023](https://arxiv.org/html/2306.05685v4); [Prometheus](https://arxiv.org/abs/2310.08491v2)
- Cross-family judge panels. — [PoLL](https://arxiv.org/abs/2404.18796v2)

### Inferences — Protocol steps
1. **Splits:**
   - Partition by building: train buildings, dev buildings, and test buildings without gold.
   - Simulate "Sunday" with leave-one-building-out over train+dev.
   - Never put test/hidden-building strings in prompts, few-shot examples, or synonym tables.
2. **Layer A, solver (code):** Property-based tests (connectivity, endpoints, accessibility compliance, optimality vs. brute force on small graphs, determinism) run on every commit. Gate at 100%.
3. **Layer B, parser (code):**
   - Field-level exact match of the structured parse vs. gold on train/dev (destination id, origin, constraints), reported per field.
   - On test (no gold), run metamorphic invariance: paraphrases, typos, irrelevant clauses, and synonym swaps must yield an identical parse.
   - Report the invariance rate.
4. **Layer C, end-to-end dialogue:**
   - Simulated users with hidden goals and diverse/adversarial personas, k≥3 trials per scenario.
   - Success = the final route equals the gold route (or satisfies the goal constraints).
   - Report pass^1 and pass^k, the number of turns, and clarification rate where clarification was needed vs. where it was not.
5. **Layer D, conversational quality:**
   - Humans grade a stratified sample with the rubric, as binary per-dimension labels plus critiques.
   - Build one LLM judge per dimension, using critiques as few-shot examples. Validate TPR/TNR on a frozen held-out set (target ≥ about 50 labels per class).
   - Use a cross-family judge or panel. For A/B, use pairwise judging in both orders.
   - Re-calibrate whenever the judge model or prompt changes.
6. **Statistics:**
   - Report mean ± 1.96·clustered-SE (cluster = building).
   - Compare versions with paired per-item differences.
   - Do not claim improvements whose CI includes 0.
7. **CI gates:** Regression suite (A + B canonical cases) = 100%; the E2E pass rate must be not significantly below baseline; the judge-metric drop must stay within the CI. Post a summary to the PR.
8. **Hygiene loop:**
   - Do error analysis after each run, add the failing cases to dev (never to test), and graduate saturated capability tasks into the regression suite.
   - Spot-check the simulator against real humans.
   - Log every test-split evaluation.

### Gaps
- No source specifically validates this layering for indoor navigation agents. It is a synthesis of the general sources above.
- The recommended k, sample sizes per building, and number of buildings needed for meaningful clustered CIs were not found and should be set by a power analysis (see [Miller 2024](https://arxiv.org/pdf/2411.00640)).
