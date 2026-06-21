"""Audit logging for PII scrubbing operations."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from preserve.detectors import PIIMatch
from preserve.mapping import PlaceholderMap

logger = logging.getLogger("preserve.audit")


@dataclass
class AuditEntry:
    """A single audit log entry for one scrub operation."""

    timestamp: str
    text_hash: str  # SHA-256 of original text
    pii_count: int
    pii_types: dict[str, int]  # counts by type
    placeholders_used: list[str]
    original_values: list[str] | None = None  # Only if log_scrubbed_content=True

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["original_values"] is None:
            del d["original_values"]
        return d


class AuditLog:
    """Maintains an audit trail of scrubbing operations."""

    def __init__(self, log_scrubbed_content: bool = False) -> None:
        self._log_content = log_scrubbed_content
        self._entries: list[AuditEntry] = []

    def record(
        self,
        original_text: str,
        detections: list[PIIMatch],
        placeholder_map: PlaceholderMap,
    ) -> AuditEntry:
        """Record a scrub operation."""
        text_hash = hashlib.sha256(original_text.encode()).hexdigest()[:16]

        pii_types: dict[str, int] = {}
        for d in detections:
            pii_types[d.replacement_type] = pii_types.get(d.replacement_type, 0) + 1

        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            text_hash=text_hash,
            pii_count=len(detections),
            pii_types=pii_types,
            placeholders_used=list(placeholder_map.entries.keys()),
            original_values=(
                list(placeholder_map.entries.values())
                if self._log_content
                else None
            ),
        )

        self._entries.append(entry)
        logger.info(
            "Scrub recorded: %d PII items found (%s)",
            entry.pii_count,
            ", ".join(f"{k}={v}" for k, v in pii_types.items()),
        )
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    @property
    def total_pii_scrubbed(self) -> int:
        return sum(e.pii_count for e in self._entries)

    def summary(self) -> dict:
        """Return a summary of all audit entries."""
        all_types: dict[str, int] = {}
        for entry in self._entries:
            for pii_type, count in entry.pii_types.items():
                all_types[pii_type] = all_types.get(pii_type, 0) + count

        return {
            "total_operations": len(self._entries),
            "total_pii_scrubbed": self.total_pii_scrubbed,
            "pii_by_type": all_types,
        }

    def export(self, path: str, fmt: str = "json") -> None:
        """Export audit log to file."""
        if fmt == "json":
            with open(path, "w") as f:
                json.dump(
                    [e.to_dict() for e in self._entries],
                    f,
                    indent=2,
                )
        elif fmt == "csv":
            import csv

            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["timestamp", "text_hash", "pii_count", "pii_types", "placeholders"]
                )
                for entry in self._entries:
                    writer.writerow([
                        entry.timestamp,
                        entry.text_hash,
                        entry.pii_count,
                        json.dumps(entry.pii_types),
                        json.dumps(entry.placeholders_used),
                    ])
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        logger.info("Audit log exported to %s (%s)", path, fmt)

    def __len__(self) -> int:
        return len(self._entries)
