# Privacy Threat Model and Framework for LLM Inference Queries to External Providers

---

## 1. Introduction

Large Language Model (LLM) inference via external providers has become a standard component of modern software systems. Applications route natural-language queries to hosted endpoints operated by third parties such as OpenAI, Anthropic, Google, DeepInfra, Together AI, and others. This architecture introduces a class of privacy risks that differ fundamentally from traditional API consumption: the payloads themselves are unstructured natural language, frequently containing sensitive information that users did not consciously intend to disclose.

The stakes are significant. A single inference request may contain personally identifiable information (PII), proprietary business logic, medical records, legal communications, or financial data. Unlike structured database queries, prompt content is difficult to audit, difficult to redact automatically, and often impossible to recall once transmitted.

This document provides a comprehensive taxonomy of privacy threats associated with external LLM inference. It is intended for security architects, privacy engineers, compliance officers, and application developers who integrate third-party LLM services. The framework covers threat actors, assets at risk, attack vectors, provider evaluation criteria, and layered client-side defenses.

---

## 2. Threat Model

### 2.1 Actors

| Actor | Role | Motivation |
|---|---|---|
| **End user** | The human composing or triggering the prompt | May unknowingly include PII; has an expectation of privacy |
| **Application developer** | Builds the system that constructs and sends inference requests | Responsible for data minimization; may inadvertently embed sensitive context |
| **Application (client software)** | The runtime that serializes and transmits the request | Attack surface for credential theft, prompt logging, and local data leakage |
| **Network intermediaries** | ISPs, CDNs, corporate proxies, DNS resolvers | Can observe connection metadata; may log or cache traffic |
| **Inference provider** | The company operating the inference endpoint (e.g., DeepInfra, Together AI) | Processes prompt content; subject to internal policy, legal compulsion, and breach risk |
| **Model licensor** | The entity that created and licensed the model (e.g., Meta for Llama, Google for Gemma) | May impose data-sharing requirements in license terms; may receive telemetry |
| **Third-party subprocessors** | Cloud infrastructure (AWS, GCP), payment processors (Stripe), analytics services | Store or process data on behalf of the provider; expand the trust perimeter |
| **External adversaries** | Hackers, criminal organizations, nation-state actors | Seek to intercept, exfiltrate, or correlate inference data for intelligence or profit |
| **Legal/regulatory authorities** | Courts, law enforcement, regulatory agencies | May compel disclosure of stored data via subpoena, warrant, or regulatory order |

### 2.2 Assets at Risk

| Asset | Sensitivity | Example |
|---|---|---|
| **Prompt content** | High | The raw text of the user's query, including instructions, context, and embedded data |
| **PII within prompts** | Critical | Names, email addresses, Social Security numbers, medical diagnoses, financial account numbers |
| **Response content** | High | Model-generated text that may contain inferred PII, sensitive conclusions, or reproduced input data |
| **Metadata** | Medium-High | Request timestamps, token counts, model identifiers, IP addresses, API key associations, usage frequency |
| **API credentials** | Critical | Bearer tokens and API keys that authenticate requests and link all queries to an identity |
| **Conversation history / session state** | High | Multi-turn dialogue context that accumulates sensitive information across interactions |
| **System prompts** | Medium-High | Application-level instructions that may reveal proprietary logic, internal policies, or data schemas |

### 2.3 Trust Boundaries

The following text diagram illustrates the principal trust boundaries in a typical external LLM inference architecture.

```
+------------------+       +-------------------+       +---------------------------+
|   USER MACHINE   |       |     NETWORK       |       |    INFERENCE PROVIDER      |
|                  |       |                   |       |                           |
|  +------------+  |       |  +-------------+  |       |  +---------------------+  |
|  |  End User  |  |       |  | ISP / Corp  |  |       |  |   API Gateway       |  |
|  +-----+------+  |       |  |   Proxy     |  |       |  +----------+----------+  |
|        |         |       |  +------+------+  |       |             |              |
|  +-----v------+  |       |         |         |       |  +----------v----------+  |
|  | Application|--+--TLS--+-->  DNS Resolver  |       |  |  Request Router /   |  |
|  | (Client)   |  |       |         |         |       |  |  Load Balancer      |  |
|  +-----+------+  |       |  +------v------+  |       |  +----------+----------+  |
|        |         |       |  |   CDN Edge   |--+--TLS-+->            |              |
|  +-----v------+  |       |  +-------------+  |       |  +----------v----------+  |
|  | Local Logs |  |       |                   |       |  |  Inference Engine    |  |
|  | & Audit    |  |       +-------------------+       |  |  (GPU Cluster)       |  |
|  +------------+  |                                   |  +----------+----------+  |
|                  |          TRUST BOUNDARY 1         |             |              |
+------------------+     (User Machine <-> Network)    |  +----------v----------+  |
                                                       |  |   Model Runtime     |  |
                          TRUST BOUNDARY 2             |  |   (Llama, Gemma,    |  |
                     (Network <-> Provider)            |  |    Mistral, etc.)   |  |
                                                       |  +----------+----------+  |
                                                       |             |              |
                                                       |  +----------v----------+  |
                                                       |  |  Logging / Metrics  |  |
                                                       |  +----------+----------+  |
                                                       |             |              |
                                                       |  +----------v----------+  |
                                                       |  |  Subprocessors      |  |
                                                       |  |  (AWS, GCP, Stripe) |  |
                                                       |  +---------------------+  |
                                                       |                           |
                                                       +---------------------------+
                                                          TRUST BOUNDARY 3
                                                     (Provider <-> Subprocessors)
```

