from cosmos_control_tower.audit.redaction import redact_record
from cosmos_control_tower.audit.service import AuditService


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


def test_safe_sample_keeps_only_explicit_structural_fields() -> None:
    payload = {
        "result": [
            {
                "ID": "1",
                "STATUS_ID": "NEW",
                "ASSIGNED_BY_ID": "7",
                "TITLE": "Client full name",
                "PHONE": "+7 999 000-00-00",
                "COMMENTS": "private message",
            }
        ]
    }
    sample = AuditService._safe_sample("crm.lead.list", payload)
    assert sample == [{"ID": "1", "STATUS_ID": "NEW", "ASSIGNED_BY_ID": "7"}]


def test_user_metadata_drops_names_and_contacts() -> None:
    payload = {
        "result": [
            {
                "ID": "7",
                "ACTIVE": True,
                "ADMIN": False,
                "UF_DEPARTMENT": ["3"],
                "NAME": "Employee",
                "EMAIL": "employee@example.test",
            }
        ]
    }
    result = AuditService._sanitize_metadata("user.get", payload)
    assert result == {
        "result": [
            {"ID": "7", "ACTIVE": True, "ADMIN": False, "UF_DEPARTMENT": ["3"]}
        ],
        "count": 1,
    }


def test_field_definitions_keep_schema_but_not_values() -> None:
    payload = {
        "result": {
            "UF_CRM_TEST": {
                "type": "string",
                "title": "Qualified",
                "value": "private client value",
            }
        }
    }
    assert AuditService._sanitize_field_definitions(payload) == {
        "result": {"UF_CRM_TEST": {"type": "string", "title": "Qualified"}}
    }
