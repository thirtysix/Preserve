// Precomputed by scripts/compute_llm_extra.py with a local Qwen3.5 model.
// Per example: PII the local LLM (Layer 3) catches that the demo's
// deterministic layers miss. Reviewed by hand; the browser can't run the model.
window.PRESERVE_LLM_MODEL = "Qwen3.5-4B (Q4_K_M)";
window.PRESERVE_LLM_EXTRA = {
  "Patient record": [],
  "Checksums (valid/invalid)": [],
  "Finnish record": [
    {
      "start": 83,
      "end": 91,
      "value": "Helsinki",
      "type": "ADDRESS"
    }
  ],
  "Messy: abbreviations": [],
  "Dense PII dump": [],
  "International names (bare)": [],
  "Bare name (rules miss it)": [
    {
      "start": 34,
      "end": 37,
      "value": "Bob",
      "type": "NAME"
    }
  ],
  "Custom ID (rules miss it)": [
    {
      "start": 26,
      "end": 39,
      "value": "MEX-2345-6789",
      "type": "OTHER"
    }
  ],
  "Safe text: no PII": []
};