**Trust Boundary 1 (User Machine to Network):** Data leaves the user's physical and logical control. TLS protects content in transit, but metadata (DNS queries, IP addresses, connection timing) is visible to intermediaries.

**Trust Boundary 2 (Network to Provider):** The provider receives full plaintext of the request after TLS termination. From this point, privacy depends entirely on the provider's policies, technical controls, and legal environment.

**Trust Boundary 3 (Provider to Subprocessors):** The provider may delegate storage, processing, or billing to third parties. Each subprocessor extends the trust perimeter and introduces additional jurisdictional exposure.

---

## 3. Privacy Risk Categories

### 3.1 Data in Transit

Data in transit between the client and the inference provider traverses multiple network hops, each presenting an opportunity for observation or interception.

**TLS Encryption**

All major inference providers require HTTPS (TLS 1.2 or 1.3). Standard TLS protects the content of HTTP requests and responses from passive network observers. However, several caveats apply:

- **Standard TLS vs. mTLS:** Standard TLS authenticates only the server. Mutual TLS (mTLS) additionally authenticates the client, preventing impersonation attacks. Most inference APIs use standard TLS with API key authentication rather than mTLS.
- **TLS termination point:** Many providers terminate TLS at a load balancer or CDN edge node, meaning plaintext is available within the provider's internal network. The distance between TLS termination and the inference engine is a trust assumption.
- **Protocol version:** TLS 1.2 with forward-secret cipher suites is the minimum acceptable configuration. TLS 1.3 eliminates several classes of downgrade attacks.

**Certificate Pinning**

Certificate pinning binds the client to a specific certificate or public key, preventing interception by a compromised or rogue certificate authority. This is rarely implemented in LLM API clients and is impractical when providers rotate certificates frequently.

**DNS Leakage**

Even with TLS, the DNS query for `api.deepinfra.com` or `api.openai.com` is typically sent in plaintext. This reveals to the DNS resolver (and any network observer) that the client is using a specific inference provider. Combined with timing analysis, this can reveal usage patterns.

**CDN and Proxy Intermediaries**

Some providers route traffic through CDNs (Cloudflare, AWS CloudFront) that terminate TLS at edge nodes distributed globally. While this improves latency, it means that plaintext request data is present in memory at geographically distributed points of presence, each subject to the CDN operator's jurisdiction and security posture.

**Mitigations**

| Mitigation | Effect | Complexity |
|---|---|---|
| Verify TLS certificate chain | Prevents trivial MITM | Low |
| Use DNS-over-HTTPS (DoH) or DNS-over-TLS (DoT) | Encrypts DNS queries | Low |
| Route through VPN or Tor | Obscures client IP and DNS | Medium |
| Certificate pinning | Prevents CA compromise MITM | High |
| Confirm provider TLS termination architecture | Understand internal plaintext exposure | Policy |

### 3.2 Data at Rest (Provider Side)

Once the inference provider receives a request, its handling of that data at rest becomes the dominant privacy concern. Provider policies vary widely and are often ambiguous.

**Request Logging Policies**

Providers log requests for various purposes: billing, abuse detection, debugging, and performance monitoring. The critical distinction is between logging metadata (timestamps, token counts, model ID) and logging content (the actual prompt and response text).

- Some providers log only metadata and explicitly discard prompt content after inference completes.
- Others retain prompt content for a defined period (30 days, 90 days) for debugging purposes.
- "Debugging exceptions" are common: a provider may claim not to log content but reserve the right to do so when investigating errors or abuse reports.

**Model Training on User Data**

