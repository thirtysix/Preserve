#!/usr/bin/env python3
"""
Generate messy, realistic human input test cases.

Real humans don't write "Patient Aurora Rossi, born 1971-04-05".
They write "pt aurora rossi dob 4/5/71 ssn last4 6789 pls followup asap".

Categories of messiness:
- No capitalization
- Abbreviations (pt, dob, ssn, addr, ph, em)
- Typos and misspellings
- Partial information (last 4 of SSN, first name only)
- Mixed languages
- No punctuation / run-on text
- Copy-paste artifacts (extra spaces, tabs, line breaks)
- Informal / conversational tone
- Shorthand numbers ("five five five")
- Redacted-but-not-really ("J. S.", initials)
"""

import json
import os

MESSY_CASES = [
    # --- No capitalization ---
    {
        "id": "no_caps_1",
        "text": "patient aurora rossi born april 5 1971 lives at via roma 31 rome italy",
        "expected_pii": ["aurora rossi", "april 5 1971", "via roma 31"],
        "tags": ["no_caps", "natural_date"],
    },
    {
        "id": "no_caps_2",
        "text": "mikko virtanen called about his prescription, phone 040 1234567, email mikko.virtanen@example.com",
        "expected_pii": ["mikko virtanen", "040 1234567", "mikko.virtanen@example.com"],
        "tags": ["no_caps", "finnish"],
    },

    # --- Abbreviations ---
    {
        "id": "abbrev_1",
        "text": "pt: J. Smith, dob 3/15/85, ssn 123-45-6789, dx: T2DM, rx: metformin 500mg bid",
        "expected_pii": ["J. Smith", "3/15/85", "123-45-6789"],
        "tags": ["abbreviations", "medical"],
    },
    {
        "id": "abbrev_2",
        "text": "emp Sofia Garcia, dept HR, ext 4521, cell 555-867-5309, addr 742 Evergreen Terrace",
        "expected_pii": ["Sofia Garcia", "555-867-5309", "742 Evergreen Terrace"],
        "tags": ["abbreviations", "workplace"],
    },
    {
        "id": "abbrev_3",
        "text": "fwd: pls contact mrs korhonen re: invoice #4521, ph +358 44 9876543, acct FI4950000120000062",
        "expected_pii": ["korhonen", "+358 44 9876543", "FI4950000120000062"],
        "tags": ["abbreviations", "email_forward"],
    },

    # --- Typos and misspellings ---
    {
        "id": "typos_1",
        "text": "Patinet name: Aurrora Rossi, date of brith: 04/05/1971, adress: Via Roma 31",
        "expected_pii": ["Aurrora Rossi", "04/05/1971", "Via Roma 31"],
        "tags": ["typos"],
    },
    {
        "id": "typos_2",
        "text": "contcat info for miko virtanen: emal mikko@example.com, tel 040-123-4567",
        "expected_pii": ["miko virtanen", "mikko@example.com", "040-123-4567"],
        "tags": ["typos", "finnish"],
    },

    # --- Run-on / no punctuation ---
    {
        "id": "runon_1",
        "text": "ok so the patient is Leonardo Ferrari age 35 from Corso Italia 47 Lombardy he came in with chest pain and his wife Maria Ferrari called to ask about results her number is +39 345 678 9012",
        "expected_pii": ["Leonardo Ferrari", "Corso Italia 47", "Maria Ferrari", "+39 345 678 9012"],
        "tags": ["runon", "conversational"],
    },
    {
        "id": "runon_2",
        "text": "need to send docs to pekka korhonen mannerheimintie 42 helsinki finland hetu 131052-308T can you handle that thanks",
        "expected_pii": ["pekka korhonen", "mannerheimintie 42", "131052-308T"],
        "tags": ["runon", "finnish"],
    },

    # --- Informal / conversational ---
    {
        "id": "informal_1",
        "text": "hey can u look up john smith? his email is jsmith99@example.com and i think his ssn is 234-56-7890 but dont quote me on that",
        "expected_pii": ["john smith", "jsmith99@example.com", "234-56-7890"],
        "tags": ["informal", "conversational"],
    },
    {
        "id": "informal_2",
        "text": "yo check this - aurora.rossi@example.com wants a refund, card ending 4567, she lives somewhere on via roma i think #31",
        "expected_pii": ["aurora.rossi@example.com", "4567", "via roma"],
        "tags": ["informal", "partial_info"],
    },

    # --- Copy-paste artifacts ---
    {
        "id": "copypaste_1",
        "text": "Name:\tSofía García\nDOB:\t06/22/1988\nAddress:\tCalle Reforma 156\n\nMexico City\nPhone:\t+52 55 1234 5678\nID:\tGODE561231HMCRRL09",
        "expected_pii": ["Sofía García", "06/22/1988", "Calle Reforma 156", "+52 55 1234 5678", "GODE561231HMCRRL09"],
        "tags": ["copypaste", "tabs", "mexican"],
    },
    {
        "id": "copypaste_2",
        "text": "From: mikko.virtanen@example.com\nTo: hr@example.com\nSubject: Leave Request\n\nHi, my employee ID is EMP-4521 and I need to update my address to Fredrikinkatu 22, 00100 Helsinki. My henkilötunnus is 010285A123N for the records.",
        "expected_pii": ["mikko.virtanen@example.com", "Fredrikinkatu 22", "010285A123N"],
        "tags": ["copypaste", "email_format", "finnish"],
    },

    # --- Partial / redacted-ish ---
    {
        "id": "partial_1",
        "text": "The patient, Mr. V (Virtanen), DOB **/**/1985, SSN ending in 6789, was seen today",
        "expected_pii": ["V", "Virtanen", "1985", "6789"],
        "tags": ["partial", "redacted"],
    },
    {
        "id": "partial_2",
        "text": "Caller identified herself as A. Rossi from Rome, ref number CC67XXXXX",
        "expected_pii": ["A. Rossi"],
        "tags": ["partial", "redacted"],
    },

    # --- Mixed languages ---
    {
        "id": "mixed_lang_1",
        "text": "Asiakas Mikko Virtanen soitti eilen, his English is good. Osoite: Mannerheimintie 42. He wants to cancel his subscription, puhelin 040-1234567.",
        "expected_pii": ["Mikko Virtanen", "Mannerheimintie 42", "040-1234567"],
        "tags": ["mixed_language", "finnish_english"],
    },
    {
        "id": "mixed_lang_2",
        "text": "El paciente Santiago Hernández vive en Calle Hidalgo 55. His insurance ID is MEX-2345-6789. Please call +52 33 1234 5678.",
        "expected_pii": ["Santiago Hernández", "Calle Hidalgo 55", "MEX-2345-6789", "+52 33 1234 5678"],
        "tags": ["mixed_language", "spanish_english"],
    },

    # --- Obfuscated ---
    {
        "id": "obfuscated_1",
        "text": "reach her at aurora dot rossi at hospital dot org or call five five five eight six seven five three zero nine",
        "expected_pii": ["aurora dot rossi at hospital dot org", "five five five eight six seven five three zero nine"],
        "tags": ["obfuscated", "spelled_out"],
    },
    {
        "id": "obfuscated_2",
        "text": "email: mikko [at] company [dot] fi, SSN: one two three dash four five dash six seven eight nine",
        "expected_pii": ["mikko [at] company [dot] fi", "one two three dash four five dash six seven eight nine"],
        "tags": ["obfuscated", "spelled_out"],
    },

    # --- List / structured but messy ---
    {
        "id": "list_1",
        "text": "Attendees:\n- Kim, Min-jun (Korea) - mkim@example.com\n- Tanaka, Haruto (Japan) - h.tanaka@example.com\n- Virtanen, Mikko (Finland) - mvirtanen@example.com",
        "expected_pii": ["Min-jun", "Kim", "mkim@example.com", "Haruto", "Tanaka", "h.tanaka@example.com", "Mikko", "Virtanen", "mvirtanen@example.com"],
        "tags": ["list", "structured", "multinational"],
    },

    # --- Real-world messy medical note ---
    {
        "id": "medical_note_1",
        "text": "36yo M leonardo ferrari presents w/ cp x 2d. pmhx: dm2, htn. meds: metformin, lisinopril. allergy: nkda. wife maria called, ph 039-345-6789012. ins: aetna grp# 12345. addr: corso italia 47 lombardy. plan: admit, trop q6h, echo am.",
        "expected_pii": ["leonardo ferrari", "maria", "039-345-6789012", "12345", "corso italia 47"],
        "tags": ["medical_shorthand", "real_world"],
    },

    # --- Social media / chat style ---
    {
        "id": "chat_1",
        "text": "lol aurora rossi just dmed me her address its via roma 31 in rome 😂 her bday is april 5th btw",
        "expected_pii": ["aurora rossi", "via roma 31", "april 5th"],
        "tags": ["chat", "social_media", "emoji"],
    },

    # --- Dense PII dump ---
    {
        "id": "dense_1",
        "text": "Name: Aino Korhonen / DOB: 15.3.1990 / HETU: 150390A234B / Addr: Aleksanterinkatu 7, Helsinki / Tel: +358501234567 / IBAN: FI2112345600000785 / Passport: XK4567890",
        "expected_pii": ["Aino Korhonen", "15.3.1990", "150390A234B", "Aleksanterinkatu 7", "+358501234567", "FI2112345600000785", "XK4567890"],
        "tags": ["dense", "structured", "finnish"],
    },
]


def main():
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "messy_test_data.json")

    with open(output_path, "w") as f:
        json.dump(MESSY_CASES, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(MESSY_CASES)} messy test cases")
    print(f"Tags: {sorted(set(t for c in MESSY_CASES for t in c['tags']))}")
    print(f"Total expected PII items: {sum(len(c['expected_pii']) for c in MESSY_CASES)}")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
