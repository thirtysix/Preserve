# LLM Inference Provider Privacy Comparison Framework

## Scoring Rubric

Each category is scored 1-5:
- **1** = No policy / major concern
- **2** = Weak or vague policy
- **3** = Standard industry practice
- **4** = Above average, with specifics
- **5** = Best-in-class, technically enforced

## Categories

| # | Category | What to Evaluate |
|---|----------|-----------------|
| 1 | **Transport Encryption** | TLS version, mTLS support, certificate pinning |
| 2 | **Storage/Logging Policy** | Are prompts/responses stored on disk? What is logged? |
| 3 | **Training Data Usage** | Does the provider train on user queries? Opt-in or opt-out? |
| 4 | **Security Certifications** | SOC 2, ISO 27001, HITRUST, FedRAMP, etc. |
| 5 | **Data Residency Controls** | Can users choose where data is processed? |
| 6 | **Breach Notification** | SLA for breach disclosure, notification process |
| 7 | **Transparency Reporting** | Published transparency reports, government request disclosures |
| 8 | **Third-Party Model Handling** | Are hosted models subject to the model creator's separate policies? |
| 9 | **DPA Availability** | Data Processing Agreement for GDPR compliance |
| 10 | **Debugging Exception Clarity** | How clearly defined is the provider's right to inspect user data? |

## Comparison Table

| Category | DeepInfra | Provider B | Provider C |
|----------|-----------|------------|------------|
| Transport Encryption | 3 — TLS (standard, no mTLS advertised) | — | — |
| Storage/Logging Policy | 4 — Memory-only, no disk storage; metadata-only logging | — | — |
| Training Data Usage | 5 — Explicit no-training unless user requests fine-tuning | — | — |
| Security Certifications | 4 — SOC 2 + ISO 27001 | — | — |
| Data Residency Controls | 2 — AWS/GCP, no user-selectable region | — | — |
| Breach Notification | 3 — Standard (no specific SLA published) | — | — |
| Transparency Reporting | 2 — No published transparency reports found | — | — |
| Third-Party Model Handling | 2 — Google/Anthropic models subject to their own policies; unclear disclosure | — | — |
| DPA Availability | 3 — GDPR compliance claimed, DPA availability not prominently documented | — | — |
| Debugging Exception Clarity | 2 — Vague: "may store for limited time for debugging"; no time limit or opt-out | — | — |
| **Total** | **30/50** | — | — |

## DeepInfra Assessment Notes

**Strengths:**
- Memory-only storage during inference is a strong technical control
- Explicit no-training commitment with clear language
- SOC 2 + ISO 27001 dual certification
- Metadata-only logging (no prompt/response content)

**Concerns:**
- Debugging exception is the weakest area — vague language, no defined time limit, no user opt-out
- Third-party model routing creates a "policy within a policy" problem — users may not realize Google/Anthropic models carry additional data handling terms
- No published transparency reports
- Data residency controls are limited
- 30-day post-account-deletion retention window

## How to Use This Framework

1. **Fill in the table** for each provider you evaluate
2. **Weight categories** based on your organization's risk profile (e.g., healthcare orgs should weight Storage and Certifications higher)
3. **Compare totals** but also look at individual category scores — a single 1 in a critical category may be disqualifying regardless of total
4. **Re-evaluate quarterly** — provider policies change
5. **Request clarification** from providers on any category scored 2 or below
