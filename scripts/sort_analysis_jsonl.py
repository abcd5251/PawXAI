#!/usr/bin/env python3
"""
Sort analysis_results.jsonl by kolFollowersCount (descending) and reorder fields.

Output format per item:
1) username
2) followersCount
3) friendsCount
4) kolFollowersCount (sort key, descending)
5) description
6) location
7) website
8) language_tags, ecosystem_tags, user_type_tags, MBTI
9) summary
10) Any remaining fields

Usage:
  python scripts/sort_analysis_jsonl.py \
      --input analysis_results.jsonl \
      --output analysis_results_sorted.jsonl
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def to_int(value: Any) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except Exception:
            return 0


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
                else:
                    print(f"Skipping non-dict JSON at line {i}")
            except json.JSONDecodeError as e:
                print(f"Skipping invalid JSON at line {i}: {e}")
    return items


def reorder_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    ordered: Dict[str, Any] = {}

    # Primary fields in required order
    primary_order = [
        "username",
        "followersCount",
        "friendsCount",
        "kolFollowersCount",
        "description",
        "location",
        "website",
    ]

    for key in primary_order:
        if key in item:
            ordered[key] = item.get(key)

    # Tags and MBTI, then summary
    tag_order = [
        "language_tags",
        "ecosystem_tags",
        "user_type_tags",
        "MBTI",
    ]
    for key in tag_order:
        if key in item:
            ordered[key] = item.get(key)

    if "summary" in item:
        ordered["summary"] = item.get("summary")

    # Append any remaining keys not yet included
    for key, value in item.items():
        if key not in ordered:
            ordered[key] = value

    return ordered


def sort_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda x: to_int(x.get("kolFollowersCount", 0)), reverse=True)


def write_jsonl(items: List[Dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Sort analysis_results.jsonl by kolFollowersCount descending and reorder fields.")
    parser.add_argument("--input", default="analysis_results.jsonl", help="Path to input JSONL file")
    parser.add_argument("--output", default="analysis_results_sorted.jsonl", help="Path to output sorted JSONL file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    items = load_jsonl(input_path)
    if not items:
        print("No valid items found in input.")
        write_jsonl([], output_path)
        print(f"Wrote 0 items to {output_path}")
        return

    sorted_items = sort_items(items)
    reordered_items = [reorder_fields(item) for item in sorted_items]
    write_jsonl(reordered_items, output_path)
    print(f"Sorted {len(reordered_items)} items by kolFollowersCount (desc) and wrote to {output_path}")


if __name__ == "__main__":
    main()