Some providers reserve the right to use submitted data for model fine-tuning or evaluation. This is the highest-risk data-at-rest scenario because it means prompt content becomes embedded in model weights, making deletion effectively impossible.

Key questions:
- Does the provider train on API submissions by default?
- Can training be opted out of? Is the opt-out per-account or per-request?
- Does the provider distinguish between free-tier and paid-tier data usage?

**Backup and Retention Policies**

Even providers that claim prompt content is memory-only during inference may maintain system-level backups that capture request data. Questions to ask:

- Are backups encrypted at rest?
- What is the backup retention period?
- Do backups include request content or only metadata?
- What is the post-deletion retention period (time between deletion request and actual purge from all systems including backups)?

**Subprocessor Storage**

Providers that run on AWS or GCP implicitly store data on those platforms' infrastructure. This introduces the cloud provider's security posture, jurisdiction, and access controls as additional variables.

**Mitigations**

| Mitigation | Effect | Complexity |
|---|---|---|
| Review and compare provider privacy policies | Identify high-risk providers | Low |
| Execute a Data Processing Agreement (DPA) | Contractual obligation for data handling | Medium |
| Minimize prompt content (send only what is necessary) | Reduce exposure surface | Medium |
| Use providers with SOC 2 / ISO 27001 certification | Verified security controls | Policy |
| Prefer providers with zero-retention content policies | Eliminate data-at-rest risk | Policy |

### 3.3 PII Leakage

PII leakage occurs when personally identifiable information is transmitted to the inference provider, intentionally or (more commonly) unintentionally.

**Accidental Inclusion of PII in Prompts**

Applications that incorporate user-generated content, database records, emails, or documents into prompts frequently transmit PII without explicit awareness. Common scenarios:

- A summarization tool that sends a full email thread including sender names, addresses, and phone numbers.
- A code assistant that receives a configuration file containing database connection strings with credentials.
- A customer support bot that includes customer records in the context window.

**Types of PII at Risk**

| PII Type | Example | Risk Level |
|---|---|---|
| Full names | "John Smith" | Medium |
| Email addresses | "john.smith@company.com" | Medium |
| Phone numbers | "+1-555-867-5309" | Medium |
| Social Security numbers | "123-45-6789" | Critical |
| Medical records / diagnoses | "Patient diagnosed with Type 2 diabetes" | Critical |
| Financial data | "Account #4532-XXXX-XXXX-1234, balance $45,230" | Critical |
| Physical addresses | "123 Main Street, Springfield, IL 62704" | Medium |
| Dates of birth | "DOB: 03/15/1985" | Medium |
| Biometric data | Voiceprint features, facial recognition embeddings | Critical |
| Authentication credentials | Passwords, tokens, private keys | Critical |

**Contextual PII**

Individual data points that are not PII in isolation can become identifying when combined. A prompt containing a job title, employer name, and city of residence may uniquely identify an individual even without an explicit name. This "mosaic effect" is difficult to detect with pattern-based PII scrubbers.

**Mitigations**

| Mitigation | Effect | Complexity |
|---|---|---|
| Client-side PII detection and scrubbing | Remove PII before transmission | Medium |
| Reversible tokenization (placeholder substitution) | Maintain query utility while removing PII | High |
| Synthetic data substitution | Replace real PII with realistic but fake equivalents | High |
| Prompt templates that exclude raw data | Architectural separation of data and instructions | Medium |
| Input validation and content classification | Flag prompts containing sensitive categories | Medium |

### 3.4 Metadata Exposure

Even when prompt content is perfectly protected, metadata can reveal sensitive information about user behavior, identity, and intent.

**Request Timing Correlation**

The timing of inference requests can reveal activity patterns. An analyst observing that a user makes requests every weekday at 9:00 AM and 5:00 PM can infer work schedule patterns. Burst patterns may correlate with specific events (e.g., a spike in legal-query activity before a lawsuit filing).

**Token Count Analysis**

Token counts for requests and responses are typically logged by all providers for billing. These counts reveal the size and complexity of queries. A sudden increase in token count may indicate that a user has begun submitting large documents (contracts, medical records) for analysis.

**Model Selection Patterns**

The choice of model (e.g., switching from a general model to a medical or legal fine-tune) reveals the domain of the user's activity.

**IP Address and Geolocation**

The client IP address is visible to the provider and reveals approximate geographic location. For corporate users behind a NAT, it identifies the organization. For individual users, it may identify the household.

**API Key Association**

API keys link all queries from a key to a single identity. If the key is associated with an individual's account, the provider can construct a complete history of that individual's inference activity.

**Usage Pattern Analysis**

Aggregate patterns (frequency, timing, model selection, token volume) constitute a behavioral fingerprint that may be identifying even if individual requests are anonymized.

