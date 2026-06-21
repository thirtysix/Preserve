#!/usr/bin/env python3
"""
Preserve Dashboard — Interactive PII detection and scrubbing.

Usage:
    source .venv/bin/activate
    python dashboard.py
"""

import csv
import io
import json
import time

import gradio as gr

from preserve import Scrubber, PreserveConfig, SensitivityLevel
from preserve.structured import StructuredScrubber, classify_column

# --- Preloaded examples ---

EXAMPLES = {
    "Clean — Patient record": (
        "Patient Aurora Rossi, born 1971-04-05, age 52, residing at Via Roma 31, "
        "Emilia-Romagna, Italy. Contact: aurora.rossi@hospital.org, phone +39 381 303 9928. "
        "National ID: KLHWTE77P09E881I. Passport: CC6770619. "
        "Emergency contact: Sofia Esposito (+39 393 611 7482)."
    ),
    "Clean — Finnish data": (
        "Patient Mikko Virtanen, henkilötunnus 131052-308T, "
        "residing at Mannerheimintie 42, Helsinki. Phone +358 44 9876543. "
        "IBAN: FI4950000120000062. Y-tunnus: 2345678-0. "
        "Emergency contact: Aino Korhonen."
    ),
    "Messy — No capitalization": (
        "patient aurora rossi born april 5 1971 lives at via roma 31 rome italy. "
        "email aurora.rossi@hospital.org, ssn 123-45-6789"
    ),
    "Messy — Abbreviations": (
        "pt: J. Smith, dob 3/15/85, ssn 123-45-6789, dx: T2DM, rx: metformin 500mg bid"
    ),
    "Messy — Run-on text": (
        "ok so the patient is Leonardo Ferrari age 35 from Corso Italia 47 Lombardy "
        "he came in with chest pain and his wife Maria Ferrari called to ask about "
        "results her number is +39 345 678 9012"
    ),
    "Messy — Chat style": (
        "lol aurora rossi just dmed me her address its via roma 31 in rome 😂 "
        "her bday is april 5th btw"
    ),
    "Messy — Medical shorthand": (
        "36yo M leonardo ferrari presents w/ cp x 2d. pmhx: dm2, htn. "
        "meds: metformin, lisinopril. wife maria called, ph 039-345-6789012. "
        "ins: aetna grp# 12345. addr: corso italia 47 lombardy."
    ),
    "Messy — Mixed languages": (
        "Asiakas Mikko Virtanen soitti eilen, his English is good. "
        "Osoite: Mannerheimintie 42. He wants to cancel his subscription, "
        "puhelin 040-1234567."
    ),
    "Messy — Obfuscated": (
        "reach her at aurora dot rossi at hospital dot org or "
        "call five five five eight six seven five three zero nine"
    ),
    "Messy — Dense PII dump": (
        "Name: Aino Korhonen / DOB: 15.3.1990 / HETU: 150390A234B / "
        "Addr: Aleksanterinkatu 7, Helsinki / Tel: +358501234567 / "
        "IBAN: FI2112345600000785 / Passport: XK4567890"
    ),
    "Safe text — no PII": (
        "The algorithm processes data in parallel using 8 threads across the CPU cores. "
        "Version 4.2 includes improved performance metrics and better error handling."
    ),
    "Safe text — medical terms": (
        "The patient presented with acute myocardial infarction. Treatment protocol "
        "includes aspirin 325mg and heparin drip. Blood type O+ is the most common."
    ),
}

# --- Core functions ---

_scrubber_cache: dict[str, Scrubber] = {}


def get_scrubber(sensitivity: str, use_l1: bool, use_l2_names: bool, use_l3: bool) -> Scrubber:
    """Get or create a cached scrubber with the given settings."""
    key = f"{sensitivity}_{use_l1}_{use_l2_names}_{use_l3}"
    if key not in _scrubber_cache:
        config = PreserveConfig(
            sensitivity_level=SensitivityLevel(sensitivity),
            use_normalcy_scanner=use_l1,
            use_name_scorer=use_l2_names,
            use_llm_review=use_l3,
            llm_backend="embedded" if use_l3 else "server",
            llm_model_path="models/Qwen3.5-0.8B-Q4_K_M.gguf",
            llm_n_threads=4,
            llm_n_threads_batch=4,
        )
        _scrubber_cache[key] = Scrubber(config)
    return _scrubber_cache[key]


