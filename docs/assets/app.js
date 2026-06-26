/*
 * Preserve: static browser demo of the deterministic detection layer.
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

  // What each sensitivity level actually applies (shown live under the dropdown).
  const SENS_DETAIL = {
    minimal: "Applies regex + checksums + context · structured IDs, cards, IBANs",
    standard: "Applies regex + checksums + context · + phones, IPs, dates",
    aggressive: "Applies regex + checksums + context + name gazetteer · + names, addresses",
  };

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

  // --- Layer 2h (compact): gazetteer name scorer (ported from name_scorer.py) ---
  // Detects bare personal names across major countries using the name list in
  // names.js (distilled from names-dataset + wordfreq). This is what the full
  // Python pipeline's name scorer / local LLM would catch beyond the regexes.
  const NAMES = window.PRESERVE_NAMES || { first: [], last: [], common: [], countries: 0 };
  const FIRST = new Set(NAMES.first);
  const LAST = new Set(NAMES.last);
  const COMMON = new Set(NAMES.common);
  const inGaz = (t) => FIRST.has(t) || LAST.has(t);
  const isAcronym = (w) => w.length <= 4 && w === w.toUpperCase() && w !== w.toLowerCase();

  const NAME_SKIP = new Set([
    "the","a","an","and","or","but","for","nor","yet","so","is","are","was",
    "were","be","been","being","has","have","had","do","does","did","will",
    "would","shall","should","can","could","may","might","this","that","these",
    "those","it","its","not","no","yes","all","any","each","every","i","we",
    "you","he","she","they","me","us","him","her","them","my","our","your",
    "his","their","who","what","where","when","why","how","if","then","else",
    "than","as","at","by","in","on","to","of","with","from","into","about",
    "new","old","best","first","last","next","north","south","east","west",
    "need","want","called","said","told","asked","check","send","get","got",
    "helsinki","finland","europe","asia","africa","america","london","paris",
    "berlin","rome","tokyo","moscow","stockholm","oslo","copenhagen","amsterdam",
    "brussels","madrid","lisbon","vienna","prague","warsaw","budapest",
  ]);
  const NAME_CONTEXT_WORDS = new Set([
    "patient","client","employee","name","contact","witness","supervisor",
    "manager","doctor","nurse","attorney","applicant","customer","user",
    "beneficiary","spouse","guardian","dependent","plaintiff","defendant",
    "caller","attendee","participant","sender","recipient",
  ]);
  const TITLE_WORDS = new Set(["mr","mrs","ms","miss","dr","prof","professor","rev","sir","lady"]);
  const INTRO_WORDS = new Set([
    "wife","husband","mother","father","son","daughter",
    "patient","pt","caller","contact","employee","emp","attn",
  ]);
  const SURNAME_SUFFIX = /(?:nen|la|lä|sto|son|sen|ström|berg|lund|qvist|ez|az|ov|ova|ski|ska|vich|enko|ian|yan|ou|is|os|ić|ović)$/i;
  const NAME_CTX_BEFORE = /(?:patient|client|employee|name|contact|witness|supervisor|manager|doctor|nurse|attorney|signed by|referred by|mr|mrs|ms|miss|dr|prof|wife|husband|spouse|mother|father|son|daughter|caller|attendee|participant|sender|recipient|pt|emp|attn|fwd|re|cc)\s*[:.\s]?\s*$/i;
  const CAP_TOKEN = /[A-ZÀ-ÖØ-ÞĀ-ſ][a-zà-öø-ÿĀ-ſ]+(?:-[A-ZÀ-ÖØ-ÞĀ-ſa-zà-öø-ÿĀ-ſ]+)*/g;
  const WORD_TOKEN = /[a-zA-ZÀ-ÖØ-ÞĀ-ſà-öø-ÿ]{2,}/g;
  const INITIAL_SURNAME = /([A-ZÀ-ÖØ-ÞĀ-ſ])\.\s*([A-ZÀ-ÖØ-ÞĀ-ſ][a-zà-öø-ÿĀ-ſ]{2,})/g;
  const PAREN_NAME = /([A-ZÀ-ÖØ-ÞĀ-ſa-zà-öø-ÿĀ-ſ]+)\s*\(([A-ZÀ-ÖØ-ÞĀ-ſ][a-zà-öø-ÿĀ-ſ]+)\)/g;

  function scoreNameTokens(tokens, text, start) {
    let score = 0;
    for (const raw of tokens) {
      const t = raw.toLowerCase();
      const gaz = inGaz(t);
      if (gaz) {
        score += COMMON.has(t) ? 0.1 : 0.4;   // common word-name penalised
        if (SURNAME_SUFFIX.test(t)) score += 0.1;
      } else {
        score += COMMON.has(t) ? -0.2 : 0.05;
      }
    }
    if (tokens.length >= 2) score += 0.2;
    const before = text.slice(Math.max(0, start - 40), start);
    if (NAME_CTX_BEFORE.test(before)) score += 0.4;
    if ((start === 0 || ".!?\n".includes(text[start - 1])) && tokens.length === 1) score -= 0.2;
    return Math.max(0, Math.min(1, score));
  }

  function tokenize(re, text) {
    const out = [];
    for (const m of text.matchAll(re)) out.push([m.index, m.index + m[0].length, m[0]]);
    return out;
  }

  function detectNames(text, minScore = 0.5) {
    const cands = [];
    const mk = (s, e, conf) => cands.push({
      start: s, end: e, value: text.slice(s, e),
      pattern: "name_scorer", type: "NAME", layer: "name", confidence: conf,
    });

    // Pass 1: capitalized word sequences
    const caps = tokenize(CAP_TOKEN, text);
    for (let i = 0; i < caps.length;) {
      const [s0, e0, t0] = caps[i];
      if (NAME_SKIP.has(t0.toLowerCase()) || NAME_CONTEXT_WORDS.has(t0.toLowerCase())) { i++; continue; }
      const run = [caps[i]];
      let j = i + 1;
      while (j < caps.length) {
        const [ns, , nt] = caps[j];
        if (ns - run[run.length - 1][1] <= 2
            && !NAME_SKIP.has(nt.toLowerCase())
            && !NAME_CONTEXT_WORDS.has(nt.toLowerCase())) { run.push(caps[j]); j++; }
        else break;
      }
      if (run.length >= 2) {
        const fs = run[0][0], fe = run[run.length - 1][1];
        const sc = scoreNameTokens(run.map((r) => r[2]), text, fs);
        if (sc >= minScore) mk(fs, fe, sc);
        i = j;
      } else {
        const sc = scoreNameTokens([t0], text, s0);
        if (sc >= minScore + 0.1 && inGaz(t0.toLowerCase())) mk(s0, e0, sc);
        i++;
      }
    }

    // Pass 2: lowercase gazetteer pairs ("mikko virtanen")
    const words = tokenize(WORD_TOKEN, text);
    for (let i = 0; i < words.length - 1; i++) {
      const [s1, e1, w1] = words[i];
      const [s2, e2, w2] = words[i + 1];
      if (w1[0] === w1[0].toUpperCase() && w2[0] === w2[0].toUpperCase()) continue;
      const t1 = w1.toLowerCase(), t2 = w2.toLowerCase();
      if (NAME_SKIP.has(t1) || NAME_SKIP.has(t2)) continue;
      if (NAME_CONTEXT_WORDS.has(t1) || NAME_CONTEXT_WORDS.has(t2)) continue;
      if (s2 - e1 > 2) continue;
      if (!/^[\s,]*$/.test(text.slice(e1, s2))) continue;  // no pair across ':' etc.
      if (isAcronym(w1) || isAcronym(w2)) continue;        // MRN, DEA, ... not names
      const pair = (FIRST.has(t1) && LAST.has(t2)) || (LAST.has(t1) && FIRST.has(t2));
      if (!pair) continue;
      if (COMMON.has(t1) && COMMON.has(t2)) continue;
      let sc = 0.35;
      if (!COMMON.has(t1)) sc += 0.15;
      if (!COMMON.has(t2)) sc += 0.15;
      if (SURNAME_SUFFIX.test(t2)) sc += 0.1;
      if (NAME_CTX_BEFORE.test(text.slice(Math.max(0, s1 - 40), s1))) sc += 0.4;
      if (sc >= minScore) mk(s1, e2, Math.min(1, sc));
    }

    // Pass 3: initial + surname ("J. Smith")
    for (const m of text.matchAll(INITIAL_SURNAME)) {
      if (inGaz(m[2].toLowerCase())) mk(m.index, m.index + m[0].length, 0.7);
    }
    // Pass 4: parenthetical reveal ("V (Virtanen)")
    for (const m of text.matchAll(PAREN_NAME)) {
      if (inGaz(m[2].toLowerCase())) mk(m.index, m.index + m[0].length, 0.8);
    }

    // Pass 5: single name after a title/context keyword ("mrs korhonen", "patient Mikko")
    const allKw = new Set([...TITLE_WORDS, ...INTRO_WORDS]);
    for (let i = 0; i < words.length; i++) {
      if (!allKw.has(words[i][2].toLowerCase())) continue;
      for (let j = i + 1; j < Math.min(i + 3, words.length); j++) {
        const nl = words[j][2].toLowerCase();
        if (TITLE_WORDS.has(nl) || INTRO_WORDS.has(nl) || NAME_CONTEXT_WORDS.has(nl) || NAME_SKIP.has(nl)) continue;
        if (words[j][0] - words[j - 1][1] > 3) break;
        if (isAcronym(words[j][2])) break;   // MRN, DEA, ... not names
        if (inGaz(nl)) mk(words[j][0], words[j][1], 0.7);
        break;
      }
    }

    // Local dedup: highest score, keep non-overlapping
    cands.sort((a, b) => (b.confidence - a.confidence) || (a.start - b.start));
    const kept = [];
    for (const c of cands) {
      if (!kept.some((k) => c.start < k.end && c.end > k.start)) kept.push(c);
    }
    return kept;
  }

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

    // Layer 2h: gazetteer name scorer (names are aggressive-tier)
    if (sensitivity === "aggressive") {
      matches = matches.concat(detectNames(text));
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
    // Assign placeholders left-to-right so numbering reads in document order
    for (const d of [...detections].sort((a, b) => a.start - b.start)) {
      const key = d.value.toLowerCase();
      if (!valueToPlaceholder.has(key)) {
        counters[d.type] = (counters[d.type] || 0) + 1;
        valueToPlaceholder.set(key, `[${d.type}_${counters[d.type]}]`);
      }
    }
    // Replace right-to-left so indices stay valid
    let out = text;
    for (const d of [...detections].sort((a, b) => b.start - a.start)) {
      out = out.slice(0, d.start) + valueToPlaceholder.get(d.value.toLowerCase()) + out.slice(d.end);
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
      const cls = d.layer === "name" ? ' class="m-name"'
                : d.layer === "llm" ? ' class="m-llm"' : "";
      html += `<mark${cls} title="${esc(d.type)} (${d.layer})">${esc(text.slice(d.start, d.end))}</mark>`;
      cursor = d.end;
    }
    html += esc(text.slice(cursor));
    return html || '<span class="empty">(nothing yet)</span>';
  }

  function renderScrubbed(sanitized) {
    return esc(sanitized).replace(/\[([A-Z_]+_\d+)\]/g, '<span class="ph">[$1]</span>')
           || '<span class="empty">(nothing yet)</span>';
  }

  function renderTable(detections) {
    if (!detections.length) return '<p class="empty">No PII detected at this sensitivity level.</p>';
    let rows = "";
    for (const d of [...detections].sort((a, b) => a.start - b.start)) {
      const detectedBy = d.layer === "name"
        ? `<span class="layer-name">name&nbsp;scorer</span>`
        : d.checksum
          ? `<span class="layer-checksum">checksum&nbsp;${d.checksum}</span>`
          : "regex";
      rows += `<tr>
        <td><span class="type">${esc(d.type)}</span></td>
        <td class="val">${esc(d.value)}</td>
        <td>${esc(d.pattern)}</td>
        <td>${detectedBy}</td>
        <td><span class="conf-bar" style="width:${Math.round(d.confidence * 46)}px"></span>
            &nbsp;${d.confidence.toFixed(2)}</td>
      </tr>`;
    }
    return `<table><thead><tr>
      <th>Type</th><th>Value</th><th>Pattern</th><th>Detected by</th><th>Confidence</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  }

  // --- Layer 3 preview: what the local LLM catches beyond the deterministic layers ---
  // The browser can't run the model, so these deltas are precomputed offline
  // (scripts/compute_llm_extra.py) and keyed by the exact built-in example text.
  const LLM_EXTRA = window.PRESERVE_LLM_EXTRA || {};

  function lookupLlmExtra(text) {
    for (const [name, val] of Object.entries(window.PRESERVE_EXAMPLES || {})) {
      if (val === text) return LLM_EXTRA[name] || [];
    }
    return null; // not a built-in example
  }

  function renderLlmPanel(text, detections) {
    const meta = document.getElementById("llm-meta");
    const note = document.getElementById("llm-note");
    const hl = document.getElementById("llm-highlight");
    const chips = document.getElementById("llm-extra");
    if (!meta) return;

    const extra = lookupLlmExtra(text);
    if (extra === null) {
      meta.textContent = "";
      hl.innerHTML = "";
      chips.innerHTML = "";
      note.textContent = "Load a built-in example above to preview Layer 3 (the browser can't run the model).";
      return;
    }

    const merged = detections.concat(
      extra.map((e) => ({ ...e, pattern: "llm", layer: "llm", confidence: 0.9 }))
    );
    hl.innerHTML = highlight(text, merged);
    chips.innerHTML = extra.length
      ? extra.map((e) => `<span class="chip chip-llm">${esc(e.type)}: ${esc(e.value)}</span>`).join("")
      : "";
    meta.textContent = `Deterministic: ${detections.length} · local LLM adds: ${extra.length}`;
    const model = window.PRESERVE_LLM_MODEL || "Qwen3.5";
    note.textContent = extra.length
      ? `Precomputed offline with a local ${model} model. The browser runs no model and sends no data.`
      : "Layer 3 adds nothing here: the deterministic layers already caught everything.";
  }

  // --- Wire up ---
  const $ = (id) => document.getElementById(id);

  function run() {
    const text = $("input").value;
    const sensitivity = $("sensitivity").value;
    const sd = $("sens-detail");
    if (sd) sd.textContent = SENS_DETAIL[sensitivity] || "";
    const detections = detect(text, sensitivity);
    const { sanitized, summary } = scrub(text, detections);

    $("highlight").innerHTML = highlight(text, detections);
    $("scrubbed").innerHTML = renderScrubbed(sanitized);

    const chips = Object.entries(summary)
      .map(([t, n]) => `<span class="chip">${esc(t)} × ${n}</span>`).join("");
    $("summary").innerHTML = chips || '<span class="empty">No PII detected.</span>';
    const nameNote = sensitivity === "aggressive" ? ` + name scorer (${NAMES.countries} countries)` : "";
    $("stat").textContent =
      `${detections.length} item(s) detected · ${text.length} chars · ${PATTERNS.length} patterns active at "${sensitivity}"${nameNote}`;
    $("table").innerHTML = renderTable(detections);
    renderLlmPanel(text, detections);
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
