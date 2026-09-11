"""Approval workflow integration tests (FR-9/FR-17/FR-18).

Covers the deterministic policy escalation (money threshold -> HIGH ->
approval required), the purchase-order PENDING_APPROVAL -> APPROVED
lifecycle, the human decision endpoints, and role gating on decisions.
"""

import uuid

from app.agents.orchestrator import run_agent
from app.core.llm.mock import MockProvider
from app.models.agent import AgentSession, AgentTask
from app.models.enums import AgentSessionStatus, AgentTaskStatus, BusinessRole


async def _new_user_and_task(client, business_id, db_session) -> tuple[str, str, str]:
    register = await client.post(
        "/api/auth/register",
        json={"email": f"approval-{uuid.uuid4().hex[:8]}@example.com", "password": "a-strong-password", "full_name": "Approval Tester"},
    )
    user_id = register.json()["user"]["id"]
    token = register.json()["access_token"]
    session = AgentSession(
        business_id=business_id,
        user_id=uuid.UUID(user_id),
        status=AgentSessionStatus.RUNNING,
        user_message="test",
    )
    db_session.add(session)
    await db_session.flush()
    task = AgentTask(session_id=session.id, status=AgentTaskStatus.RUNNING)
    db_session.add(task)
    await db_session.flush()
    return token, user_id, str(task.id)


async def _seed_supplier_and_product(client, headers, price="200.00"):
    product = (
        await client.post(
            "/api/products", json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "250.00"}, headers=headers
        )
    ).json()
    supplier = (await client.post("/api/suppliers", json={"name": "Metro"}, headers=headers)).json()
    await client.post(
        f"/api/suppliers/{supplier['id']}/products",
        json={"product_id": product["id"], "price": price, "lead_time_days": 3},
        headers=headers,
    )
    return supplier, product


async def test_high_risk_po_creates_approval_request_and_stops(client, business, db_session):
    """With a money-threshold policy, an agent-proposed PO above the threshold
    is created in PENDING_APPROVAL and an approval request is opened — the
    agent does NOT execute it.
    """
    headers = business["owner_headers"]
    supplier, product = await _seed_supplier_and_product(client, headers, price="200.00")
    # 5 x 200 = 1000 >= threshold 500 -> HIGH risk.
    await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "500.00"}},
        headers=headers,
    )
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {
                "tool": "extract_purchase_order",
                "arguments": {"supplier_query": "Metro", "items": [{"product_query": "coffee", "quantity": 5}]},
            },
        ]
    )
    state = await run_agent(
        provider,
        db_session,
        business_id=business["business_id"],
        user_id=uuid.UUID(user_id),
        role=BusinessRole.OWNER,
        task_id=uuid.UUID(task_id),
        message="Prepare a purchase order from Metro for 5 coffee packets",
    )
    assert "needs a human approval" in state["reply"]
    assert state["needs_approval"] is True

    approvals = (await client.get("/api/approvals?status_filter=PENDING", headers=headers)).json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["action"] == "create_purchase_order"
    assert approval["target_type"] == "purchase_order"
    assert approval["risk_level"] == "HIGH"

    po = (await client.get(f"/api/purchase-orders/{approval['target_id']}", headers=headers)).json()
    assert po["status"] == "PENDING_APPROVAL"

    # Not sent: cannot send a PENDING_APPROVAL PO.
    send = await client.post(f"/api/purchase-orders/{po['id']}/send", headers=headers)
    assert send.status_code == 409


async def test_approve_transitions_po_to_approved_then_send(client, business, db_session):
    headers = business["owner_headers"]
    await _seed_supplier_and_product(client, headers, price="200.00")
    await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "500.00"}},
        headers=headers,
    )
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)
    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {"tool": "extract_purchase_order", "arguments": {"supplier_query": "Metro", "items": [{"product_query": "coffee", "quantity": 5}]}},
        ]
    )
    await run_agent(
        provider, db_session, business_id=business["business_id"], user_id=uuid.UUID(user_id),
        role=BusinessRole.OWNER, task_id=uuid.UUID(task_id),
        message="Prepare a purchase order from Metro for 5 coffee packets",
    )
    approval = (await client.get("/api/approvals?status_filter=PENDING", headers=headers)).json()[0]
    po_id = approval["target_id"]

    approve = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "OK"}, headers=headers
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"

    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert po["status"] == "APPROVED"

    send = await client.post(f"/api/purchase-orders/{po_id}/send", headers=headers)
    assert send.status_code == 200
    assert send.json()["status"] == "SENT"


