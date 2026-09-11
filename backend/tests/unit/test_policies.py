"""Deterministic policy engine unit tests (FR-16/FR-17, ADR-004).

The policy engine must classify purely from structured inputs and business
policy rows — no LLM, no prompt influence.
"""

import uuid
from decimal import Decimal

import pytest

from app.models.business_policy import BusinessPolicy
from app.models.enums import PolicyType
from app.policies.policies import (
    approval_roles_for,
    approval_stages_for,
    money_threshold,
)
from app.policies.risk import RiskLevel, classify_action
from app.tools.registry import registry


def _policy(policy_type: PolicyType, key: str, value: dict, is_active: bool = True) -> BusinessPolicy:
    return BusinessPolicy(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        policy_type=policy_type,
        key=key,
        value=value,
        is_active=is_active,
        updated_by_user_id=uuid.uuid4(),
    )


def test_classify_action_still_returns_tool_declared_risk():
    assert classify_action(registry.get("create_order"), {"customer_id": "x", "items": []}) == RiskLevel.MEDIUM
    assert classify_action(registry.get("check_stock"), {"search": "coffee"}) == RiskLevel.LOW


def test_money_threshold_returns_smallest_active_amount():
    policies = [
        _policy(PolicyType.MONEY_THRESHOLD, "po_threshold", {"amount": "5000"}),
        _policy(PolicyType.MONEY_THRESHOLD, "order_threshold", {"amount": "1000"}),
    ]
    assert money_threshold(policies) == Decimal("1000")


def test_money_threshold_none_when_no_policy():
    assert money_threshold([]) is None
    assert money_threshold([_policy(PolicyType.APPROVAL_ROLES, "roles", {"roles": ["OWNER"]})]) is None


def test_money_threshold_ignores_inactive_and_bad_values():
    policies = [
        _policy(PolicyType.MONEY_THRESHOLD, "a", {"amount": "1000"}, is_active=False),
        _policy(PolicyType.MONEY_THRESHOLD, "b", {"amount": "not-a-number"}),
    ]
    assert money_threshold(policies) is None


def test_approval_roles_defaults_to_owner_admin():
    assert approval_roles_for([], RiskLevel.HIGH) == ["OWNER", "ADMIN"]
    assert approval_roles_for([_policy(PolicyType.APPROVAL_ROLES, "r", {"roles": []})], RiskLevel.HIGH) == []


def test_approval_roles_honors_policy():
    policies = [_policy(PolicyType.APPROVAL_ROLES, "r", {"roles": ["OWNER", "ADMIN", "EMPLOYEE"]})]
    assert approval_roles_for(policies, RiskLevel.MEDIUM) == ["OWNER", "ADMIN", "EMPLOYEE"]


def test_approval_stages_defaults_to_one():
    assert approval_stages_for([]) == 1
    assert approval_stages_for([_policy(PolicyType.MONEY_THRESHOLD, "t", {"amount": "100"})]) == 1
    # Invalid / inactive values are ignored -> default 1.
    assert approval_stages_for([_policy(PolicyType.APPROVAL_STAGES, "s", {"stages": 0})]) == 1
    assert approval_stages_for([_policy(PolicyType.APPROVAL_STAGES, "s", {"stages": "x"})]) == 1
    assert approval_stages_for([_policy(PolicyType.APPROVAL_STAGES, "s", {"stages": 2}, is_active=False)]) == 1


def test_approval_stages_honors_policy():
    policies = [_policy(PolicyType.APPROVAL_STAGES, "stages", {"stages": 3})]
    assert approval_stages_for(policies) == 3
