#!/usr/bin/env python3
"""
Download a GGUF model for Preserve's Layer 3 local LLM review.

Usage:
    # Recommended: 4B model, best accuracy for PII detection
    python scripts/download_model.py --model 4B --quant Q4_K_M

    # Lightweight: 0.8B model, fastest on CPU
    python scripts/download_model.py --model 0.8B --quant Q8_0

    # Medium: 2B model, good balance
    python scripts/download_model.py --model 2B --quant Q4_K_M

Models are downloaded to the models/ directory.
"""

import argparse
import os
import subprocess
import sys


MODELS = {
    "0.8B": {
        "repo": "unsloth/Qwen3.5-0.8B-GGUF",
        "quants": {
            "Q3_K_M": {"file": "Qwen3.5-0.8B-Q3_K_M.gguf", "size": "470 MB"},
            "Q4_K_M": {"file": "Qwen3.5-0.8B-Q4_K_M.gguf", "size": "533 MB"},
            "Q5_K_M": {"file": "Qwen3.5-0.8B-Q5_K_M.gguf", "size": "590 MB"},
            "Q8_0": {"file": "Qwen3.5-0.8B-Q8_0.gguf", "size": "812 MB"},
        },
        "ram": "~3-3.5 GB",
    },
    "2B": {
        "repo": "unsloth/Qwen3.5-2B-GGUF",
        "quants": {
            "Q3_K_M": {"file": "Qwen3.5-2B-Q3_K_M.gguf", "size": "~1.1 GB"},
            "Q4_K_M": {"file": "Qwen3.5-2B-Q4_K_M.gguf", "size": "~1.4 GB"},
            "Q5_K_M": {"file": "Qwen3.5-2B-Q5_K_M.gguf", "size": "~1.7 GB"},
            "Q8_0": {"file": "Qwen3.5-2B-Q8_0.gguf", "size": "~2.3 GB"},
        },
        "ram": "~3.5-5 GB",
    },
    "4B": {
        "repo": "unsloth/Qwen3.5-4B-GGUF",
        "quants": {
            "Q3_K_M": {"file": "Qwen3.5-4B-Q3_K_M.gguf", "size": "2.29 GB"},
            "Q4_K_M": {"file": "Qwen3.5-4B-Q4_K_M.gguf", "size": "2.74 GB"},
            "Q5_K_M": {"file": "Qwen3.5-4B-Q5_K_M.gguf", "size": "3.14 GB"},
            "Q8_0": {"file": "Qwen3.5-4B-Q8_0.gguf", "size": "4.48 GB"},
        },
        "ram": "~4.5-7 GB",
    },
}


def main():
    parser = argparse.ArgumentParser(description="Download a GGUF model for Preserve")
    parser.add_argument(
        "--model", choices=["0.8B", "2B", "4B"], default="4B",
        help="Model size (default: 4B)"
    )
    parser.add_argument(
        "--quant", choices=["Q3_K_M", "Q4_K_M", "Q5_K_M", "Q8_0"], default="Q4_K_M",
        help="Quantization level (default: Q4_K_M)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory to save the model (default: models/ in project root)"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available models and exit"
    )
    args = parser.parse_args()

    if args.list:
        print("Available models:\n")
        for size, info in MODELS.items():
            print(f"  Qwen3.5-{size} (RAM: {info['ram']})")
            for quant, qinfo in info["quants"].items():
                print(f"    --model {size} --quant {quant}  ({qinfo['size']})")
            print()
        return

    model_info = MODELS[args.model]
    quant_info = model_info["quants"][args.quant]

    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, "models")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, quant_info["file"])

    if os.path.exists(output_path):
        print(f"Model already exists: {output_path}")
        return

    print(f"Downloading Qwen3.5-{args.model} {args.quant}")
    print(f"  Repository: {model_info['repo']}")
    print(f"  File: {quant_info['file']}")
    print(f"  Size: {quant_info['size']}")
    print(f"  RAM needed: {model_info['ram']}")
    print(f"  Saving to: {output_path}")
    print()

    # Try huggingface-hub CLI first, fall back to wget
    try:
        subprocess.run(
            [
                sys.executable, "-m", "huggingface_hub", "download",
                model_info["repo"],
                quant_info["file"],
                "--local-dir", output_dir,
                "--local-dir-use-symlinks", "False",
            ],
            check=True,
        )
        print(f"\nDone! Model saved to: {output_path}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to direct URL download
        url = f"https://huggingface.co/{model_info['repo']}/resolve/main/{quant_info['file']}"
        print(f"Falling back to direct download from: {url}")
        try:
            subprocess.run(["wget", "-O", output_path, url], check=True)
            print(f"\nDone! Model saved to: {output_path}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"\nDownload failed. Please download manually from:")
            print(f"  https://huggingface.co/{model_info['repo']}")
            print(f"\nSave {quant_info['file']} to: {output_dir}/")
            sys.exit(1)

    print(f"\nTo use with Preserve:")
    print(f"  config = PreserveConfig(")
    print(f"      use_llm_review=True,")
    print(f"      llm_model_path='{output_path}',")
    print(f"  )")


if __name__ == "__main__":
    main()