async def test_employee_cannot_approve_high_risk(client, business, employee_headers, db_session):
    headers = business["owner_headers"]
    await _seed_supplier_and_product(client, headers, price="200.00")
    await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "500.00"}},
        headers=headers,
    )
    # Owner runs the agent to open a HIGH-risk approval request.
    _, owner_user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)
    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {"tool": "extract_purchase_order", "arguments": {"supplier_query": "Metro", "items": [{"product_query": "coffee", "quantity": 5}]}},
        ]
    )
    await run_agent(
        provider, db_session, business_id=business["business_id"], user_id=uuid.UUID(owner_user_id),
        role=BusinessRole.OWNER, task_id=uuid.UUID(task_id),
        message="Prepare a purchase order from Metro for 5 coffee packets",
    )
    approval = (await client.get("/api/approvals?status_filter=PENDING", headers=headers)).json()[0]

    # EMPLOYEE cannot approve a HIGH-risk request (default APPROVAL_ROLES).
    resp = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "nope"}, headers=employee_headers
    )
    assert resp.status_code == 403

    # Still pending; owner can approve.
    still_pending = (await client.get(f"/api/approvals/{approval['id']}", headers=headers)).json()
    assert still_pending["status"] == "PENDING"


async def test_reject_leaves_po_cancelled(client, business, db_session):
    headers = business["owner_headers"]
    await _seed_supplier_and_product(client, headers, price="200.00")
    await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "500.00"}},
        headers=headers,
    )
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)
    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {"tool": "extract_purchase_order", "arguments": {"supplier_query": "Metro", "items": [{"product_query": "coffee", "quantity": 5}]}},
        ]
    )
    await run_agent(
        provider, db_session, business_id=business["business_id"], user_id=uuid.UUID(user_id),
        role=BusinessRole.OWNER, task_id=uuid.UUID(task_id),
        message="Prepare a purchase order from Metro for 5 coffee packets",
    )
    approval = (await client.get("/api/approvals?status_filter=PENDING", headers=headers)).json()[0]
    po_id = approval["target_id"]

    reject = await client.post(
        f"/api/approvals/{approval['id']}/reject", json={"decision_note": "No"}, headers=headers
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "REJECTED"

    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert po["status"] == "CANCELLED"


# --- Phase 9: multi-stage (chained) approval ---


async def _set_stages_policy(client, headers, stages: int):
    await client.put(
        "/api/policies/stages",
        json={"policy_type": "APPROVAL_STAGES", "key": "stages", "value": {"stages": stages}},
        headers=headers,
    )


async def _admin_headers(client, business) -> dict:
    register = await client.post(
        "/api/auth/register",
        json={"email": f"admin-{uuid.uuid4().hex[:8]}@example.com", "password": "a-strong-password", "full_name": "Admin Tester"},
    )
    token = register.json()["access_token"]
    await client.post(
        "/api/businesses/members",
        json={"email": register.json()["user"]["email"], "role": "ADMIN"},
        headers=business["owner_headers"],
    )
    return {"Authorization": f"Bearer {token}", "X-Business-Id": business["business_id"]}


async def _open_high_risk_po_approval(client, business, db_session) -> dict:
    headers = business["owner_headers"]
    await _seed_supplier_and_product(client, headers, price="200.00")
    await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "500.00"}},
        headers=headers,
    )
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)
    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {"tool": "extract_purchase_order", "arguments": {"supplier_query": "Metro", "items": [{"product_query": "coffee", "quantity": 5}]}},
        ]
    )
    await run_agent(
        provider, db_session, business_id=business["business_id"], user_id=uuid.UUID(user_id),
        role=BusinessRole.OWNER, task_id=uuid.UUID(task_id),
        message="Prepare a purchase order from Metro for 5 coffee packets",
    )
    return (await client.get("/api/approvals?status_filter=PENDING", headers=headers)).json()[0]


async def test_two_stage_approval_needs_two_different_approvers(client, business, db_session):
    """With APPROVAL_STAGES=2, a HIGH-risk PO request needs two sequential
    approvals by different people; the PO only leaves PENDING_APPROVAL after
    the final stage approves."""
    headers = business["owner_headers"]
    admin_headers = await _admin_headers(client, business)
    await _set_stages_policy(client, headers, 2)
    approval = await _open_high_risk_po_approval(client, business, db_session)
    po_id = approval["target_id"]

    assert approval["required_stages"] == 2
    assert approval["current_stage"] == 1
    assert [s["status"] for s in approval["steps"]] == ["PENDING", "PENDING"]

    # Stage 1: owner approves. The request stays PENDING for the next stage.
    first = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "stage 1 ok"}, headers=headers
    )
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "PENDING"
    assert body["current_stage"] == 2
    assert body["steps"][0]["status"] == "APPROVED"
    assert body["steps"][1]["status"] == "PENDING"

    # The PO is still gated while a stage remains.
    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert po["status"] == "PENDING_APPROVAL"

    # The same person cannot approve the next stage (no rubber-stamping).
    same_user = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "me again"}, headers=headers
    )
    assert same_user.status_code == 409

    # A different approver (ADMIN) completes the chain.
    second = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "stage 2 ok"}, headers=admin_headers
    )
    assert second.status_code == 200
    assert second.json()["status"] == "APPROVED"
    assert second.json()["current_stage"] == 2
    assert [s["status"] for s in second.json()["steps"]] == ["APPROVED", "APPROVED"]

    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert po["status"] == "APPROVED"
    send = await client.post(f"/api/purchase-orders/{po_id}/send", headers=headers)
    assert send.status_code == 200


