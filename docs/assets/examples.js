// Example inputs for the static demo. A curated subset of the Gradio
// dashboard's examples, chosen to exercise the deterministic (regex + checksum)
// layer, plus one checksum-focused case with known-valid values.
window.PRESERVE_EXAMPLES = {
  "Patient record": (
    "Patient: Aurora Rossi, born 04/05/1971, email aurora.rossi@hospital.org, " +
    "phone (555) 123-4567, SSN 123-45-6789, card 4242 4242 4242 4242. " +
    "Emergency contact: Sofia Esposito."
  ),
  "Checksums (valid/invalid)": (
    "Card 4242 4242 4242 4242 passes the Luhn check. " +
    "IBAN GB82 WEST 1234 5698 7654 32 is valid; " +
    "GB99 WEST 1234 5698 7654 32 fails its check digits. NHS 943 476 5919."
  ),
  "Finnish record": (
    "Patient Mikko Virtanen, henkilötunnus 131052-308T, " +
    "residing at Mannerheimintie 42, Helsinki. Phone +358 44 9876543. " +
    "IBAN: FI4950000120000062. Y-tunnus: 2345678-0."
  ),
  "Messy — abbreviations": (
    "pt: J. Smith, dob 3/15/85, ssn 123-45-6789, dx: T2DM, rx: metformin 500mg bid"
  ),
  "Dense PII dump": (
    "Name: Aino Korhonen / DOB: 15.3.1990 / HETU: 150390A234B / " +
    "Addr: 7 Park Avenue / Tel: +358501234567 / " +
    "IBAN: FI2112345600000785 / Passport: XK4567890"
  ),
  "Safe text — no PII": (
    "The algorithm processes data in parallel using 8 threads across the CPU cores. " +
    "Version 4.2 includes improved performance metrics and better error handling."
  ),
};
