from cosmos_control_tower.audit.portal import _only, _rows


def test_portal_helpers_drop_unapproved_fields() -> None:
    payload = {"result": [{"ID": "1", "NAME": "Sales", "EMAIL": "hidden@example.test"}]}
    assert _only(_rows(payload), {"ID", "NAME"}) == [{"ID": "1", "NAME": "Sales"}]