**Mitigations**

| Mitigation | Effect | Complexity |
|---|---|---|
| Request batching and scheduling | Obscure timing patterns | Medium |
| Token count padding (add dummy tokens) | Obscure query/response size | Medium |
| VPN or proxy routing | Mask IP address | Low |
| API key rotation | Limit linkability window | Low |
| Multiple provider accounts | Fragment usage history | Medium |
| Request routing through an aggregation proxy | Decouple client identity from provider identity | High |

### 3.5 Model Provider Trust

The fundamental privacy challenge with external inference is that trust is placed in the provider's policies rather than in technical guarantees. Policies are promises; they can change, be misunderstood, or be violated.

**Policy vs. Technical Enforcement**

No widely available inference provider offers cryptographic guarantees that prompt content is not stored or logged. Confidential computing (e.g., Intel SGX, AMD SEV) could provide such guarantees, but adoption in inference services remains minimal. In practice, the user trusts the provider's word.

**Jurisdiction and Legal Compulsion**

A provider incorporated in the United States is subject to US law, including the CLOUD Act, which permits compelled disclosure of data stored abroad. A provider in the EU is subject to GDPR. The intersection of these frameworks creates compliance complexity, particularly when the user, provider, and subprocessors are in different jurisdictions.

**Policy Change Risk**

Privacy policies can be updated unilaterally. A provider that does not train on user data today may change that policy tomorrow. Retroactive application of new policies to previously submitted data is a realistic risk.

**Breach Notification Obligations**

In the event of a data breach, notification timelines and obligations vary by jurisdiction. Understanding the provider's breach notification commitments is essential for the user's own compliance obligations.

**Third-Party Model Routing**

Some providers host models from other companies (e.g., DeepInfra hosting Google's Gemma or Meta's Llama). The relationship between the provider and the model licensor may involve data sharing, telemetry, or usage reporting that is not clearly disclosed to the end user.

**Mitigations**

| Mitigation | Effect | Complexity |
|---|---|---|
| Execute a DPA with explicit terms | Contractual protection against policy changes | Medium |
| Multi-provider strategy | Reduce concentration risk | Medium |
| Monitor provider policy changes | Early warning of risk changes | Low |
| Prefer providers with transparency reports | Visibility into legal compulsion frequency | Policy |
| Client-side safeguards (PII scrubbing) | Defense-in-depth regardless of provider trust | Medium |
| Evaluate confidential computing options | Technical enforcement of data isolation | High |

---

## 4. Attack Vectors and Mitigations

| Attack Vector | Category | Description | Likelihood | Impact | Mitigations |
|---|---|---|---|---|---|
| **Man-in-the-middle (network interception)** | Data in Transit | Attacker intercepts TLS connection via compromised CA, rogue proxy, or downgrade attack | Low (with TLS 1.3) | Critical | Certificate validation, certificate pinning, TLS 1.3 enforcement, HSTS |
| **Insider threat at provider** | Data at Rest | Malicious or negligent employee at the inference provider accesses stored prompt data | Low-Medium | Critical | Provider SOC 2 controls, access logging, least-privilege policies, DPA with audit rights |
| **Legal compulsion / subpoena** | Model Provider Trust | Law enforcement or regulatory body compels the provider to disclose stored request data | Medium | High | Data minimization (send less), prefer providers with zero-retention policies, geographic jurisdiction selection |
| **Provider policy change** | Model Provider Trust | Provider updates privacy policy to permit training on user data or extended retention | Medium | High | DPA with change notification clauses, multi-provider strategy, continuous policy monitoring |
| **Prompt injection extracting prior PII** | PII Leakage | Adversarial input causes the model to reproduce PII from earlier in the conversation or from other users' sessions | Medium | High | Session isolation, input sanitization, output filtering, PII scrubbing before submission |
| **Model memorization (training data leakage)** | PII Leakage | Model reproduces verbatim training data containing PII when prompted with related context | Low-Medium | High | Use models with documented deduplication and privacy controls, output PII scanning, prefer models not trained on user data |
| **Metadata correlation attack** | Metadata Exposure | Adversary correlates request timing, token counts, and model selection to identify users or infer activity | Medium | Medium | Request batching, token padding, VPN, API key rotation, aggregation proxy |
| **API key theft** | Credential Compromise | Attacker obtains API key from source code repository, client-side code, or compromised developer machine | Medium-High | Critical | Key rotation, environment variable storage, secrets management (Vault, AWS Secrets Manager), key scoping and rate limiting |
| **DNS-based traffic analysis** | Data in Transit | Adversary monitors DNS queries to determine which inference providers a user contacts and when | Medium | Low-Medium | DNS-over-HTTPS (DoH), DNS-over-TLS (DoT), VPN, local DNS caching |
| **Provider data breach** | Data at Rest | External attacker compromises the provider's infrastructure and exfiltrates stored data | Low | Critical | Prefer providers with minimal data retention, DPA with breach notification SLA, client-side PII scrubbing as defense-in-depth |
| **Third-party model data sharing** | Model Provider Trust | Model licensor receives usage data or telemetry from the hosting provider without clear user disclosure | Medium | Medium | Review provider terms regarding hosted third-party models, prefer open-weight models with clear licensing, request written confirmation of data flows |
| **Session reconstruction from logs** | Data at Rest | Attacker or insider reconstructs full conversation history from provider-side logs | Low-Medium | High | Prefer providers with content-free logging, avoid multi-turn sessions when possible, rotate session identifiers |
| **Side-channel timing attack** | Metadata Exposure | Adversary infers prompt content characteristics from response latency patterns | Low | Low-Medium | Response padding, fixed-delay responses (impractical for most applications) |
| **Compromised CDN edge node** | Data in Transit | Attacker compromises a CDN point of presence where TLS is terminated | Low | High | Prefer providers with end-to-end encryption to origin, avoid CDN-terminated TLS where possible |
| **Cross-tenant data leakage** | Data at Rest | Bug in multi-tenant inference infrastructure leaks data between customers | Low | Critical | Prefer providers with strong tenant isolation architecture, monitor for anomalous response content |

