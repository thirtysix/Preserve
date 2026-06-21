"""
CLI interface for Preserve.

Usage:
    python -m preserve scrub "Patient Aurora Rossi, SSN 123-45-6789"
    python -m preserve detect "Patient Aurora Rossi, SSN 123-45-6789"
    echo "text" | python -m preserve scrub -
    python -m preserve scrub-file input.txt
    python -m preserve scrub-csv data.csv
"""

import argparse
import csv
import json
import sys

from preserve import Scrubber, PreserveConfig, SensitivityLevel
from preserve.structured import StructuredScrubber


def cmd_scrub(args, config):
    """Scrub PII from text and output the sanitized version."""
    scrubber = Scrubber(config)
    text = _get_input(args.text)
    result = scrubber.scrub(text)
    print(result.sanitized_text)

    if args.verbose:
        print(f"\n--- {result.pii_count} PII items scrubbed ---", file=sys.stderr)
        for d in result.detections:
            print(f"  [{d.replacement_type:12s}] \"{d.matched_text}\" ({d.detection_layer})", file=sys.stderr)


def cmd_detect(args, config):
    """Detect PII in text and output detections as JSON."""
    scrubber = Scrubber(config)
    text = _get_input(args.text)
    result = scrubber.scrub(text)

    detections = [
        {
            "text": d.matched_text,
            "type": d.replacement_type,
            "start": d.start,
            "end": d.end,
            "confidence": round(d.confidence, 2),
            "layer": d.detection_layer,
        }
        for d in result.detections
    ]

    if args.format == "json":
        print(json.dumps(detections, indent=2, ensure_ascii=False))
    else:
        for d in detections:
            print(f"[{d['type']:12s}] {d['start']:4d}-{d['end']:4d} ({d['confidence']:.1f}) \"{d['text']}\"")


def cmd_scrub_file(args, config):
    """Scrub PII from a text file."""
    scrubber = Scrubber(config)

    with open(args.file, "r", encoding="utf-8") as f:
        text = f.read()

    result = scrubber.scrub(text)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result.sanitized_text)
        print(f"Scrubbed {result.pii_count} PII items → {args.output}", file=sys.stderr)
    else:
        print(result.sanitized_text)


def cmd_scrub_csv(args, config):
    """Scrub PII from a CSV file using column-aware classification."""
    scrubber = StructuredScrubber(config)

    with open(args.file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames

    scrubbed_rows, maps = scrubber.scrub_csv_rows(rows)

    writer = csv.DictWriter(
        sys.stdout if not args.output else open(args.output, "w", encoding="utf-8", newline=""),
        fieldnames=headers,
    )
    writer.writeheader()
    writer.writerows(scrubbed_rows)

    total_pii = sum(len(pm) for pm in maps)
    print(f"Scrubbed {total_pii} PII items across {len(rows)} rows", file=sys.stderr)


def _get_input(text_arg: str) -> str:
    """Get input text from argument or stdin."""
    if text_arg == "-":
        return sys.stdin.read()
    return text_arg


def main():
    parser = argparse.ArgumentParser(
        prog="preserve",
        description="Privacy-preserving PII detection and scrubbing",
    )
    parser.add_argument(
        "-s", "--sensitivity",
        choices=["minimal", "standard", "aggressive"],
        default="aggressive",
        help="Sensitivity level (default: aggressive)",
    )
    parser.add_argument(
        "--no-names", action="store_true",
        help="Disable hybrid name scorer",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scrub
    p_scrub = subparsers.add_parser("scrub", help="Scrub PII from text")
    p_scrub.add_argument("text", help='Text to scrub (use "-" for stdin)')
    p_scrub.add_argument("-v", "--verbose", action="store_true")

    # detect
    p_detect = subparsers.add_parser("detect", help="Detect PII in text (no scrubbing)")
    p_detect.add_argument("text", help='Text to analyze (use "-" for stdin)')
    p_detect.add_argument("-f", "--format", choices=["json", "table"], default="table")

    # scrub-file
    p_file = subparsers.add_parser("scrub-file", help="Scrub PII from a text file")
    p_file.add_argument("file", help="Input file path")
    p_file.add_argument("-o", "--output", help="Output file (default: stdout)")

    # scrub-csv
    p_csv = subparsers.add_parser("scrub-csv", help="Scrub PII from a CSV file")
    p_csv.add_argument("file", help="Input CSV file")
    p_csv.add_argument("-o", "--output", help="Output CSV file (default: stdout)")

    args = parser.parse_args()

    config = PreserveConfig(
        sensitivity_level=SensitivityLevel(args.sensitivity),
        use_name_scorer=not args.no_names,
    )

    commands = {
        "scrub": cmd_scrub,
        "detect": cmd_detect,
        "scrub-file": cmd_scrub_file,
        "scrub-csv": cmd_scrub_csv,
    }

    commands[args.command](args, config)


if __name__ == "__main__":
    main()
