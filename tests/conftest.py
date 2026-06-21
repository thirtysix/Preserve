"""Shared test fixtures — session-scoped to avoid reloading heavy datasets."""

import pytest

from preserve.config import PreserveConfig, SensitivityLevel
from preserve.detectors import PIIDetector
from preserve.scrubber import Scrubber


@pytest.fixture(scope="session")
def detector_minimal():
    return PIIDetector(PreserveConfig(sensitivity_level=SensitivityLevel.MINIMAL))


@pytest.fixture(scope="session")
def detector_standard():
    return PIIDetector(PreserveConfig(sensitivity_level=SensitivityLevel.STANDARD))


@pytest.fixture(scope="session")
def detector_aggressive():
    return PIIDetector(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))


@pytest.fixture(scope="session")
def scrubber():
    return Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.STANDARD))


@pytest.fixture(scope="session")
def aggressive_scrubber():
    return Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