---

## 5. Provider Comparison Framework

### 5.1 Scoring Rubric

Each category is scored on a 1-5 scale:

| Score | Meaning |
|---|---|
| 1 | No protection or no information available |
| 2 | Minimal protection; significant gaps |
| 3 | Adequate protection; meets baseline expectations |
| 4 | Strong protection; exceeds baseline |
| 5 | Best-in-class; technical enforcement or cryptographic guarantees |

### 5.2 Evaluation Categories

| # | Category | Description | What "5" Looks Like |
|---|---|---|---|
| 1 | **Transport encryption** | TLS version, cipher suites, certificate management | TLS 1.3 enforced, strong cipher suites only, short certificate rotation |
| 2 | **Storage/logging policy** | What is logged (metadata vs. content) and for how long | No content logging; metadata-only with short retention; documented and auditable |
| 3 | **Training data usage policy** | Whether user submissions are used for model training | Explicit opt-out by default; contractual guarantee; no retroactive changes |
| 4 | **Security certifications** | Independent security audits and certifications | SOC 2 Type II + ISO 27001 + annual penetration testing with published results |
| 5 | **Data residency controls** | Ability to specify geographic region for data processing | User-selectable region; single-jurisdiction processing; documented data flow |
| 6 | **Breach notification policy** | Committed timeline and process for breach notification | 72-hour notification SLA; named contact; documented incident response process |
| 7 | **Transparency reporting** | Publication of government data requests and compliance statistics | Annual transparency report; warrant canary; documented legal process requirements |
| 8 | **Third-party model handling** | Disclosure and controls for models hosted from other licensors | Clear documentation of data flows to model licensors; opt-out available; no hidden telemetry |
| 9 | **DPA availability** | Availability and terms of Data Processing Agreement | Standard DPA available; customizable terms; GDPR-compliant; audit rights included |
| 10 | **Debugging exception clarity** | Clarity about when and how the provider may access content for debugging | No debugging exceptions, or narrowly scoped with time limits, user notification, and audit trail |

### 5.3 Blank Template

| Category | Provider A | Provider B | Provider C |
|---|---|---|---|
| Transport encryption | | | |
| Storage/logging policy | | | |
| Training data usage policy | | | |
| Security certifications | | | |
| Data residency controls | | | |
| Breach notification policy | | | |
| Transparency reporting | | | |
| Third-party model handling | | | |
| DPA availability | | | |
| Debugging exception clarity | | | |
| **Total (out of 50)** | | | |

### 5.4 Example: DeepInfra

| Category | Score | Notes |
|---|---|---|
| Transport encryption | 4 | Standard HTTPS/TLS; no documented mTLS option |
| Storage/logging policy | 4 | Input/output not stored on disk; memory-only during inference; only metadata logged |
| Training data usage policy | 4 | Will not train on submissions unless explicit consent is given |
| Security certifications | 5 | SOC 2 + ISO 27001 certified |
| Data residency controls | 3 | AWS/GCP infrastructure; limited region selection documentation |
| Breach notification policy | 3 | Standard notification obligations; no published SLA timeline |
| Transparency reporting | 2 | No published transparency report identified |
| Third-party model handling | 2 | Caveat for Google/Anthropic models: data may be subject to those companies' terms; insufficient clarity on data flows |
| DPA availability | 3 | DPA available; standard terms |
| Debugging exception clarity | 2 | Vague "may store submissions briefly" for debugging; no defined time limit or notification process |
| **Total (out of 50)** | **32** | Solid baseline with notable gaps in third-party model transparency and debugging exception specificity |