def scrub_text(
    text: str,
    sensitivity: str,
    use_l1: bool,
    use_l2_names: bool,
    use_l3: bool,
):
    """Main scrub function called by the dashboard."""
    if not text.strip():
        return "", "", "No input text.", ""

    scrubber = get_scrubber(sensitivity, use_l1, use_l2_names, use_l3)

    t0 = time.time()
    result = scrubber.scrub(text)
    elapsed = time.time() - t0

    # Build highlighted text (original with PII highlighted)
    highlighted = text
    # Sort detections by position descending for safe replacement
    sorted_dets = sorted(result.detections, key=lambda d: d.start, reverse=True)
    for d in sorted_dets:
        before = highlighted[:d.start]
        after = highlighted[d.end:]
        highlighted = f"{before}**[{d.replacement_type}: {d.matched_text}]**{after}"

    # Build detection table
    det_rows = []
    for d in result.detections:
        det_rows.append({
            "Type": d.replacement_type,
            "Text": d.matched_text,
            "Layer": d.detection_layer,
            "Confidence": f"{d.confidence:.2f}",
            "Position": f"{d.start}-{d.end}",
        })

    # Stats
    layer_counts = {}
    for d in result.detections:
        layer_counts[d.detection_layer] = layer_counts.get(d.detection_layer, 0) + 1

    stats = f"**{result.pii_count} PII items** detected in **{elapsed:.3f}s**\n\n"
    if layer_counts:
        stats += "Per layer:\n"
        for layer, count in sorted(layer_counts.items()):
            stats += f"- {layer}: {count}\n"
    else:
        stats += "No PII detected."

    # Detection table as markdown
    if det_rows:
        table = "| Type | Text | Layer | Confidence |\n|------|------|-------|------|\n"
        for r in det_rows:
            table += f"| {r['Type']} | {r['Text'][:30]} | {r['Layer']} | {r['Confidence']} |\n"
    else:
        table = "No detections."

    return result.sanitized_text, highlighted, stats, table


