from alchemi.endpoints.copilot_marketplace_endpoints import _is_item_visible_to_subject


def test_should_match_user_assignment_case_insensitive_email() -> None:
    item = {
        "metadata": {
            "assignments": [
                {"scope_type": "user", "scope_id": "HELLO@zentience.co"},
            ]
        }
    }
    auth_ctx = {
        "user_id": "u-1",
        "user_email": "hello@zentience.co",
        "teams": [],
    }
    assert _is_item_visible_to_subject(item, auth_ctx, "acc-1") is True


def test_should_match_group_assignment_from_organization_ids_list() -> None:
    item = {
        "metadata": {
            "assignments": [
                {"scope_type": "group", "scope_id": "org-123"},
            ]
        }
    }
    auth_ctx = {
        "user_id": "u-1",
        "user_email": "hello@zentience.co",
        "teams": [],
        "organization_id": None,
        "organization_ids": ["org-123", "org-456"],
    }
    assert _is_item_visible_to_subject(item, auth_ctx, "acc-1") is True


def test_should_allow_all_when_no_assignments_present() -> None:
    item = {"metadata": {}}
    auth_ctx = {
        "user_id": "u-1",
        "user_email": "hello@zentience.co",
        "teams": [],
    }
    assert _is_item_visible_to_subject(item, auth_ctx, "acc-1") is True
