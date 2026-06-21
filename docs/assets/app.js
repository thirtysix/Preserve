/*
 * Preserve — static browser demo of the deterministic detection layer.
 *
 * Mirrors the Python pipeline for Layer 2a (regex) + Layer 2c (checksums):
 *   detectPatterns -> validateChecksums -> deduplicate -> scrub
 *
 * Patterns are exported verbatim from preserve/patterns.py (assets/patterns.js).
 * The checksum validators below are hand-ported from preserve/validators.py.
 * Everything runs client-side; no text leaves the browser.
 */
(function () {
  "use strict";

  const SENS_ORDER = ["minimal", "standard", "aggressive"];

  // --- Checksum validators (ported from preserve/validators.py) ---
  const onlyDigits = (s) => (s.match(/\d/g) || []).map(Number);

  function luhn(number) {
    const d = onlyDigits(number);
    if (d.length < 2) return false;
    for (let i = d.length - 2; i >= 0; i -= 2) {
      d[i] *= 2;
      if (d[i] > 9) d[i] -= 9;
    }
    return d.reduce((a, b) => a + b, 0) % 10 === 0;
  }

  function iban(value) {
    const c = value.replace(/\s/g, "").toUpperCase();
    if (c.length < 5 || !/^[A-Z]{2}/.test(c) || !/^\d{2}/.test(c.slice(2, 4))) return false;
    const rearr = c.slice(4) + c.slice(0, 4);
    let numeric = "";
    for (const ch of rearr) {
      if (/\d/.test(ch)) numeric += ch;
      else if (/[A-Z]/.test(ch)) numeric += (ch.charCodeAt(0) - 65 + 10).toString();
      else return false;
    }
    try { return BigInt(numeric) % 97n === 1n; } catch (e) { return false; }
  }

  const MOD23 = "TRWAGMYFPDXBNJZSQVHLCKE";

  function spainDni(value) {
    const c = value.trim();
    if (c.length !== 9) return false;
    const n = parseInt(c.slice(0, 8), 10);
    if (Number.isNaN(n)) return false;
    return c[8].toUpperCase() === MOD23[n % 23];
  }

  function spainNie(value) {
    const c = value.trim().toUpperCase();
    if (c.length !== 9 || !"XYZ".includes(c[0])) return false;
    const n = parseInt(({ X: "0", Y: "1", Z: "2" }[c[0]]) + c.slice(1, 8), 10);
    if (Number.isNaN(n)) return false;
    return c[8] === MOD23[n % 23];
  }

  function finlandHetu(value) {
    const c = value.replace(/\s/g, "");
    if (c.length !== 11) return false;
    const lookup = "0123456789ABCDEFHJKLMNPRSTUVWXY";
    const nine = parseInt(c.slice(0, 6) + c.slice(8, 11), 10);
    if (Number.isNaN(nine)) return false;
    return c[c.length - 1] === lookup[nine % 31];
  }

  function brazilCpf(value) {
    const d = onlyDigits(value);
    if (d.length !== 11 || new Set(d).size === 1) return false;
    let total = 0;
    for (let i = 0; i < 9; i++) total += d[i] * (10 - i);
    let chk = total % 11 < 2 ? 0 : 11 - (total % 11);
    if (d[9] !== chk) return false;
    total = 0;
    for (let i = 0; i < 10; i++) total += d[i] * (11 - i);
    chk = total % 11 < 2 ? 0 : 11 - (total % 11);
    return d[10] === chk;
  }

  function netherlandsBsn(value) {
    let d = onlyDigits(value);
    if (d.length === 8) d = [0].concat(d);
    if (d.length !== 9) return false;
    const w = [9, 8, 7, 6, 5, 4, 3, 2, -1];
    const total = d.reduce((a, x, i) => a + x * w[i], 0);
    return total % 11 === 0 && total !== 0;
  }

  function ukNhs(value) {
    const d = onlyDigits(value);
    if (d.length !== 10) return false;
    let total = 0;
    for (let i = 0; i < 9; i++) total += d[i] * (10 - i);
    let chk = 11 - (total % 11);
    if (chk === 11) chk = 0;
    if (chk === 10) return false;
    return d[9] === chk;
  }

  function southKoreaRrn(value) {
    const d = onlyDigits(value);
    if (d.length !== 13) return false;
    const w = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5];
    let total = 0;
    for (let i = 0; i < 12; i++) total += d[i] * w[i];
    const chk = (11 - (total % 11)) % 10;
    return d[12] === chk;
  }

  // Keyed by pattern name, mirroring VALIDATORS in preserve/validators.py
  const lastToken = (t) => (t.includes(":") ? t.trim().split(/\s+/).pop() : t);
  const VALIDATORS = {
    credit_card: luhn,
    iban: iban,
    finland_hetu: finlandHetu,
    spain_dni: spainDni,
    spain_nie: spainNie,
    brazil_cpf: brazilCpf,
    netherlands_bsn: (t) => netherlandsBsn(lastToken(t)),
    uk_nhs: (t) => ukNhs(lastToken(t)),
    south_korea_rrn: southKoreaRrn,
  };

  // --- Layer 2d: context-aware confidence scoring (ported from context.py) ---
  function compileContext() {
    const c = window.PRESERVE_CONTEXT;
    const mk = (arr) => arr.map(([src, fl, w]) => [new RegExp(src, fl), w]);
    const boosters = {};
    for (const t of Object.keys(c.boosters)) boosters[t] = mk(c.boosters[t]);
    return { window: c.window, boosters, generic: mk(c.generic), reducers: mk(c.reducers) };
  }
  const CTX = compileContext();

  function scoreContext(text, start, end, type, base) {
    const cs = Math.max(0, start - CTX.window);
    const ce = Math.min(text.length, end + CTX.window);
    const before = text.slice(cs, start);
    const context = before + text.slice(end, ce);
    let conf = base;
    for (const [re, boost] of (CTX.boosters[type] || [])) {
      if (re.test(context)) { conf += boost; break; }
    }
    for (const [re, boost] of CTX.generic) {
      if (re.test(before)) { conf += boost; break; }
    }
    for (const [re, red] of CTX.reducers) {
      if (re.test(context)) conf += red;
    }
    return Math.max(0, Math.min(1, conf));
  }

  // --- Detection pipeline ---
  function compilePatterns() {
    return window.PRESERVE_PATTERNS.map((p) => ({
      ...p,
      re: new RegExp(p.source, "gd" + p.flags),
    }));
  }
  const PATTERNS = compilePatterns();

  function detect(text, sensitivity) {
    const maxIdx = SENS_ORDER.indexOf(sensitivity);
    let matches = [];

    // Layer 2a: regex
    for (const p of PATTERNS) {
      if (SENS_ORDER.indexOf(p.sensitivity) > maxIdx) continue;
      p.re.lastIndex = 0;
      for (const m of text.matchAll(p.re)) {
        let start, end, value;
        if (p.group === 1 && m[1] != null && m.indices && m.indices[1]) {
          [start, end] = m.indices[1];
          value = m[1];
        } else {
          [start, end] = m.indices[0];
          value = m[0];
        }
        matches.push({
          start, end, value,
          pattern: p.name,
          type: p.replacement_type,
          layer: "regex",
          confidence: 1.0,
        });
      }
    }

    // Layer 2c: checksum validation (failure lowers confidence, never drops)
    for (const m of matches) {
      const v = VALIDATORS[m.pattern];
      if (!v) continue;
      let ok = false;
      try { ok = v(m.value); } catch (e) { ok = false; }
      m.layer = "checksum";
      m.checksum = ok ? "pass" : "fail";
      m.confidence = ok ? Math.min(m.confidence + 0.1, 1.0)
                        : Math.max(m.confidence - 0.3, 0.2);
    }

    // Layer 2d: context-aware confidence scoring
    for (const m of matches) {
      m.confidence = scoreContext(text, m.start, m.end, m.type, m.confidence);
    }

    // Deduplicate: highest confidence, then longest, keep non-overlapping
    matches.sort((a, b) =>
      (b.confidence - a.confidence) ||
      ((b.end - b.start) - (a.end - a.start)) ||
      (a.start - b.start));
    const kept = [];
    for (const m of matches) {
      if (!kept.some((k) => m.start < k.end && m.end > k.start)) kept.push(m);
    }
    kept.sort((a, b) => a.start - b.start);
    return kept;
  }

  // --- Scrub: reversible per-type placeholders, value-deduped (mirrors mapping.py) ---
  function scrub(text, detections) {
    const counters = {};
    const valueToPlaceholder = new Map();
    const summary = {};
    // Replace right-to-left so indices stay valid
    const ordered = [...detections].sort((a, b) => b.start - a.start);
    let out = text;
    for (const d of ordered) {
      const key = d.value.toLowerCase();
      let ph = valueToPlaceholder.get(key);
      if (!ph) {
        counters[d.type] = (counters[d.type] || 0) + 1;
        ph = `[${d.type}_${counters[d.type]}]`;
        valueToPlaceholder.set(key, ph);
      }
      out = out.slice(0, d.start) + ph + out.slice(d.end);
    }
    for (const d of detections) summary[d.type] = (summary[d.type] || 0) + 1;
    return { sanitized: out, summary };
  }

  // --- Rendering ---
  const esc = (s) => s.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function highlight(text, detections) {
    const ordered = [...detections].sort((a, b) => a.start - b.start);
    let html = "", cursor = 0;
    for (const d of ordered) {
      if (d.start < cursor) continue;
      html += esc(text.slice(cursor, d.start));
      html += `<mark title="${esc(d.type)} (${d.layer})">${esc(text.slice(d.start, d.end))}</mark>`;
      cursor = d.end;
    }
    html += esc(text.slice(cursor));
    return html || '<span class="empty">—</span>';
  }

  function renderScrubbed(sanitized) {
    return esc(sanitized).replace(/\[([A-Z_]+_\d+)\]/g, '<span class="ph">[$1]</span>')
           || '<span class="empty">—</span>';
  }

  function renderTable(detections) {
    if (!detections.length) return '<p class="empty">No PII detected at this sensitivity level.</p>';
    let rows = "";
    for (const d of [...detections].sort((a, b) => a.start - b.start)) {
      const checksum = d.checksum
        ? `<span class="layer-checksum">checksum&nbsp;${d.checksum}</span>` : "regex";
      rows += `<tr>
        <td><span class="type">${esc(d.type)}</span></td>
        <td class="val">${esc(d.value)}</td>
        <td>${esc(d.pattern)}</td>
        <td>${checksum}</td>
        <td><span class="conf-bar" style="width:${Math.round(d.confidence * 46)}px"></span>
            &nbsp;${d.confidence.toFixed(2)}</td>
      </tr>`;
    }
    return `<table><thead><tr>
      <th>Type</th><th>Value</th><th>Pattern</th><th>Detected by</th><th>Confidence</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  }

  // --- Wire up ---
  const $ = (id) => document.getElementById(id);

  function run() {
    const text = $("input").value;
    const sensitivity = $("sensitivity").value;
    const detections = detect(text, sensitivity);
    const { sanitized, summary } = scrub(text, detections);

    $("highlight").innerHTML = highlight(text, detections);
    $("scrubbed").innerHTML = renderScrubbed(sanitized);

    const chips = Object.entries(summary)
      .map(([t, n]) => `<span class="chip">${esc(t)} × ${n}</span>`).join("");
    $("summary").innerHTML = chips || '<span class="empty">No PII detected.</span>';
    $("stat").textContent =
      `${detections.length} item(s) detected · ${text.length} chars · ${PATTERNS.length} patterns active at "${sensitivity}"`;
    $("table").innerHTML = renderTable(detections);
  }

  function loadExample(name) {
    if (window.PRESERVE_EXAMPLES[name]) {
      $("input").value = window.PRESERVE_EXAMPLES[name];
      run();
    }
  }

  // Export the pure pipeline for headless testing (Node); skip DOM wiring there.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { detect, scrub, VALIDATORS, PATTERNS };
  }
  if (typeof document === "undefined") return;

  document.addEventListener("DOMContentLoaded", () => {
    // Example buttons
    const ex = $("examples");
    Object.keys(window.PRESERVE_EXAMPLES).forEach((name) => {
      const b = document.createElement("button");
      b.textContent = name;
      b.addEventListener("click", () => loadExample(name));
      ex.appendChild(b);
    });
    $("input").addEventListener("input", run);
    $("sensitivity").addEventListener("change", run);
    $("clear").addEventListener("click", () => { $("input").value = ""; run(); });

    // Seed with the first example
    const first = Object.keys(window.PRESERVE_EXAMPLES)[0];
    $("input").value = window.PRESERVE_EXAMPLES[first];
    run();
  });
})();
