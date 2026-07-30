from cosmos_control_tower.audit.redaction import redact_record


def test_personal_data_is_redacted_recursively() -> None:
    source = {
        "NAME": "Test Person",
        "PHONE": "+7 999 000-00-00",
        "nested": {"email": "person@example.test"},
        "note": "Call +7 (999) 111-22-33 or person@example.test",
        "safe_id": "42",
    }
    result = redact_record(source)
    assert result["NAME"] == "[REDACTED]"
    assert result["PHONE"] == "[REDACTED]"
    assert result["nested"]["email"] == "[REDACTED]"
    assert "999" not in result["note"]
    assert "person@" not in result["note"]
    assert result["safe_id"] == "42"
