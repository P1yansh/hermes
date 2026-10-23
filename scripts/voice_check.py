#!/usr/bin/env python3
"""
voice_check.py: Deterministic Stylometry & Anti-AI Linter.
Scans blog posts, drafts, and documentation for AI tells, buzzwords, and rhythmic monotony.
Part of the voice-mimic skill.
"""
import sys
import re
from pathlib import Path
import statistics

BANNED_AI_WORDS = [
    "delve", "leverage", "foster", "utilize", "underscore", "illuminate",
    "elucidate", "seamless", "seamlessly", "robust", "testament", "tapestry",
    "beacon", "supercharge", "elevate", "groundbreaking", "game-changing",
    "in today's fast-paced", "not only", "revolutionizing"
]

STANCE_ADVERBIALS = [
    "honestly", "frankly", "crucially", "importantly", "interestingly",
    "notably", "obviously", "clearly"
]

def split_sentences(text: str) -> list[str]:
    # Strip markdown headers, code blocks, images, and links
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^#+\s+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"<[^>]+>", "", text)

    # Split on sentence terminals
    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in raw_sentences if s.strip() and len(s.split()) >= 2]
    return sentences

def analyze_file(file_path: Path):
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    text = file_path.read_text(encoding="utf-8")
    sentences = split_sentences(text)

    if not sentences:
        print("[WARNING] No sentences found to analyze.")
        return

    word_counts = [len(s.split()) for s in sentences]
    mean_len = statistics.mean(word_counts)
    stdev_len = statistics.stdev(word_counts) if len(word_counts) > 1 else 0
    short_sentences = sum(1 for w in word_counts if w <= 6)
    long_sentences = sum(1 for w in word_counts if w >= 28)

    # Check for banned AI vocabulary
    lower_text = text.lower()
    banned_hits = {}
    for word in BANNED_AI_WORDS:
        count = len(re.findall(r"\b" + re.escape(word) + r"\b", lower_text))
        if count > 0:
            banned_hits[word] = count

    # Check for stance adverbial openers
    stance_hits = []
    for s in sentences:
        first_word = s.split()[0].lower().rstrip(",.:;")
        if first_word in STANCE_ADVERBIALS:
            stance_hits.append(s[:60] + "...")

    # Check em dash count
    em_dash_count = text.count("—")

    # Output Report
    print("=" * 65)
    print(f"  VOICE LINTER REPORT: {file_path.name}")
    print("=" * 65)
    print(f"Total Sentences Analyzed : {len(sentences)}")
    print(f"Mean Sentence Length     : {mean_len:.1f} words")
    print(f"Burstiness (Std Dev)     : {stdev_len:.1f} words")
    print(f"Staccato Sentences (<=6w): {short_sentences} ({short_sentences / len(sentences) * 100:.1f}%)")
    print(f"Long Sentences (>=28w)   : {long_sentences} ({long_sentences / len(sentences) * 100:.1f}%)")
    print(f"Em Dashes ('—') Found    : {em_dash_count}")
    print("-" * 65)

    passed = True
    if banned_hits:
        print("[FAIL] Banned AI Buzzwords Detected:")
        for word, count in banned_hits.items():
            print(f"  - '{word}': {count} instance(s)")
        passed = False
    else:
        print("[PASS] Zero banned AI buzzwords.")

    if stance_hits:
        print("\n[FAIL] Stance Adverbials as Sentence Openers:")
        for hit in stance_hits:
            print(f"  - {hit}")
        passed = False
    else:
        print("[PASS] Zero stance adverbial sentence openers.")

    if em_dash_count > 15:
        print(f"\n[WARNING] High Em Dash Density ({em_dash_count} instances). Consider replacing with periods or commas.")

    if stdev_len < 4.0:
        print("\n[WARNING] Low burstiness (rhythmic monotony). Vary sentence lengths.")

    print("=" * 65)
    if passed:
        print("  RESULT: VERIFIED CLEAN (Authentic Human Tone)")
    else:
        print("  RESULT: LINT FAILED (AI tells detected)")
    print("=" * 65)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python voice_check.py <path_to_markdown_file>")
        sys.exit(1)
    analyze_file(Path(sys.argv[1]))
