"""Basic completion check for one finished Chinese text stage."""

import json
import re
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COUNTS = (200, 400, 600, 800, 1000, 1000, 1200, 1800, 1800, 1200)
REQUIRED = {
    "schema_version", "id", "locale", "sentence", "cloze", "answer",
    "accepted_answers", "lemma", "meaning", "part_of_speech",
}
SUPPORT = {"target_pinyin", "pronunciation_note", "usage_note", "idiom_support", "recognition"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def length(text):
    return sum(not ch.isspace() for ch in unicodedata.normalize("NFC", text))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def check(stage):
    require(re.fullmatch(r"0[0-9]", stage), "Expected stage 00–09")
    count = COUNTS[int(stage)]
    cards = json.loads((ROOT / "cards" / "zh-Hans-CN" / f"{stage}.json").read_text())
    require(isinstance(cards, list) and len(cards) == count, "Wrong stage count")
    expected = [f"zh-{stage}-{i:04d}" for i in range(1, count + 1)]
    seen_ids, seen_sentences = set(), set()
    for earlier in range(int(stage)):
        path = ROOT / "cards" / "zh-Hans-CN" / f"{earlier:02d}.json"
        for card in json.loads(path.read_text()):
            seen_ids.add(card["common"]["id"])
            seen_sentences.add(card["common"]["sentence"])
    cap = 18 if int(stage) <= 1 else 26 if stage == "02" else 40
    for expected_id, card in zip(expected, cards):
        require(isinstance(card, dict) and set(card) == {"common", "language_specific"}, expected_id)
        common, support = card["common"], card["language_specific"]
        require(isinstance(common, dict) and REQUIRED <= common.keys(), f"{expected_id}: required fields")
        require(set(common) <= REQUIRED | {"register", "note"}, f"{expected_id}: unknown common field")
        require(type(common["schema_version"]) is int and common["schema_version"] == 2, expected_id)
        require(common["id"] == expected_id and common["locale"] == "zh-Hans-CN", expected_id)
        require(all(nonempty(v) for k, v in common.items() if k not in {"schema_version", "accepted_answers"}), expected_id)
        variants = common["accepted_answers"]
        require(isinstance(variants, list) and all(nonempty(v) for v in variants), expected_id)
        require(len(set(variants)) == len(variants), f"{expected_id}: repeated variants")
        sentence, cloze = common["sentence"], common["cloze"]
        require(cloze == common["answer"] and sentence.count(cloze) == 1, f"{expected_id}: cloze alignment")
        require(length(sentence) <= cap, f"{expected_id}: sentence cap")
        require(all(0 < length(v) <= 8 for v in [cloze, *variants]), f"{expected_id}: answer cap")
        require(expected_id not in seen_ids and sentence not in seen_sentences, f"{expected_id}: duplicate")
        seen_ids.add(expected_id)
        seen_sentences.add(sentence)
        require(isinstance(support, dict) and set(support) <= SUPPORT, f"{expected_id}: support keys")
        require(nonempty(support.get("target_pinyin")), f"{expected_id}: target Pinyin")
        for key, value in support.items():
            if key in {"idiom_support", "recognition"}:
                keys = {"literal", "contemporary", "collocations", "register", "avoid"} if key == "idiom_support" else {"variety", "explanation", "form"}
                require(isinstance(value, dict) and set(value) == keys and all(nonempty(v) for v in value.values()), f"{expected_id}: {key}")
            else:
                require(nonempty(value), f"{expected_id}: {key}")
        strings = json.dumps(card, ensure_ascii=False)
        require(unicodedata.normalize("NFC", strings) == strings, f"{expected_id}: NFC")
        require(not unicodedata.combining(cloze[0]), f"{expected_id}: cloze boundary")

    text = (ROOT / "coverage" / "zh-Hans-CN" / f"{stage}.md").read_text()
    rows, blocks = [], {}
    for line in text.splitlines():
        columns = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(columns) == 3 and re.fullmatch(r"zh-\d{2}-\d{4}", columns[0]):
            require(all(columns), "Empty coverage cell")
            rows.append(columns)
        if len(columns) == 5 and re.fullmatch(rf"{stage}-[A-Z]+", columns[0]):
            match = re.fullmatch(rf"zh-{stage}-(\d{{4}})–zh-{stage}-(\d{{4}})", columns[4])
            require(match and columns[0] not in blocks, "Invalid coverage block")
            first, last = map(int, match.groups())
            require(last - first + 1 == int(columns[3]), "Wrong block count")
            blocks[columns[0]] = set(expected[first - 1:last])
    require([row[0] for row in rows] == expected, "Coverage must match every ordered card")
    require(sum(map(len, blocks.values())) == count, "Block allocations must total the stage")
    require(set().union(*blocks.values()) == set(expected), "Block ranges must cover the stage")
    for card_id, block, _ in rows:
        require(card_id in blocks.get(block, set()), f"{card_id}: block mismatch")
    print(f"PASS: stage {stage}, {count} cards and matching coverage; fields, IDs, clozes, caps and duplicates checked.")


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2, "Usage: ./.venv/bin/python scripts/check_content.py NN")
        check(sys.argv[1])
    except (ValueError, KeyError, TypeError, OSError) as error:
        sys.exit(f"FAIL: {error}")
