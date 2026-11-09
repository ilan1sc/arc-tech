import json
from pathlib import Path

import jsonschema

from shared.schemas import EffortRange, SoftwareCapabilityPassport

DATA = Path(__file__).resolve().parents[1] / "data"
DRIVE_SCHEMA = json.loads((DATA / "software_capability_passport.schema.json").read_text())


def test_drive_example_parses_into_pydantic_model():
    ex = json.loads((DATA / "software_capability_passport.example.json").read_text())
    p = SoftwareCapabilityPassport.model_validate(ex)
    assert p.passport_id == "swisslink-example-001"


def test_pydantic_output_is_valid_against_drive_schema():
    ex = json.loads((DATA / "software_capability_passport.example.json").read_text())
    dumped = json.loads(SoftwareCapabilityPassport.model_validate(ex).model_dump_json(exclude_none=True))
    jsonschema.validate(dumped, DRIVE_SCHEMA)


def test_unknown_is_not_zero():
    a = EffortRange(low=10, base=20, high=30)
    assert not (a + EffortRange()).known
    assert (a + a).base == 40