**DeepInfra Summary Assessment:**

DeepInfra presents a strong security posture for first-party model hosting (Llama, Mistral, etc.), with memory-only processing and SOC 2/ISO 27001 certification. The primary concerns are: (1) the 30-day post-deletion retention period, which means data traces may persist after an account deletion request; (2) the vague debugging exception, which creates an undefined window during which content may be stored; and (3) the third-party model caveat, which means that prompts sent to Google or Anthropic models hosted on DeepInfra may be subject to those companies' data handling policies, effectively routing data through an additional trust boundary that is not fully transparent to the user.

---

## 6. Client-Side Defense Layers

A robust client-side defense employs multiple layers, each addressing a distinct failure mode. These layers operate independently so that the failure of any single layer does not compromise the overall privacy posture.

```
+-------------------------------------------------------------------+
|                        APPLICATION                                 |
|                                                                    |
|  +-------------------------------------------------------------+  |
|  | LAYER 5: Response Restoration                                |  |
|  | Re-insert original PII into response using token map         |  |
|  +-------------------------------------------------------------+  |
|                              ^                                     |
|                              | (response from provider)            |
|  +-------------------------------------------------------------+  |
|  | LAYER 4: Network Verification                                |  |
|  | Confirm what actually left the machine via packet inspection  |  |
|  +-------------------------------------------------------------+  |
|                              ^                                     |
|                              |                                     |
|  +-------------------------------------------------------------+  |
|  | LAYER 3: Audit Logging                                       |  |
|  | Record sanitized prompt, timestamp, provider, model          |  |
|  +-------------------------------------------------------------+  |
|                              ^                                     |
|                              |                                     |
|  +-------------------------------------------------------------+  |
|  | LAYER 2: Reversible Tokenization                             |  |
|  | Replace PII with deterministic placeholders; store mapping   |  |
|  +-------------------------------------------------------------+  |
|                              ^                                     |
|                              |                                     |
|  +-------------------------------------------------------------+  |
|  | LAYER 1: PII Detection and Scrubbing                         |  |
|  | Identify and flag PII using NER, regex, and heuristics       |  |
|  +-------------------------------------------------------------+  |
|                              ^                                     |
|                              |                                     |
|                     [ Raw prompt input ]                            |
+-------------------------------------------------------------------+
```

### Layer 1: PII Detection and Scrubbing (Pre-Send)

**Purpose:** Identify and remove or flag PII before the prompt leaves the client.

**Techniques:**
- **Regular expression matching:** Detect structured PII such as SSNs (`\d{3}-\d{2}-\d{4}`), email addresses, phone numbers, and credit card numbers.
- **Named Entity Recognition (NER):** Use a local NER model (e.g., spaCy, Presidio, or a small transformer) to detect names, organizations, locations, and dates.
- **Dictionary-based matching:** Maintain local dictionaries of known sensitive values (employee names, customer IDs) for exact-match detection.
- **Heuristic rules:** Flag prompts containing medical terminology (ICD codes, drug names), legal terminology (case numbers, statute references), or financial terminology (account numbers, routing numbers).

**Limitations:** No PII detector achieves 100% recall. Contextual PII (combinations of non-PII fields that become identifying) is particularly difficult to detect. False positives degrade prompt quality.

### Layer 2: Reversible Tokenization (Maintain Utility)

**Purpose:** Replace detected PII with deterministic placeholders that preserve the semantic structure of the prompt, enabling accurate inference while protecting the actual data.

**Mechanism:**
1. Each detected PII entity is assigned a category-specific placeholder: `[PERSON_1]`, `[EMAIL_1]`, `[SSN_1]`, etc.
2. A local mapping table records the association: `{PERSON_1: "John Smith", EMAIL_1: "john@example.com"}`.
3. The mapping table is stored only on the client machine and never transmitted.
4. Placeholders are consistent within a session: the same entity always maps to the same placeholder, preserving co-reference.

**Example:**

| Original Prompt | Tokenized Prompt |
|---|---|
| "Summarize the medical history of John Smith, DOB 03/15/1985, diagnosed with Type 2 diabetes at Springfield General Hospital." | "Summarize the medical history of [PERSON_1], DOB [DATE_1], diagnosed with Type 2 diabetes at [ORGANIZATION_1]." |