async def test_rejection_at_second_stage_cancels_po(client, business, db_session):
    """A rejection at any stage ends the chain and cancels the gated PO."""
    headers = business["owner_headers"]
    admin_headers = await _admin_headers(client, business)
    await _set_stages_policy(client, headers, 2)
    approval = await _open_high_risk_po_approval(client, business, db_session)
    po_id = approval["target_id"]

    await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "stage 1 ok"}, headers=headers
    )
    rejected = await client.post(
        f"/api/approvals/{approval['id']}/reject", json={"decision_note": "no"}, headers=admin_headers
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["steps"][1]["status"] == "REJECTED"

    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert po["status"] == "CANCELLED"


async def test_default_single_stage_when_no_policy(client, business, db_session):
    """Without an APPROVAL_STAGES policy the behavior is exactly Phase 5: one
    decision approves the request (required_stages defaults to 1)."""
    headers = business["owner_headers"]
    approval = await _open_high_risk_po_approval(client, business, db_session)
    assert approval["required_stages"] == 1
    assert approval["current_stage"] == 1
    assert len(approval["steps"]) == 1

    approve = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "OK"}, headers=headers
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"
    po = (await client.get(f"/api/purchase-orders/{approval['target_id']}", headers=headers)).json()
    assert po["status"] == "APPROVED"


# --- Phase 10 fix: approved HIGH-risk ORDERS are executed ---


async def _open_high_risk_order_approval(client, business, db_session) -> dict:
    headers = business["owner_headers"]
    customer = (await client.post("/api/customers", json={"name": "Rahul"}, headers=headers)).json()
    product = (
        await client.post(
            "/api/products", json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "250.00"}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 10}, headers=headers
    )
    await client.put(
        "/api/policies/order_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "order_threshold", "value": {"amount": "500.00"}},
        headers=headers,
    )
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)
    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_ORDER", "summary": "Order"}},
            {
                "tool": "extract_order",
                "arguments": {"customer_query": "Rahul", "items": [{"product_query": "coffee", "quantity": 3}]},
            },
        ]
    )
    state = await run_agent(
        provider, db_session, business_id=business["business_id"], user_id=uuid.UUID(user_id),
        role=BusinessRole.OWNER, task_id=uuid.UUID(task_id),
        message="Create an order for Rahul with 3 coffee packets",
    )
    assert "needs a human approval" in state["reply"]
    return (await client.get("/api/approvals?status_filter=PENDING", headers=headers)).json()[0]


async def test_approved_high_risk_order_is_executed(client, business, db_session):
    """Approving a HIGH-risk order request creates the order: stock decrements,
    an invoice is generated, and the approval request links to the order."""
    headers = business["owner_headers"]
    approval = await _open_high_risk_order_approval(client, business, db_session)

    # Nothing was created while the request waited.
    assert approval["target_type"] is None
    orders = (await client.get("/api/orders", headers=headers)).json()
    assert orders == []

    approve = await client.post(
        f"/api/approvals/{approval['id']}/approve", json={"decision_note": "OK"}, headers=headers
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["status"] == "APPROVED"
    assert body["target_type"] == "order"
    assert body["target_id"]

    orders = (await client.get("/api/orders", headers=headers)).json()
    assert len(orders) == 1
    order = orders[0]
    assert order["customer_name"] == "Rahul"
    assert order["total"] == "750.00"
    assert order["invoice_number"]

    inventory = (await client.get("/api/inventory", headers=headers)).json()
    assert inventory[0]["quantity_on_hand"] == 7  # 10 - 3


async def test_rejected_high_risk_order_creates_nothing(client, business, db_session):
    headers = business["owner_headers"]
    approval = await _open_high_risk_order_approval(client, business, db_session)

    reject = await client.post(
        f"/api/approvals/{approval['id']}/reject", json={"decision_note": "No"}, headers=headers
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "REJECTED"

    orders = (await client.get("/api/orders", headers=headers)).json()
    assert orders == []
    inventory = (await client.get("/api/inventory", headers=headers)).json()
    assert inventory[0]["quantity_on_hand"] == 10  # untouched
