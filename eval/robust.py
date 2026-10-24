"""L4: does the benchmark path survive wording it has never seen? (The Sunday questions may be phrased
differently.) Gold answers stay valid because only the wording changes.

Variants:
- perturb (offline, deterministic): lower-case, no answer-format suffix, floor synonyms ("floor 2" ->
  "2nd floor" / "level 2"), room mentioned by number only, extra politeness, typo in a type word
- paraphrase (Claude, cached in eval/data/paraphrases_<split>.jsonl): free rewrites that keep every name,
  number and floor, generated once so reruns are comparable

  uv run python -m eval.robust --split dev --variants perturb          # free; rules + LLM parser if key
  uv run --env-file .env python -m eval.robust --split dev --variants paraphrase"""

import argparse
import json
import random
import re
from pathlib import Path

from eval.common import load_questions, score_reply, source_of
from eval.ledger import Ledger
from floorwise.agent.answer import answer_with_trace

DATA_DIR = Path(__file__).parent / "data"
SUFFIX = re.compile(r"\s*Finish with a line .*$", re.S)
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


def perturbations(question: str, rng: random.Random) -> dict[str, str]:
    core = SUFFIX.sub("", question)
    suffix = question[len(core):]
    variants = {
        "lower": question.lower(),
        "no_suffix": core + " End with 'Answer: <value>'.",
        "polite": "Hi! Quick question. " + question.replace("?", ", please?", 1),
    }
    floor = re.search(r"the floor (\d+)", core)
    if floor:
        n = int(floor.group(1))
        variants["floor_ordinal"] = core.replace(floor.group(0), f"the {ORDINAL.get(n, f'{n}th')} floor") + suffix
        variants["floor_level"] = core.replace(floor.group(0), f"level {n}") + suffix
    room = re.search(r"\b([A-Z][a-z]+(?: [a-z]+)*) (\d+\.\d+[A-Z]?) \(", core)
    if room:
        variants["ref_only"] = core.replace(room.group(0), f"room {room.group(2)} (", 1) + suffix
    typo_target = re.search(r"\b(largest|every) ([a-z]{5,})", core)
    if typo_target:
        word = typo_target.group(2)
        i = rng.randrange(1, len(word) - 1)
        typo = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        variants["typo"] = core.replace(typo_target.group(0), f"{typo_target.group(1)} {typo}", 1) + suffix
    return variants


def paraphrases(split: str, items: list) -> dict[str, str]:
    """Cached Claude rewrites: question id -> paraphrase."""
    path = DATA_DIR / f"paraphrases_{split}.jsonl"
    cache = {}
    if path.exists():
        cache = {row["id"]: row["text"] for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
    missing = [q for _, q in items if q["id"] not in cache]
    if missing:
        import anthropic

        client = anthropic.Anthropic()
        DATA_DIR.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for question in missing:
                response = client.messages.create(
                    model="claude-sonnet-5-5", max_tokens=2000, output_config={"effort": "low"},
                    messages=[{"role": "user", "content": (
                        "Rewrite this question the way a real person in the building might ask it. Keep every room "
                        "name, room number, floor, item, width and constraint exactly; change everything else "
                        "(order, wording, tone). Keep the final instruction about the 'Answer:' line. Reply with "
                        f"the rewritten question only.\n\n{question['question']}")}],
                )
                text = "".join(b.text for b in response.content if b.type == "text").strip()
                cache[question["id"]] = text
                handle.write(json.dumps({"id": question["id"], "text": text}, ensure_ascii=False) + "\n")
    return cache


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.robust")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--variants", default="perturb", choices=["perturb", "paraphrase"])
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("-v", "--verbose", action="store_true")
    args = cli.parse_args()
    items = load_questions([args.split])[: args.limit]
    ledger = Ledger("robust", {"split": args.split, "variants": args.variants}, name=args.variants)
    rng = random.Random(5)
    rewritten = paraphrases(args.split, items) if args.variants == "paraphrase" else {}
    for directory, question in items:
        variants = perturbations(question["question"], rng) if args.variants == "perturb" else {"paraphrase": rewritten[question["id"]]}
        for name, text in variants.items():
            reply, trace = answer_with_trace(directory, text)
            ledger.add_usage(trace.get("usage", {}))
            ok = score_reply(question["answer"], reply)
            ledger.record(id=f"{question['id']}:{name}", kind=name, source=source_of(question["building_id"]), building=question["building_id"], correct=ok,
                          parser=trace.get("parser"), fallback=trace.get("fallback"), text=text, reply=reply[-200:])
            if not ok and args.verbose:
                print("BAD", question["id"], name, trace.get("parser"), trace.get("fallback"), "|", text[:140])
    summary = ledger.finish()
    parsers = {}
    for row in ledger.rows:
        parsers[row.get("parser")] = parsers.get(row.get("parser"), 0) + 1
    print("  parser used:", parsers)


if __name__ == "__main__":
    main()
