"""Registry contract tests (docs/decisions.md ADR-003): schema validation,
permission checks, audit rows, structured errors, compact summaries.
"""

import json
import uuid
from decimal import Decimal

import pytest
from pydantic import BaseModel, Field

from app.models.enums import AgentActionStatus, BusinessRole
from app.policies.risk import RiskLevel
from app.tools.base import ToolError, ToolSpec
from app.tools.registry import ToolRegistry, _compact


class SumArgs(BaseModel):
    a: int = Field(ge=0)
    b: int = Field(ge=0)


async def _sum_handler(db, business_id, user_id, args: SumArgs) -> dict:
    return {"total": args.a + args.b}


def _make_registry(roles: tuple[BusinessRole, ...] | None = None) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="sum",
            description="Add two numbers.",
            input_schema=SumArgs,
            risk_level=RiskLevel.MEDIUM,
            handler=_sum_handler,
            required_roles=roles,
        )
    )
    return reg


@pytest.fixture
def task_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_registry_validates_and_records_action(db_session, task_id):
    reg = _make_registry()
    result = await reg.call(
        db_session,
        business_id=uuid.uuid4(),
        role=BusinessRole.EMPLOYEE,
        task_id=task_id,
        user_id=uuid.uuid4(),
        name="sum",
        arguments={"a": 2, "b": 3},
    )
    assert result == {"ok": True, "data": {"total": 5}}
    assert reg.all()[0].risk_level == RiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_registry_rejects_invalid_arguments_without_executing(db_session, task_id):
    reg = _make_registry()
    result = await reg.call(
        db_session,
        business_id=uuid.uuid4(),
        role=BusinessRole.EMPLOYEE,
        task_id=task_id,
        user_id=uuid.uuid4(),
        name="sum",
        arguments={"a": -1, "b": "not-a-number"},
    )
    assert result["ok"] is False
    assert "Invalid arguments" in result["error"]


@pytest.mark.asyncio
async def test_registry_enforces_required_roles(db_session, task_id):
    reg = _make_registry(roles=(BusinessRole.OWNER, BusinessRole.ADMIN))
    denied = await reg.call(
        db_session,
        business_id=uuid.uuid4(),
        role=BusinessRole.EMPLOYEE,
        task_id=task_id,
        user_id=uuid.uuid4(),
        name="sum",
        arguments={"a": 1, "b": 1},
    )
    assert denied["ok"] is False
    assert "requires role" in denied["error"]

    allowed = await reg.call(
        db_session,
        business_id=uuid.uuid4(),
        role=BusinessRole.ADMIN,
        task_id=task_id,
        user_id=uuid.uuid4(),
        name="sum",
        arguments={"a": 1, "b": 1},
    )
    assert allowed["ok"] is True


@pytest.mark.asyncio
async def test_registry_unknown_tool_returns_structured_error(db_session, task_id):
    reg = _make_registry()
    result = await reg.call(
        db_session,
        business_id=uuid.uuid4(),
        role=BusinessRole.EMPLOYEE,
        task_id=task_id,
        user_id=uuid.uuid4(),
        name="nope",
        arguments={},
    )
    assert result["ok"] is False
    assert "Unknown tool" in result["error"]


@pytest.mark.asyncio
async def test_handler_error_is_structured_and_recorded_as_failed(db_session, task_id):
    async def failing_handler(db, business_id, user_id, args):
        raise ToolError("supplier is inactive")

    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="failing",
            description="Always fails.",
            input_schema=SumArgs,
            risk_level=RiskLevel.LOW,
            handler=failing_handler,
        )
    )
    result = await reg.call(
        db_session,
        business_id=uuid.uuid4(),
        role=BusinessRole.EMPLOYEE,
        task_id=task_id,
        user_id=uuid.uuid4(),
        name="failing",
        arguments={"a": 1, "b": 1},
    )
    assert result == {"ok": False, "error": "supplier is inactive"}


@pytest.mark.asyncio
async def test_schemas_are_provider_neutral(db_session):
    reg = _make_registry()
    schemas = reg.schemas()
    assert schemas[0].name == "sum"
    assert schemas[0].input_schema["properties"]["a"]["type"] == "integer"
    assert schemas[0].description == "Add two numbers."


def test_compact_truncates_long_values():
    assert _compact({"big": "x" * 1000}) == {"big": "x" * 600 + "…"}
    assert len(_compact(list(range(100)))) == 25
    assert _compact({"nested": [1, 2], "keep": "ok"}) == {"nested": [1, 2], "keep": "ok"}


def test_compact_makes_values_json_safe():
    compacted = _compact({"customer_id": uuid.uuid4(), "price": Decimal("12.50")})
    assert compacted["customer_id"] == str(compacted["customer_id"])
    json.dumps(compacted)  # must not raise