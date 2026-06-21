# DeepInfra Privacy Posture Analysis

**Date of Analysis:** 2026-03-29
**Analyst:** Automated policy review
**Version:** 1.0
**Classification:** Internal Use

---

## 1. Executive Summary

DeepInfra is a managed LLM inference provider that offers an OpenAI-compatible API for running open-weight and third-party models. This analysis examines their privacy posture based on publicly available policies, documentation, and trust center disclosures.

**Key finding:** DeepInfra maintains strong privacy defaults relative to its peers. Input and output data are held only in memory during inference and are not persisted to disk under normal operation. The provider explicitly commits to not training on user submissions and limits logging to metadata only.

**However, notable gaps exist.** A vaguely scoped debugging exception allows data inspection without clear time limits or opt-out mechanisms. Routing requests through third-party models (Google Gemini, Anthropic Claude) silently escalates privacy exposure to those providers' separate policies. Memory-only storage, while architecturally sound, is unverifiable by customers. These gaps do not invalidate the provider's utility, but organizations handling sensitive data should implement the compensating controls described in Section 6.

---

## 2. Provider Profile

| Attribute | Detail |
|---|---|
| **Provider** | DeepInfra |
| **Service** | Managed LLM inference (text generation, image generation, embeddings) |
| **API Endpoint** | `https://api.deepinfra.com/v1/openai` |
| **API Compatibility** | OpenAI-compatible (drop-in replacement for most client libraries) |
| **Authentication** | Bearer token via `DEEPINFRA_API_KEY` environment variable |
| **Infrastructure** | Hosted on AWS and GCP |
| **Payment Processing** | Stripe |
| **Pricing Model** | Pay-per-token (input/output priced separately per model) |
| **Certifications** | SOC 2, ISO 27001 |
| **Compliance Posture** | GDPR and HIPAA compliance measures |
| **Trust Center** | [trust.deepinfra.com](https://trust.deepinfra.com) |

---

## 3. Policy Analysis

### 3.1 Input/Output Not Stored on Disk

> **Claim:** Input data is not stored on disk. It is held in memory only during inference and deleted afterward. Output data is similarly not stored and is transmitted then removed from memory.

**Assessment:** This is a strong architectural commitment. Memory-only processing significantly reduces the attack surface for data-at-rest breaches. If implemented correctly, it means that a disk compromise, snapshot, or backup restoration would not expose prompt or completion content.

**Residual Risk:** Memory-only processing is an implementation claim that customers cannot independently verify. Memory can be swapped to disk by the operating system, dumped during crashes, or captured by hypervisor-level snapshots in cloud environments. The policy also carves out two exceptions: image generation outputs may be retained briefly for accessibility, and bulk inference requests may be stored temporarily in encrypted form on disk. The scope and duration of "briefly" and "temporarily" are not defined.

**Severity:** Medium

---

### 3.2 Only Metadata Logged

> **Claim:** Only metadata is logged: request IDs, inference costs, and sampling parameters. Prompt text and response content are not logged.

**Assessment:** This is best-practice behavior for an inference provider. Logging only metadata means that a compromise of log infrastructure would not expose the content of customer interactions. It also limits the potential for insider access to sensitive data.

**Residual Risk:** Metadata alone can be revealing. Request timing, model selection, token counts, and sampling parameters can disclose usage patterns, the nature of workloads, and approximate prompt/response lengths. An adversary with access to metadata could infer what types of tasks are being performed, when they occur, and at what scale. This is a well-documented limitation of metadata-only collection regimes.

**Severity:** Low

---

### 3.3 Won't Train on Submissions

> **Claim:** "We will not store, sell, or train using this data unless we have your explicit consent." Training occurs only if the user explicitly requests fine-tuning.

**Assessment:** This is the most important privacy commitment for organizations using third-party inference. It means that proprietary prompts, internal data, and customer information sent through the API will not become part of DeepInfra's training corpus. The consent mechanism is appropriately scoped to fine-tuning requests, which are an affirmative action by the user.

**Residual Risk:** The commitment is contractual, not technical. There is no cryptographic or architectural guarantee that data cannot be used for training. Policy changes could weaken this commitment prospectively. Additionally, the debugging exception (analyzed in 3.7) creates a pathway through which data could theoretically be observed by personnel, even if not used for training.

**Severity:** Low

---

### 3.4 SOC 2 / ISO 27001 Certified

> **Claim:** DeepInfra holds SOC 2 and ISO 27001 certifications.

**Assessment:** These certifications demonstrate that DeepInfra has undergone external audits of its security controls. SOC 2 covers security, availability, processing integrity, confidentiality, and privacy. ISO 27001 covers information security management systems. Together, they provide reasonable assurance that baseline security practices are in place.

**Residual Risk:** Certifications attest to the existence of controls, not to their effectiveness against sophisticated threats. SOC 2 reports come in two types: Type I (controls exist at a point in time) and Type II (controls operated effectively over a period). The policy does not specify which type was obtained. ISO 27001 certification scope may not cover all services. Customers should request the SOC 2 report directly to verify scope and type.

**Severity:** Low

---

### 3.5 Third-Party Model Caveat

> **Claim:** Google models (Gemini) are subject to Google's own policies. Anthropic models are subject to Anthropic's policies. All other models: no data shared with third parties.

**Assessment:** This is an honest disclosure, but it represents a significant privacy escalation that may not be obvious to users. When a customer selects a Google or Anthropic model through DeepInfra's API, their data is forwarded to that provider and becomes subject to a different (and potentially less favorable) privacy regime. The customer's contractual relationship is with DeepInfra, but their data is governed by a third party's terms.

**Residual Risk:** Users may select third-party models without understanding the privacy implications. Google and Anthropic have their own data retention, training, and logging policies that may differ substantially from DeepInfra's. DeepInfra's privacy commitments (no storage, no training, metadata-only logging) do not bind these third parties. There is no indication that DeepInfra negotiates data processing agreements with these providers on behalf of its customers.

**Severity:** High

---

### 3.6 30-Day Post-Deletion Retention

> **Claim:** After account deletion, data is stored for 30 days for fraud prevention, then deleted completely.

**Assessment:** A 30-day retention window after account deletion is a standard industry practice. It allows the provider to address chargebacks, investigate abuse, and comply with legal obligations. Complete deletion after this period is a reasonable commitment.

**Residual Risk:** The scope of "data" retained during this period is not specified. It could include account metadata only, or it could include any temporarily stored content (e.g., from the bulk inference or image generation exceptions). If a customer sends sensitive data and then deletes their account, that data may persist for up to 30 days. For organizations subject to strict data lifecycle requirements, this window may need to be addressed contractually.

**Severity:** Low

---

### 3.7 Debugging Exception

> **Claim:** Data may be inspected "when necessary for debugging or security purposes." The Terms of Service further state: "might store some Submissions for a limited time for the purpose of debugging our Services."

**Assessment:** This is the most concerning gap in DeepInfra's privacy posture. The exception is vaguely scoped along every relevant dimension: who can invoke it, what data can be accessed, under what circumstances, for how long, and with what oversight. The phrase "when necessary" is subjective and provides no meaningful constraint. The ToS language ("might store some Submissions for a limited time") does not define "limited time" or "some."

**Residual Risk:** In practice, this exception could authorize any DeepInfra employee with appropriate access to inspect prompt and response content at any time, for any reason they deem related to debugging or security. There is no disclosed audit trail for when this exception is invoked, no notification to affected customers, no time limit on retention under this exception, and no opt-out mechanism. This effectively creates an open-ended carve-out from the no-storage commitment.

**Severity:** High

---

### 3.8 GDPR / HIPAA Compliance Claims

> **Claim:** DeepInfra implements GDPR and HIPAA compliance measures.

**Assessment:** The use of "compliance measures" rather than "compliance" is important. This language indicates that DeepInfra has implemented controls aligned with these frameworks but may not have undergone formal HIPAA audits or appointed EU-based data protection officers. For GDPR, the key question is whether DeepInfra offers a Data Processing Agreement (DPA). For HIPAA, the key question is whether they will sign a Business Associate Agreement (BAA).

**Residual Risk:** "Compliance measures" is not the same as compliance. Organizations subject to GDPR that use DeepInfra as a processor must ensure a DPA is in place. Organizations subject to HIPAA must ensure a BAA is signed before transmitting any protected health information (PHI). The public documentation does not confirm the availability of either agreement. Without these instruments, using DeepInfra for regulated workloads carries legal risk.

**Severity:** Medium

---

## 4. Gap Analysis Summary

| Policy Area | Claim | Gap | Residual Risk | Severity |
|---|---|---|---|---|
| Data storage | Input/output not stored on disk | Exceptions for images and bulk inference; memory swapping unaddressed | Data-at-rest exposure via OS swap, crash dumps, or cloud snapshots | Medium |
| Logging | Only metadata logged | Metadata includes timing, model, token counts | Usage pattern inference; workload characterization | Low |
| Training | Won't train without consent | Contractual only; no technical enforcement | Policy change risk; debugging exception overlap | Low |
| Certifications | SOC 2 / ISO 27001 | Report type and scope undisclosed | Controls may not cover all services; point-in-time vs. operational | Low |
| Third-party models | Google/Anthropic subject to own policies | No DPA negotiated on customer's behalf; no UI warning | Silent privacy escalation; customer data under foreign terms | High |
| Account deletion | 30-day retention for fraud prevention | Scope of retained data undefined | Sensitive content may persist for up to 30 days post-deletion | Low |
| Debugging | Data may be inspected for debugging | No time limit, no audit trail, no notification, no opt-out | Unrestricted personnel access to prompt/response content | High |
| Regulatory | GDPR/HIPAA "compliance measures" | DPA/BAA availability not confirmed | Legal exposure for regulated workloads | Medium |

---

## 5. Key Findings

### Finding 1: The Debugging Exception Is the Most Concerning Gap

The debugging exception effectively negates the no-storage commitment for any data that DeepInfra personnel decide to inspect. It has no defined scope, no time limit, no audit trail, and no customer notification or opt-out. While debugging exceptions are common across providers, DeepInfra's is unusually broad in its language and lacks the compensating controls (such as access logging or data minimization requirements) that would limit its impact.

### Finding 2: Third-Party Model Routing Is a Hidden Privacy Escalation

When a user selects a Google Gemini or Anthropic Claude model through DeepInfra's API, their request is forwarded to that provider under that provider's terms. This is disclosed in the policy but is unlikely to be noticed by developers who assume DeepInfra's privacy commitments apply uniformly. The practical effect is that a user who chose DeepInfra for its privacy posture may unknowingly send data to a provider with different retention and training practices.

### Finding 3: Memory-Only Storage Is Strong but Unverifiable

The commitment to hold data only in memory during inference is architecturally sound and represents a meaningful privacy advantage over providers that log prompts and completions to disk. However, customers have no mechanism to verify this claim. Operating system behavior (swap, core dumps), hypervisor-level operations, and cloud provider snapshots can all persist memory contents to disk without DeepInfra's application layer being aware.

### Finding 4: Metadata Alone Can Be Revealing

Even without logging prompt or response content, the metadata that DeepInfra does collect (request IDs, inference costs, sampling parameters, and implicitly, timestamps and model identifiers) can reveal significant information about customer workloads. Token counts approximate prompt and response length. Model selection indicates task type. Request timing reveals work patterns. For organizations concerned about competitive intelligence or operational security, metadata exposure should not be dismissed.

---

## 6. Recommendations for Organizations

### Critical Priority

- **Always scrub PII client-side before sending requests.** Do not rely on any provider's privacy commitments as a substitute for data minimization. Implement automated PII detection and redaction in your API client layer. This is the single most effective control regardless of provider behavior.

- **Avoid third-party models through DeepInfra if privacy is paramount.** If your threat model requires the privacy posture described in DeepInfra's policies, restrict usage to models that DeepInfra hosts directly (open-weight models). Do not route requests through DeepInfra to Google Gemini or Anthropic Claude, as those requests fall under those providers' separate and potentially less favorable policies.

### High Priority

- **Request a Data Processing Agreement (DPA) for GDPR compliance.** If your organization is subject to GDPR and uses DeepInfra as a data processor, a DPA is a legal requirement under Article 28. Contact DeepInfra directly to confirm availability and negotiate terms.

- **Request written clarification on the debugging exception.** Ask DeepInfra to specify: (a) under what circumstances the exception is invoked, (b) who has access, (c) what data can be accessed, (d) how long it is retained, (e) whether an audit trail exists, and (f) whether customers are notified. Document their response and incorporate it into your risk assessment.

### Medium Priority

- **Monitor the policy page for changes.** DeepInfra's privacy commitments are documented in their Privacy Policy and Terms of Service. These can change at any time. Implement periodic (e.g., monthly) review of these pages or use a web monitoring service to detect changes.

- **Implement client-side audit logging.** Maintain your own logs of what data was sent to DeepInfra, when, and to which model. This provides an independent record for compliance purposes and enables you to assess exposure if a breach or policy change occurs. Do not log sensitive content in these audit logs; log hashes or references instead.

### Low Priority

- **Use API keys with minimal permissions and rotate regularly.** Treat the `DEEPINFRA_API_KEY` as a sensitive credential. Store it in a secrets manager, not in code or environment files committed to version control. Rotate keys on a regular schedule (e.g., quarterly) and immediately upon personnel changes.

- **Consider request padding to obscure token count patterns.** If metadata exposure is within your threat model, adding random padding to requests can obscure the true token count and make usage pattern analysis less reliable. This is a niche control appropriate only for high-sensitivity workloads.

---

## 7. Methodology

This analysis was conducted through review of the following publicly available sources:

1. **Privacy Policy Review:** Examination of DeepInfra's published privacy policy, with attention to data collection, storage, retention, sharing, and processing commitments.

2. **Terms of Service Review:** Examination of DeepInfra's Terms of Service for provisions affecting data rights, debugging exceptions, and liability limitations.

3. **Documentation Review:** Review of DeepInfra's API documentation, including authentication mechanisms, endpoint specifications, and model availability.

4. **Trust Center Review:** Examination of materials published at trust.deepinfra.com, including certification claims and compliance posture disclosures.

The analysis applies a structured framework: for each policy claim, the assessment identifies what the claim means in practice, what it does not cover, and the residual risk to an organization relying on that claim. Severity ratings reflect the potential impact on data confidentiality assuming an organization is sending moderately sensitive business data through the API.

**Limitations:** This analysis is based on publicly available documentation only. It does not include penetration testing, infrastructure inspection, review of SOC 2 reports, or direct communication with DeepInfra personnel. Actual implementation may differ from documented policy. Organizations with high-sensitivity workloads should conduct their own due diligence, including requesting SOC 2 Type II reports and negotiating contractual protections.

---

*This document is provided for informational purposes and does not constitute legal advice. Organizations should consult qualified legal counsel for compliance decisions.*