def scrub_csv_upload(file, sensitivity, use_l1, use_l2_names, use_l3):
    """Scrub an uploaded CSV file."""
    if file is None:
        return "No file uploaded.", ""

    config = PreserveConfig(
        sensitivity_level=SensitivityLevel(sensitivity),
        use_normalcy_scanner=use_l1,
        use_name_scorer=use_l2_names,
    )
    struct_scrubber = StructuredScrubber(config)

    with open(file.name, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames

    scrubbed_rows, maps = struct_scrubber.scrub_csv_rows(rows)
    total_pii = sum(len(pm) for pm in maps)

    # Column classification
    col_info = "**Column classification:**\n\n"
    for h in headers:
        pii_type = classify_column(h)
        col_info += f"- `{h}` → {'**' + pii_type + '**' if pii_type else 'safe (not scrubbed)'}\n"

    col_info += f"\n**{total_pii} PII items** scrubbed across **{len(rows)} rows**"

    # Build output CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(scrubbed_rows)

    return col_info, output.getvalue()


def compare_configs(text, sens_a, l1_a, names_a, l3_a, sens_b, l1_b, names_b, l3_b):
    """Compare two configurations side by side."""
    if not text.strip():
        return "", "", ""

    scrubber_a = get_scrubber(sens_a, l1_a, names_a, l3_a)
    scrubber_b = get_scrubber(sens_b, l1_b, names_b, l3_b)

    t0 = time.time()
    result_a = scrubber_a.scrub(text)
    time_a = time.time() - t0

    t0 = time.time()
    result_b = scrubber_b.scrub(text)
    time_b = time.time() - t0

    comparison = f"| Metric | Config A | Config B |\n|--------|----------|----------|\n"
    comparison += f"| PII found | {result_a.pii_count} | {result_b.pii_count} |\n"
    comparison += f"| Time | {time_a:.3f}s | {time_b:.3f}s |\n"

    types_a = set(d.replacement_type for d in result_a.detections)
    types_b = set(d.replacement_type for d in result_b.detections)
    only_a = types_a - types_b
    only_b = types_b - types_a
    if only_a:
        comparison += f"| Only in A | {', '.join(only_a)} | — |\n"
    if only_b:
        comparison += f"| Only in B | — | {', '.join(only_b)} |\n"

    return result_a.sanitized_text, result_b.sanitized_text, comparison


def load_example(example_name):
    """Load a preloaded example."""
    return EXAMPLES.get(example_name, "")


# --- Build Gradio UI ---

with gr.Blocks(title="Preserve Dashboard", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Preserve Dashboard\nPrivacy-preserving PII detection and scrubbing")

    with gr.Tabs():
        # === Tab 1: Main Scrubber ===
        with gr.Tab("Scrub"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Input")
                    example_dropdown = gr.Dropdown(
                        choices=list(EXAMPLES.keys()),
                        label="Load example",
                        value=None,
                    )
                    input_text = gr.Textbox(
                        label="Text to scrub",
                        lines=10,
                        placeholder="Paste or type text containing PII...",
                    )

                with gr.Column(scale=1):
                    gr.Markdown("### Output")
                    output_scrubbed = gr.Textbox(label="Scrubbed text", lines=5)
                    output_highlighted = gr.Markdown(label="Highlighted PII")

            with gr.Row():
                sensitivity = gr.Radio(
                    ["minimal", "standard", "aggressive"],
                    value="aggressive",
                    label="Sensitivity",
                )
                use_l1 = gr.Checkbox(value=True, label="Layer 1 (Normalcy)")
                use_l2_names = gr.Checkbox(value=True, label="Layer 2h (Name Scorer)")
                use_l3 = gr.Checkbox(value=False, label="Layer 3 (Local LLM)")

            scrub_btn = gr.Button("Scrub", variant="primary")

            with gr.Row():
                with gr.Column():
                    output_stats = gr.Markdown(label="Statistics")
                with gr.Column():
                    output_table = gr.Markdown(label="Detections")

            example_dropdown.change(load_example, inputs=[example_dropdown], outputs=[input_text])
            scrub_btn.click(
                scrub_text,
                inputs=[input_text, sensitivity, use_l1, use_l2_names, use_l3],
                outputs=[output_scrubbed, output_highlighted, output_stats, output_table],
            )

        # === Tab 2: CSV Upload ===
        with gr.Tab("CSV Scrub"):
            gr.Markdown("### Upload a CSV file for structured scrubbing\nColumn names drive PII classification automatically.")
            with gr.Row():
                csv_file = gr.File(label="Upload CSV", file_types=[".csv"])
                csv_sens = gr.Radio(
                    ["minimal", "standard", "aggressive"],
                    value="aggressive", label="Sensitivity",
                )
            with gr.Row():
                csv_l1 = gr.Checkbox(value=True, label="Layer 1")
                csv_names = gr.Checkbox(value=True, label="Name Scorer")
                csv_l3 = gr.Checkbox(value=False, label="Layer 3 (LLM)")
            csv_btn = gr.Button("Scrub CSV", variant="primary")
            csv_info = gr.Markdown(label="Column Classification")
            csv_output = gr.Textbox(label="Scrubbed CSV", lines=15)

            csv_btn.click(
                scrub_csv_upload,
                inputs=[csv_file, csv_sens, csv_l1, csv_names, csv_l3],
                outputs=[csv_info, csv_output],
            )

        # === Tab 3: Compare Configs ===
        with gr.Tab("Compare"):
            gr.Markdown("### Compare two configurations side by side")
            compare_input = gr.Textbox(
                label="Text",
                lines=5,
                value=EXAMPLES["Clean — Patient record"],
            )

            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Config A**")
                    cmp_sens_a = gr.Radio(["minimal", "standard", "aggressive"], value="minimal", label="Sensitivity")
                    cmp_l1_a = gr.Checkbox(value=False, label="Layer 1")
                    cmp_names_a = gr.Checkbox(value=False, label="Name Scorer")
                    cmp_l3_a = gr.Checkbox(value=False, label="Layer 3")
                with gr.Column():
                    gr.Markdown("**Config B**")
                    cmp_sens_b = gr.Radio(["minimal", "standard", "aggressive"], value="aggressive", label="Sensitivity")
                    cmp_l1_b = gr.Checkbox(value=True, label="Layer 1")
                    cmp_names_b = gr.Checkbox(value=True, label="Name Scorer")
                    cmp_l3_b = gr.Checkbox(value=False, label="Layer 3")

            cmp_btn = gr.Button("Compare", variant="primary")

            with gr.Row():
                cmp_out_a = gr.Textbox(label="Config A output", lines=5)
                cmp_out_b = gr.Textbox(label="Config B output", lines=5)

            cmp_table = gr.Markdown(label="Comparison")

            cmp_btn.click(
                compare_configs,
                inputs=[compare_input, cmp_sens_a, cmp_l1_a, cmp_names_a, cmp_l3_a,
                        cmp_sens_b, cmp_l1_b, cmp_names_b, cmp_l3_b],
                outputs=[cmp_out_a, cmp_out_b, cmp_table],
            )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
