"""
Structured data mode.

When input is CSV, JSON, or key-value data, column/field names provide
strong context signals. "patient_name" column = everything in it is a name.

Usage:
    from preserve.structured import StructuredScrubber
    scrubber = StructuredScrubber(config)
    result = scrubber.scrub_dict({"patient_name": "Aurora Rossi", "diagnosis": "T2DM"})
    result = scrubber.scrub_csv(csv_rows, headers)
"""

from __future__ import annotations

import re
from preserve.config import PreserveConfig
from preserve.scrubber import Scrubber, ScrubResult
from preserve.mapping import PlaceholderMap
from preserve.detectors import PIIMatch, SensitivityLevel


# Map column name patterns to PII types
COLUMN_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Names
    (re.compile(r"(?:full_?)?name|patient|client|employee|contact|person|applicant", re.I), "NAME"),
    (re.compile(r"first_?name|given_?name|forename", re.I), "NAME"),
    (re.compile(r"last_?name|surname|family_?name", re.I), "NAME"),
    (re.compile(r"emergency.+name|next.+kin|guardian|spouse", re.I), "NAME"),
    # Dates
    (re.compile(r"d[._]?o[._]?b|date.+birth|birth.?date|birthday|born", re.I), "DOB"),
    # Contact
    (re.compile(r"e?mail|email.+addr", re.I), "EMAIL"),
    (re.compile(r"phone|tel|mobile|cell|fax", re.I), "PHONE"),
    (re.compile(r"address|addr|street|residence|location|home", re.I), "ADDRESS"),
    (re.compile(r"zip|postal|postcode", re.I), "ZIPCODE"),
    # IDs
    (re.compile(r"ssn|social.+sec|national.+id|identity|hetu|nino|bsn|cpf|dni", re.I), "ID_NUMBER"),
    (re.compile(r"passport", re.I), "PASSPORT"),
    (re.compile(r"driver.?s?.+lic", re.I), "DRIVERS_LICENSE"),
    (re.compile(r"mrn|medical.+record|chart.+num|patient.+id", re.I), "MRN"),
    (re.compile(r"insurance|policy|member.+id|group.+num", re.I), "INSURANCE_ID"),
    # Financial
    (re.compile(r"iban|bank.+acc|account.+num|routing|sort.+code|bsb", re.I), "FINANCIAL"),
    (re.compile(r"credit.+card|card.+num|cc.+num", re.I), "CREDIT_CARD"),
    (re.compile(r"salary|income|wage|compensation|pay", re.I), "FINANCIAL"),
    # Network
    (re.compile(r"ip.+addr|ip$", re.I), "IP"),
    # Health
    (re.compile(r"diagnosis|condition|dx", re.I), "MEDICAL"),
    (re.compile(r"medication|rx|prescription|drug", re.I), "MEDICAL"),
    (re.compile(r"blood.+type|genetic|dna|genome|brca|marker", re.I), "MEDICAL"),
    (re.compile(r"disabilit|mental.+health|psych", re.I), "MEDICAL"),
    # Sensitive categories
    (re.compile(r"religio|faith|worship", re.I), "SENSITIVE"),
    (re.compile(r"politic|party|affiliation", re.I), "SENSITIVE"),
    (re.compile(r"ethnic|race|national.+origin", re.I), "SENSITIVE"),
    (re.compile(r"sex$|gender|orientation|lgb", re.I), "SENSITIVE"),
]

# Columns that are safe (not PII) even if they sound like they could be
SAFE_COLUMNS = re.compile(
    r"^(?:id|row|index|count|total|status|type|category|flag|"
    r"created|updated|modified|timestamp|date$|age|"
    r"description|notes|comments|region|country|city|state)$",
    re.I,
)


def classify_column(column_name: str) -> str | None:
    """Classify a column name as a PII type, or None if safe/unknown."""
    if SAFE_COLUMNS.match(column_name):
        return None
    for pattern, pii_type in COLUMN_PATTERNS:
        if pattern.search(column_name):
            return pii_type
    return None


class StructuredScrubber:
    """Scrubs structured data (dicts, CSV rows) using column-level classification."""

    def __init__(self, config: PreserveConfig | None = None) -> None:
        self.config = config or PreserveConfig()
        self._scrubber = Scrubber(self.config)

    def scrub_dict(
        self, data: dict[str, str], column_types: dict[str, str] | None = None
    ) -> tuple[dict[str, str], PlaceholderMap]:
        """Scrub a dictionary of key-value pairs.

        Args:
            data: {"column_name": "value", ...}
            column_types: Optional override of column -> PII type mapping.

        Returns:
            (scrubbed_dict, placeholder_map)
        """
        pm = PlaceholderMap(placeholder_format=self.config.placeholder_format)
        scrubbed = {}

        for col, val in data.items():
            if not val or not isinstance(val, str):
                scrubbed[col] = val
                continue

            # Determine PII type from column name
            if column_types and col in column_types:
                pii_type = column_types[col]
            else:
                pii_type = classify_column(col)

            if pii_type:
                # Column is classified as PII — scrub the entire value
                placeholder = pm.add(val, pii_type)
                scrubbed[col] = placeholder
            else:
                # Column not classified — run normal scrubber on value
                result = self._scrubber.scrub(val)
                scrubbed[col] = result.sanitized_text
                # Merge placeholder maps
                for ph, orig in result.placeholder_map.entries.items():
                    pm._placeholder_to_original[ph] = orig
                    pm._original_to_placeholder[orig.lower()] = ph

        return scrubbed, pm

    def scrub_csv_rows(
        self,
        rows: list[dict[str, str]],
        column_types: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, str]], list[PlaceholderMap]]:
        """Scrub a list of CSV rows (list of dicts).

        Returns:
            (scrubbed_rows, list_of_placeholder_maps)
        """
        scrubbed_rows = []
        maps = []
        for row in rows:
            scrubbed, pm = self.scrub_dict(row, column_types)
            scrubbed_rows.append(scrubbed)
            maps.append(pm)
        return scrubbed_rows, maps