### Layer 3: Audit Logging (Record What Was Sent)

**Purpose:** Maintain a tamper-evident local log of every inference request, enabling after-the-fact review and compliance auditing.

**Log Fields:**
- Timestamp (UTC)
- Provider and model identifier
- Sanitized prompt hash (hash of the tokenized prompt, not the original)
- Token count (request and response)
- PII entities detected and scrubbed (types and counts, not values)
- Whether any PII scrubbing failures or warnings occurred
- Response hash

**Storage:** Logs should be stored locally with append-only access controls. For compliance-sensitive environments, logs should be forwarded to a centralized SIEM.

### Layer 4: Network Verification (Confirm What Left the Machine)

**Purpose:** Independently verify that the data actually transmitted over the network matches the sanitized version, detecting cases where a bug or misconfiguration bypasses the scrubbing layer.

**Techniques:**
- **Local proxy inspection:** Route inference requests through a local HTTPS proxy (e.g., mitmproxy in transparent mode) that logs request bodies. Compare logged bodies against the expected sanitized prompt.
- **Packet capture sampling:** Periodically capture and inspect outbound TLS traffic (using the client's own TLS keys) to verify content.
- **Application-level checksums:** The application computes a hash of the sanitized prompt before sending and compares it against a hash of the actual transmitted payload.

**Limitations:** This layer adds latency and complexity. It is most appropriate for high-sensitivity environments and may be implemented as a periodic audit rather than continuous inspection.

### Layer 5: Response Restoration (Re-Insert PII Post-Response)

**Purpose:** After receiving the model's response (which references placeholders), substitute the original PII back in so the end user sees natural, readable output.

**Mechanism:**
1. Parse the response for placeholder tokens (`[PERSON_1]`, `[EMAIL_1]`, etc.).
2. Look up each placeholder in the local mapping table.
3. Replace placeholders with original values.
4. Present the restored response to the user.

**Edge Cases:**
- The model may rephrase or partially reproduce a placeholder (e.g., "Person 1" instead of "[PERSON_1]"). Fuzzy matching may be required.
- The model may generate new PII not present in the original prompt. This should be flagged rather than silently passed through.
- Multi-turn conversations require maintaining the mapping table across turns with consistent placeholder assignment.

---

## 7. Recommendations

### 7.1 Technical Controls

1. **Implement client-side PII detection and tokenization.** This is the single highest-impact mitigation. Even an imperfect PII scrubber significantly reduces the volume of sensitive data transmitted to external providers. Use a layered approach combining regex, NER, and dictionary matching.

2. **Enforce TLS 1.3 with certificate validation.** Verify that the client's HTTP library validates the provider's certificate chain and does not silently downgrade to older TLS versions. Pin certificates where operationally feasible.

3. **Use DNS-over-HTTPS or DNS-over-TLS.** Prevent DNS queries from revealing which inference providers are being contacted. Configure the application or system resolver to use encrypted DNS.

4. **Implement audit logging for all inference requests.** Log the sanitized prompt (not the original), the provider, the model, token counts, and timestamps. This enables compliance auditing and incident investigation.

5. **Store API keys in a secrets manager.** Never embed API keys in source code, configuration files checked into version control, or client-side applications. Use environment variables backed by a secrets management system (HashiCorp Vault, AWS Secrets Manager, or equivalent).

6. **Rotate API keys on a defined schedule.** Regular rotation limits the window of exposure if a key is compromised. Implement automated rotation where the provider's API supports it.

7. **Minimize prompt content.** Send the minimum context necessary for accurate inference. Avoid including full documents when a summary or extracted passage would suffice. Strip metadata, headers, and boilerplate from included content.

8. **Scan model responses for PII.** Apply the same PII detection used on outbound prompts to inbound responses. Flag or redact any PII that appears in model output, particularly PII that was not present in the prompt (which may indicate model memorization or cross-session leakage).

9. **Isolate sessions.** Do not share conversation context across users or across unrelated tasks. Use separate session identifiers and consider separate API keys for distinct use cases.

10. **Evaluate confidential computing options.** As providers begin offering inference within trusted execution environments (TEEs), evaluate whether these options meet your threat model. TEE-based inference provides technical guarantees that policy-based approaches cannot.

### 7.2 Policy and Contractual Controls

1. **Execute a Data Processing Agreement (DPA) with every inference provider.** The DPA should specify data handling obligations, retention limits, training data usage restrictions, breach notification timelines, and audit rights.

2. **Prohibit training on user data.** Ensure the DPA or terms of service explicitly exclude the use of submitted data for model training, evaluation, or improvement. Verify that this applies to all models hosted by the provider, including third-party models.

3. **Require breach notification within a defined SLA.** 72 hours is the GDPR standard and a reasonable baseline. The DPA should specify the notification channel, the information to be provided, and the provider's obligation to cooperate with the user's incident response.

4. **Review subprocessor lists.** Understand which third parties have access to your data. Require notification when new subprocessors are added.

5. **Establish a provider exit plan.** Document the process for migrating away from a provider if their privacy posture changes. Maintain the ability to switch providers with minimal disruption.

6. **Classify data before sending to external inference.** Establish a data classification policy that defines which categories of data may be sent to external LLM providers and which must remain on-premises. Critical PII, trade secrets, and legally privileged communications should generally not be sent to external providers without strong justification and additional safeguards.

7. **Monitor provider policy changes.** Subscribe to provider policy update notifications. Assign responsibility for reviewing changes and assessing their impact on your data protection posture.

### 7.3 Operational Controls

1. **Conduct regular privacy impact assessments.** Evaluate the privacy implications of LLM inference usage at least annually, or whenever the application, provider, or data types change.

2. **Train developers on prompt privacy.** Developers who build LLM-integrated applications should understand the privacy implications of prompt construction. Include prompt privacy in secure development training.

3. **Test PII scrubbing effectiveness.** Regularly test the PII detection and tokenization pipeline against representative prompts containing known PII. Measure recall (what percentage of PII is caught) and precision (what percentage of flagged items are actually PII). Target recall above 95% for structured PII types.

4. **Maintain a provider comparison scorecard.** Use the framework in Section 5 to evaluate and compare providers. Update scores when provider policies or certifications change. Use the scorecard to inform provider selection and renewal decisions.

5. **Establish an incident response procedure for PII exposure.** Define the steps to take if PII is discovered to have been sent to an external provider without adequate scrubbing. This should include: assessment of the data exposed, notification of the provider, invocation of deletion rights, notification of affected individuals (if required by regulation), and root cause analysis.

6. **Conduct periodic network audits.** Verify that inference traffic is routed as expected (correct provider endpoints, correct TLS configuration, no unexpected intermediaries). Use the Layer 4 network verification approach from Section 6 on a sampling basis.

7. **Document and version all prompt templates.** Maintain prompt templates in version control with code review. Changes to prompt templates that alter the data included in prompts should receive privacy review.

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **DPA** | Data Processing Agreement; a contract between a data controller and a data processor specifying data handling obligations |
| **mTLS** | Mutual TLS; TLS with client certificate authentication in addition to server authentication |
| **NER** | Named Entity Recognition; an NLP technique for identifying named entities (persons, organizations, locations) in text |
| **PII** | Personally Identifiable Information; data that can identify a specific individual directly or in combination |
| **SOC 2** | Service Organization Control 2; an auditing framework for service providers' security, availability, and confidentiality controls |
| **TEE** | Trusted Execution Environment; a hardware-isolated processing environment that protects code and data from the host system |
| **TLS** | Transport Layer Security; the cryptographic protocol that provides encryption for data in transit over networks |
| **Zero-retention** | A data handling policy where prompt content is not written to persistent storage at any point |

## Appendix B: Regulatory Reference

| Regulation | Jurisdiction | Key Implication for LLM Inference |
|---|---|---|
| **GDPR** (General Data Protection Regulation) | EU/EEA | Prompt content containing EU resident PII requires a lawful basis for processing; data subjects have deletion rights; cross-border transfers require adequacy decisions or SCCs |
| **CCPA/CPRA** (California Consumer Privacy Act / California Privacy Rights Act) | California, USA | California residents have rights to know, delete, and opt out of sale/sharing of personal information |
| **HIPAA** (Health Insurance Portability and Accountability Act) | USA | Protected Health Information (PHI) in prompts triggers HIPAA obligations; requires BAA with the inference provider |
| **CLOUD Act** (Clarifying Lawful Overseas Use of Data Act) | USA | US-incorporated providers can be compelled to produce data stored abroad; relevant when using US-based inference providers |
| **PIPEDA** (Personal Information Protection and Electronic Documents Act) | Canada | Requires consent for collection, use, and disclosure of personal information; applies to commercial LLM usage |
| **AI Act** | EU | Imposes transparency and risk management obligations for AI systems; high-risk applications face additional requirements |

---

*This document should be reviewed and updated as provider policies, regulatory requirements, and available technical controls evolve. The threat landscape for LLM inference privacy is active and changing.*
