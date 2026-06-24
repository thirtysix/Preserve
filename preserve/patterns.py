"""Regex pattern library for PII detection."""

import re
from dataclasses import dataclass

from preserve.config import SensitivityLevel


@dataclass(frozen=True)
class PIIPattern:
    """A named PII detection pattern."""

    name: str
    regex: re.Pattern
    min_sensitivity: SensitivityLevel
    description: str
    replacement_type: str  # Used in placeholder: [TYPE_1]


# --- Pattern Definitions ---

EMAIL = PIIPattern(
    name="email",
    regex=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Email addresses",
    replacement_type="EMAIL",
)

SSN = PIIPattern(
    name="ssn",
    regex=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="US Social Security Numbers (XXX-XX-XXXX)",
    replacement_type="SSN",
)

CREDIT_CARD = PIIPattern(
    name="credit_card",
    regex=re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Credit card numbers (13-19 digits)",
    replacement_type="CREDIT_CARD",
)

US_PHONE = PIIPattern(
    name="us_phone",
    regex=re.compile(
        r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="US phone numbers",
    replacement_type="PHONE",
)

IP_ADDRESS = PIIPattern(
    name="ip_address",
    regex=re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="IPv4 addresses",
    replacement_type="IP",
)

IP_ADDRESS_V6 = PIIPattern(
    name="ip_address_v6",
    regex=re.compile(
        r"(?<![\w:])(?:"
        r"(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}"                      # full
        r"|(?:[A-Fa-f0-9]{1,4}:){1,7}:"                                   # 1::, 1:2::
        r"|(?:[A-Fa-f0-9]{1,4}:){1,6}:[A-Fa-f0-9]{1,4}"
        r"|(?:[A-Fa-f0-9]{1,4}:){1,5}(?::[A-Fa-f0-9]{1,4}){1,2}"
        r"|(?:[A-Fa-f0-9]{1,4}:){1,4}(?::[A-Fa-f0-9]{1,4}){1,3}"
        r"|(?:[A-Fa-f0-9]{1,4}:){1,3}(?::[A-Fa-f0-9]{1,4}){1,4}"
        r"|(?:[A-Fa-f0-9]{1,4}:){1,2}(?::[A-Fa-f0-9]{1,4}){1,5}"
        r"|[A-Fa-f0-9]{1,4}:(?::[A-Fa-f0-9]{1,4}){1,6}"
        r"|:(?:(?::[A-Fa-f0-9]{1,4}){1,7}|:)"                             # ::, ::1
        r"|::(?:ffff(?::0{1,4})?:)?(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)"  # ::ffff:1.2.3.4
        r")(?:%[0-9A-Za-z]+)?(?![\w:])",                                  # optional zone id
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="IPv6 addresses (full and compressed forms, incl. IPv4-mapped and zone id)",
    replacement_type="IP",
)

DATE_OF_BIRTH = PIIPattern(
    name="date_of_birth",
    regex=re.compile(
        r"\b(?:DOB|D\.O\.B\.?|date of birth|born|birthday)[:\s]*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Dates of birth with contextual indicator",
    replacement_type="DOB",
)

DATE_GENERIC = PIIPattern(
    name="date_generic",
    regex=re.compile(
        r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="Generic dates in MM/DD/YYYY or MM-DD-YYYY format",
    replacement_type="DATE",
)

US_ADDRESS = PIIPattern(
    name="us_address",
    regex=re.compile(
        r"\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][a-z]+\s*){1,4}"
        r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Road|Rd|Court|Ct|Way|Place|Pl|Terrace|Ter|Circle|Cir|Trail|Trl|Parkway|Pkwy|Commons|Square|Sq|Loop|Alley|Aly)"
        r"\.?\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="US street addresses (heuristic)",
    replacement_type="ADDRESS",
)

INTL_ADDRESS = PIIPattern(
    name="intl_address",
    regex=re.compile(
        # European: "Via Roma 31", "Rue de la Paix 5", "Hauptstraße 88"
        # Pattern: street name (with possible articles/prepositions) + number
        r"\b(?:Via|Viale|Corso|Piazza|Largo"       # Italian
        r"|Rue|Avenue|Boulevard|Allée|Place"         # French
        r"|Calle|Avenida|Paseo|Plaza"                # Spanish
        r"|Rua|Avenida|Travessa|Alameda"             # Portuguese
        r"|Straße|Strasse|Weg|Gasse|Allee|Platz"     # German
        r"|Katu|Tie|Kuja|Bulevardi"                  # Finnish (suffix forms)
        r"|Gracht|Straat|Laan|Plein|Weg"             # Dutch
        r"|Gatan|Vägen"                              # Swedish
        r")\s+"
        r"(?:(?:de|del|della|delle|di|du|des|la|las|los|el|da|das|do)\s+)*"  # articles
        r"(?:[A-ZÀ-ÖØ-Þa-zà-öø-ÿ]+\s*){0,4}"       # street name words
        r"\d{1,5}[A-Za-z]?\b",                         # house number at end (optional letter)
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="International street addresses (European/Latin pattern: street name + number)",
    replacement_type="ADDRESS",
)

INTL_ADDRESS_NUM_FIRST = PIIPattern(
    name="intl_address_num_first",
    regex=re.compile(
        # Pattern: number + street name (English/French style)
        r"\b\d{1,5}[A-Za-z]?\s+"
        r"(?:(?:de|del|du|des|la|las|los)\s+)*"
        r"(?:[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+\s*){1,4}"
        r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Road|Rd|"
        r"Court|Ct|Way|Place|Pl|Terrace|Ter|Circle|Cir|Trail|Trl|Parkway|Pkwy|"
        r"Commons|Square|Sq|Loop|Alley|Aly|"
        # International suffixes
        r"Straat|Gracht|Laan|Plein|"         # Dutch
        r"Gatan|Vägen|"                       # Swedish
        r"katu|tie|kuja|intie|rintie"         # Finnish
        r")"
        r"\.?\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="Street addresses with number first + international suffixes",
    replacement_type="ADDRESS",
)

# Suffix-based addresses: word ending in street-type suffix + number
# Catches "Herengracht 63", "Gartenweg 54", "Mechelininkatu 931"
SUFFIX_ADDRESS = PIIPattern(
    name="suffix_address",
    regex=re.compile(
        r"\b[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]*"
        r"(?:gracht|straat|laan|plein|weg|dijk|singel|kade"  # Dutch
        r"|gatan|vägen|torget|stigen"                         # Swedish
        r"|katu|tie|intie|rintie|kuja|bulevardi|esplanadi"    # Finnish
        r"|straße|strasse|weg|gasse|allee|platz|ring|damm"   # German
        r"|veien|gata|plass|vei"                              # Norwegian
        r")"
        r"\s+\d{1,5}\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="Addresses with embedded street-type suffix + number",
    replacement_type="ADDRESS",
)

US_ZIPCODE = PIIPattern(
    name="us_zipcode",
    regex=re.compile(r"\b\d{5}(?:-\d{4})?\b"),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="US ZIP codes",
    replacement_type="ZIPCODE",
)

NAME_HEURISTIC = PIIPattern(
    name="name_heuristic",
    regex=re.compile(
        r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Professor|Rev|Judge|Sir|Lady)"
        r"\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="Names preceded by salutations/titles",
    replacement_type="NAME",
)

NAME_CONTEXTUAL = PIIPattern(
    name="name_contextual",
    regex=re.compile(
        r"(?i:patient|client|employee|applicant|customer|user|contact|witness|"
        r"supervisor|manager|doctor|nurse|attorney|plaintiff|defendant|insured|"
        r"beneficiary|spouse|guardian|dependent|referred by|signed by|"
        r"name|naam|nombre|nom|nome)\s*(?:is|:)\s*"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Names preceded by role/context keywords (e.g., 'patient: John Doe')",
    replacement_type="NAME",
)

# --- US Medical & Government IDs ---

PASSPORT_CONTEXTUAL = PIIPattern(
    name="passport_contextual",
    regex=re.compile(
        r"(?:passport\s*(?:#|number|no\.?)?[:\s]*)"
        r"([A-Z0-9]{6,13})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Passport numbers with context keyword (any alphanumeric 6-13 chars)",
    replacement_type="PASSPORT",
)

US_DRIVERS_LICENSE = PIIPattern(
    name="us_drivers_license",
    regex=re.compile(
        r"(?:driver'?s?\s*(?:license|licence|lic)\s*(?:#|number|no\.?)?[:\s]*)"
        r"([A-Z0-9]{4,15})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="US driver's license numbers (with context keyword)",
    replacement_type="DRIVERS_LICENSE",
)

MEDICAL_RECORD_NUMBER = PIIPattern(
    name="medical_record_number",
    regex=re.compile(
        r"(?:MRN|medical\s*record\s*(?:#|number|no\.?)?|chart\s*(?:#|number|no\.?)?)"
        r"[:\s]*([A-Z0-9]{4,15})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Medical record numbers (with context keyword)",
    replacement_type="MRN",
)

HEALTH_INSURANCE_ID = PIIPattern(
    name="health_insurance_id",
    regex=re.compile(
        r"(?:(?:health|medical)\s*(?:insurance|plan)\s*(?:id|#|number|no\.?)?|"
        r"member\s*(?:id|#|number)|policy\s*(?:#|number|no\.?)?|group\s*(?:#|number))"
        r"[:\s]*([A-Z0-9]{4,20})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Health insurance / member / policy IDs",
    replacement_type="INSURANCE_ID",
)

DEA_NUMBER = PIIPattern(
    name="dea_number",
    regex=re.compile(
        r"(?:DEA\s*(?:#|number|no\.?)?[:\s]*)"
        r"([A-Z]{2}\d{7})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="US DEA registration numbers (2 letters + 7 digits)",
    replacement_type="DEA",
)

NPI_NUMBER = PIIPattern(
    name="npi_number",
    regex=re.compile(
        r"(?:NPI\s*(?:#|number|no\.?)?[:\s]*)"
        r"(\d{10})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="US National Provider Identifier (10 digits, with context)",
    replacement_type="NPI",
)

US_EIN = PIIPattern(
    name="us_ein",
    regex=re.compile(
        r"(?:EIN|employer\s*identification\s*(?:#|number|no\.?))[:\s]*"
        r"(\d{2}-\d{7})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="US Employer Identification Number (XX-XXXXXXX)",
    replacement_type="EIN",
)

US_ITIN = PIIPattern(
    name="us_itin",
    regex=re.compile(r"\b9\d{2}-[7-9]\d-\d{4}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="US Individual Taxpayer Identification Number (9XX-[7-9]X-XXXX)",
    replacement_type="ITIN",
)

# --- International Identifiers ---

UK_NINO = PIIPattern(
    name="uk_nino",
    regex=re.compile(
        r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)"
        r"[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="UK National Insurance Number (e.g., AB 12 34 56 C)",
    replacement_type="UK_NINO",
)

UK_NHS = PIIPattern(
    name="uk_nhs",
    regex=re.compile(
        r"(?:NHS\s*(?:#|number|no\.?)?[:\s]*)"
        r"(\d{3}\s?\d{3}\s?\d{4})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="UK NHS number (10 digits, with context)",
    replacement_type="NHS",
)

UK_PHONE = PIIPattern(
    name="uk_phone",
    regex=re.compile(
        r"(?:\+44\s?|0)(?:\d\s?){9,10}\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="UK phone numbers (+44 or 0 prefix)",
    replacement_type="PHONE",
)

CANADA_SIN = PIIPattern(
    name="canada_sin",
    regex=re.compile(r"\b\d{3}[\s-]\d{3}[\s-]\d{3}\b"),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Canadian Social Insurance Number (XXX-XXX-XXX)",
    replacement_type="CA_SIN",
)

CANADA_HEALTH = PIIPattern(
    name="canada_health",
    regex=re.compile(
        r"(?:health\s*card|OHIP|carte\s*sant[eé]|RAMQ|PHN|care\s*card)"
        r"\s*(?:#|number|no\.?)?[:\s]*([A-Z0-9]{4,15})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Canadian provincial health card numbers (with context)",
    replacement_type="CA_HEALTH",
)

GERMANY_PERSONALAUSWEIS = PIIPattern(
    name="germany_id",
    regex=re.compile(
        r"(?:Personalausweis|Ausweis|ID\s*(?:card|nummer|number))\s*"
        r"(?:#|number|no\.?|Nr\.?)?[:\s]*([A-Z0-9]{9,10})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="German ID card number (with context)",
    replacement_type="DE_ID",
)

GERMANY_STEUER_ID = PIIPattern(
    name="germany_steuer_id",
    regex=re.compile(
        r"(?:Steuer-?ID|Steueridentifikationsnummer|tax\s*ID)\s*"
        r"(?:#|number|no\.?|Nr\.?)?[:\s]*(\d{11})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="German tax ID / Steuer-ID (11 digits, with context)",
    replacement_type="DE_TAX",
)

FRANCE_NIR = PIIPattern(
    name="france_nir",
    regex=re.compile(
        r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="French NIR / INSEE social security number (15 digits starting with 1 or 2)",
    replacement_type="FR_NIR",
)

FRANCE_PHONE = PIIPattern(
    name="france_phone",
    regex=re.compile(
        r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="French phone numbers (+33 or 0 prefix)",
    replacement_type="PHONE",
)

BRAZIL_CPF = PIIPattern(
    name="brazil_cpf",
    regex=re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Brazilian CPF (XXX.XXX.XXX-XX)",
    replacement_type="BR_CPF",
)

BRAZIL_CNPJ = PIIPattern(
    name="brazil_cnpj",
    regex=re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Brazilian CNPJ (XX.XXX.XXX/XXXX-XX)",
    replacement_type="BR_CNPJ",
)

INDIA_AADHAAR = PIIPattern(
    name="india_aadhaar",
    regex=re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Indian Aadhaar number (12 digits starting with 2-9)",
    replacement_type="IN_AADHAAR",
)

INDIA_PAN = PIIPattern(
    name="india_pan",
    regex=re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Indian PAN card (AAAAA9999A format)",
    replacement_type="IN_PAN",
)

MEXICO_CURP = PIIPattern(
    name="mexico_curp",
    regex=re.compile(
        r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b"
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Mexican CURP (18-character alphanumeric)",
    replacement_type="MX_CURP",
)

MEXICO_RFC = PIIPattern(
    name="mexico_rfc",
    regex=re.compile(
        r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Mexican RFC tax ID (12-13 characters)",
    replacement_type="MX_RFC",
)

AUSTRALIA_TFN = PIIPattern(
    name="australia_tfn",
    regex=re.compile(
        r"(?:TFN|tax\s*file\s*(?:number|no\.?|#))[:\s]*"
        r"(\d{3}\s?\d{3}\s?\d{3})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Australian Tax File Number (9 digits, with context)",
    replacement_type="AU_TFN",
)

AUSTRALIA_MEDICARE = PIIPattern(
    name="australia_medicare",
    regex=re.compile(
        r"(?:Medicare\s*(?:#|number|no\.?)?[:\s]*)"
        r"(\d{4}\s?\d{5}\s?\d{1}(?:\s?/\s?\d)?)\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Australian Medicare number (10-11 digits, with context)",
    replacement_type="AU_MEDICARE",
)

NETHERLANDS_BSN = PIIPattern(
    name="netherlands_bsn",
    regex=re.compile(
        r"(?:BSN|burgerservicenummer|citizen\s*service\s*number)\s*"
        r"(?:#|number|no\.?)?[:\s]*(\d{9})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Dutch BSN / Burgerservicenummer (9 digits, with context)",
    replacement_type="NL_BSN",
)

SPAIN_DNI = PIIPattern(
    name="spain_dni",
    regex=re.compile(r"\b\d{8}[A-Z]\b"),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Spanish DNI (8 digits + letter)",
    replacement_type="ES_DNI",
)

SPAIN_NIE = PIIPattern(
    name="spain_nie",
    regex=re.compile(r"\b[XYZ]\d{7}[A-Z]\b"),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Spanish NIE for foreigners (letter + 7 digits + letter)",
    replacement_type="ES_NIE",
)

ITALY_CODICE_FISCALE = PIIPattern(
    name="italy_codice_fiscale",
    regex=re.compile(
        r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Italian Codice Fiscale (16-character alphanumeric)",
    replacement_type="IT_CF",
)

SOUTH_KOREA_RRN = PIIPattern(
    name="south_korea_rrn",
    regex=re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="South Korean Resident Registration Number (YYMMDD-GXXXXXX)",
    replacement_type="KR_RRN",
)

JAPAN_MY_NUMBER = PIIPattern(
    name="japan_my_number",
    regex=re.compile(
        r"(?:My\s*Number|マイナンバー|個人番号)\s*(?:#|number|no\.?)?[:\s]*"
        r"(\d{12})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Japanese My Number / Individual Number (12 digits, with context)",
    replacement_type="JP_MYNUMBER",
)

# --- Finland ---

FINLAND_HETU = PIIPattern(
    name="finland_hetu",
    regex=re.compile(
        r"\b(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}"
        r"[-+A-FU-Y]"
        r"\d{3}"
        r"[0-9A-FHJKLMNPRSTUVWXY]\b"
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Finnish personal identity code / henkilötunnus (DDMMYY-NNNC)",
    replacement_type="FI_HETU",
)

FINLAND_YTUNNUS = PIIPattern(
    name="finland_ytunnus",
    regex=re.compile(
        r"(?:Y-tunnus|business\s*ID|FO-nummer)\s*(?:#|:)?\s*"
        r"(\d{7}-\d)\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Finnish business ID / Y-tunnus (NNNNNNN-C, with context)",
    replacement_type="FI_YTUNNUS",
)

FINLAND_VERONUMERO = PIIPattern(
    name="finland_veronumero",
    regex=re.compile(
        r"(?:veronumero|tax\s*number|vero\s*(?:#|number|no\.?))\s*(?:#|:)?\s*"
        r"(\d{12})\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Finnish tax number / veronumero (12 digits, with context)",
    replacement_type="FI_TAXNUM",
)

FINLAND_PHONE = PIIPattern(
    name="finland_phone",
    regex=re.compile(
        r"(?:\+358\s?|0)(?:4[0-9]|50)\s?\d{6,7}\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Finnish mobile phone numbers (+358 or 0 prefix, mobile prefixes 04x/050)",
    replacement_type="PHONE",
)

# --- Banking / Financial ---

# Context-based account/routing/branch number catcher
BANK_CONTEXTUAL = PIIPattern(
    name="bank_contextual",
    regex=re.compile(
        # Word-bounded keyword (so it doesn't fire inside "accountant"/"bankrupt"),
        # then a digit-led, account-number-like value (not arbitrary words).
        r"\b(?:bank|branch|acct|account|routing|BSB|sort\s*code)\b\s*"
        r"(?:#|number|no\.?|code)?[:\s#]*"
        r"(\d[\d\s\-]{4,20}\d)",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Bank/branch/account numbers with context keyword",
    replacement_type="FINANCIAL",
)

IBAN = PIIPattern(
    name="iban",
    regex=re.compile(
        r"\b[A-Z]{2}\d{2}\s?(?:[A-Z0-9]\s?){11,30}\b"
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="International Bank Account Number (IBAN)",
    replacement_type="IBAN",
)

SWIFT_BIC = PIIPattern(
    name="swift_bic",
    regex=re.compile(
        r"(?:SWIFT|BIC)[:\s]*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="SWIFT/BIC code (with context keyword)",
    replacement_type="SWIFT",
)

# --- Generic International Phone ---

INTL_PHONE = PIIPattern(
    name="intl_phone",
    regex=re.compile(
        r"\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{1,4}){2,5}\b"
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="International phone numbers with + country code",
    replacement_type="PHONE",
)

# Ordered by specificity (more specific patterns first to avoid partial matches)
MONTH_NAME_DATE = PIIPattern(
    name="month_name_date",
    regex=re.compile(
        r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+)?"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?"
        r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"(?:\s+\d{1,2}(?:st|nd|rd|th)?)?,?\s+(?:18|19|20)\d{2}\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Dates written with a month name and year (14 June 1994, June 14, 2020)",
    replacement_type="DATE",
)

SECONDARY_ADDRESS = PIIPattern(
    name="secondary_address",
    regex=re.compile(
        r"\b(?:Apt|Apartment|Suite|Ste|Unit|Rm|Room|Fl|Floor|Bldg|Building)\.?\s*#?\s*\d{1,5}[A-Za-z]?\b",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.AGGRESSIVE,
    description="Secondary address units (Apt. 259, Suite 786, Unit 4)",
    replacement_type="ADDRESS",
)


# --- Secrets / credentials (prevent leaking API keys, tokens, keys to an LLM) ---

AWS_ACCESS_KEY = PIIPattern(
    name="aws_access_key",
    regex=re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|A3T[A-Z0-9])[A-Z0-9]{16}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="AWS access key ID",
    replacement_type="SECRET",
)

GITHUB_TOKEN = PIIPattern(
    name="github_token",
    regex=re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="GitHub personal access / app token",
    replacement_type="SECRET",
)

ANTHROPIC_KEY = PIIPattern(
    name="anthropic_key",
    regex=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Anthropic API key",
    replacement_type="SECRET",
)

OPENAI_KEY = PIIPattern(
    name="openai_key",
    regex=re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="OpenAI API key",
    replacement_type="SECRET",
)

GOOGLE_API_KEY = PIIPattern(
    name="google_api_key",
    regex=re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Google API key",
    replacement_type="SECRET",
)

SLACK_TOKEN = PIIPattern(
    name="slack_token",
    regex=re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Slack token",
    replacement_type="SECRET",
)

STRIPE_KEY = PIIPattern(
    name="stripe_key",
    regex=re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{16,}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="Stripe API key",
    replacement_type="SECRET",
)

JWT_TOKEN = PIIPattern(
    name="jwt",
    regex=re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="JSON Web Token (JWT)",
    replacement_type="SECRET",
)

PRIVATE_KEY_PEM = PIIPattern(
    name="private_key_pem",
    regex=re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----"
    ),
    min_sensitivity=SensitivityLevel.MINIMAL,
    description="PEM private key block",
    replacement_type="SECRET",
)

DB_CONNECTION_URI = PIIPattern(
    name="db_connection_uri",
    regex=re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^\s:@/]+:[^\s:@/]+@[^\s/]+",
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Database/broker connection URI with embedded credentials",
    replacement_type="SECRET",
)

SECRET_ASSIGNMENT = PIIPattern(
    name="secret_assignment",
    regex=re.compile(
        r"(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token"
        r"|client[_-]?secret|password|passwd|pwd|bearer)\b['\"]?(?:\s*[:=]\s*|\s+)['\"]?"
        r"([A-Za-z0-9_\-./+=]{12,})",
        re.IGNORECASE,
    ),
    min_sensitivity=SensitivityLevel.STANDARD,
    description="Secret assigned after a keyword (api_key=, password:, bearer ...)",
    replacement_type="SECRET",
)

ALL_PATTERNS: list[PIIPattern] = [
    # High-confidence structured (MINIMAL)
    SSN,
    US_ITIN,
    SOUTH_KOREA_RRN,  # Before CREDIT_CARD to avoid false match
    CREDIT_CARD,
    EMAIL,
    PASSPORT_CONTEXTUAL,
    MEDICAL_RECORD_NUMBER,
    DEA_NUMBER,
    BRAZIL_CPF,
    BRAZIL_CNPJ,
    MEXICO_CURP,
    FINLAND_HETU,
    IBAN,
    UK_NHS,
    # Context-required structured (STANDARD)
    DATE_OF_BIRTH,
    NAME_CONTEXTUAL,
    US_PHONE,
    UK_PHONE,
    FRANCE_PHONE,
    INTL_PHONE,
    IP_ADDRESS,
    IP_ADDRESS_V6,
    MONTH_NAME_DATE,
    SECONDARY_ADDRESS,
    # Secrets / credentials
    AWS_ACCESS_KEY,
    GITHUB_TOKEN,
    ANTHROPIC_KEY,
    OPENAI_KEY,
    GOOGLE_API_KEY,
    SLACK_TOKEN,
    STRIPE_KEY,
    JWT_TOKEN,
    PRIVATE_KEY_PEM,
    DB_CONNECTION_URI,
    SECRET_ASSIGNMENT,
    US_DRIVERS_LICENSE,
    HEALTH_INSURANCE_ID,
    NPI_NUMBER,
    US_EIN,
    UK_NINO,
    CANADA_SIN,
    CANADA_HEALTH,
    GERMANY_PERSONALAUSWEIS,
    GERMANY_STEUER_ID,
    FRANCE_NIR,
    INDIA_AADHAAR,
    INDIA_PAN,
    MEXICO_RFC,
    AUSTRALIA_TFN,
    AUSTRALIA_MEDICARE,
    NETHERLANDS_BSN,
    SPAIN_DNI,
    SPAIN_NIE,
    ITALY_CODICE_FISCALE,
    JAPAN_MY_NUMBER,
    FINLAND_YTUNNUS,
    FINLAND_VERONUMERO,
    FINLAND_PHONE,
    BANK_CONTEXTUAL,
    SWIFT_BIC,
    # Heuristic / high-recall (AGGRESSIVE)
    NAME_HEURISTIC,
    US_ADDRESS,
    INTL_ADDRESS,
    INTL_ADDRESS_NUM_FIRST,
    SUFFIX_ADDRESS,
    US_ZIPCODE,
    DATE_GENERIC,
]


def get_active_patterns(sensitivity: SensitivityLevel) -> list[PIIPattern]:
    """Return patterns active at the given sensitivity level."""
    level_order = [SensitivityLevel.MINIMAL, SensitivityLevel.STANDARD, SensitivityLevel.AGGRESSIVE]
    max_index = level_order.index(sensitivity)
    return [p for p in ALL_PATTERNS if level_order.index(p.min_sensitivity) <= max_index]
