"""草坪管理统计与保存口径的回归测试。

覆盖：
1. 斑秃面积修改后能保存，列表/详情/汇总读到同一个数；
2. 复壮登记后看板与班次汇总的斑秃合计跟着减；
3. 同一片草坪重复提交复壮只认第一次；
4. 班次汇总斑秃合计 = 明细中斑秃草坪之和，重复刷新结果稳定；
5. 斑秃面积超过草坪面积不许保存，错误原因原样带出；
6. 接口业务错误原样返回（前端不吞错）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store


@pytest.fixture()
def client() -> TestClient:
    """每个用例用一份全新的内存数据，避免相互污染。"""
    from app.seed import SEED_ROWS

    store._tables = {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}
    return TestClient(app)


def test_bare_area_update_persists_everywhere(client: TestClient) -> None:
    payload = {"values": {"斑秃面积": 88.5, "草种类型": "早熟禾-改", "返青情况": "部分返青"}}
    resp = client.put("/api/lawn/1", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    listing = client.get("/api/lawn").json()["items"]
    row1 = next(row for row in listing if row["id"] == 1)
    detail = client.get("/api/lawn/1").json()
    assert row1["斑秃面积"] == 88.5 == detail["斑秃面积"]
    assert row1["草种类型"] == "早熟禾-改" == detail["草种类型"]
    assert row1["返青情况"] == "部分返青" == detail["返青情况"]

    board = client.get("/api/lawn/board").json()
    # #1 此时状态仍是「良好」，不进斑秃合计；登记斑秃后进合计且数值就是保存值
    client.post("/api/lawn/1/actions", json={"values": {"action": "登记斑秃"}})
    board = client.get("/api/lawn/board").json()
    assert board["斑秃合计面积"] == pytest.approx(88.5 + 120 + 80)
    detail_row = next(item for item in board["斑秃明细"] if item["草坪编号"] == "LAWN-0001")
    assert detail_row["斑秃面积"] == 88.5
    assert detail_row["草种类型"] == "早熟禾-改"


def test_rejuvenation_reduces_totals_and_is_idempotent(client: TestClient) -> None:
    before = client.get("/api/lawn/board").json()["斑秃合计面积"]
    first = client.post("/api/lawn/2/actions", json={"values": {"action": "复壮作业", "班次": "白班"}})
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert first.json()["entry"]["斑秃面积"] == 0

    after = client.get("/api/lawn/board").json()
    assert after["斑秃合计面积"] == pytest.approx(before - 120)
    assert all(item["草坪编号"] != "LAWN-0002" for item in after["斑秃明细"])

    duplicate = client.post("/api/lawn/2/actions", json={"values": {"action": "复壮作业", "班次": "夜班"}})
    assert duplicate.status_code == 200
    body = duplicate.json()
    assert body["ok"] is False
    assert "只认第一次" in body["message"]

    # 第二次没有产生新明细，合计保持不变
    again = client.get("/api/lawn/board").json()
    assert again["斑秃合计面积"] == after["斑秃合计面积"]


def test_shift_summary_total_equals_details_and_is_stable(client: TestClient) -> None:
    client.post("/api/lawn/2/actions", json={"values": {"action": "复壮作业", "班次": "白班"}})
    client.post("/api/lawn/4/actions", json={"values": {"action": "复壮作业", "班次": "夜班"}})
    # 重复提交只认第一次
    client.post("/api/lawn/2/actions", json={"values": {"action": "复壮作业", "班次": "夜班"}})

    first = client.get("/api/lawn/shift-summary").json()
    second = client.get("/api/lawn/shift-summary").json()
    assert first == second

    detail_sum = round(sum(item["复壮面积"] for item in first["复壮明细"]), 2)
    assert first["复壮面积合计"] == detail_sum == first["明细复壮面积之和"]
    assert first["斑秃合计"] == 0  # 两块斑秃都登记了复壮

    shift_rows = {item["班次"]: item for item in first["班次汇总"]}
    assert shift_rows["白班"]["复壮条数"] == 2  # 种子里 #3 白班 + #2
    assert shift_rows["夜班"]["复壮条数"] == 2  # 种子里 #5 夜班 + #4
    assert shift_rows["白班"]["复壮面积合计"] == pytest.approx(320)
    assert shift_rows["夜班"]["复壮面积合计"] == pytest.approx(130)


def test_bare_area_larger_than_lawn_area_rejected_with_reason(client: TestClient) -> None:
    resp = client.put("/api/lawn/1", json={"values": {"斑秃面积": 1200}})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert "超过草坪面积" in body["message"]
    assert "1200" in body["message"] and "1000" in body["message"]
    # 没保存进去：详情仍是原值
    assert client.get("/api/lawn/1").json()["斑秃面积"] == 0

    # 非数字也拦下并写明原因
    bad_text = client.put("/api/lawn/1", json={"values": {"斑秃面积": "abc"}}).json()
    assert bad_text["ok"] is False and "必须是数字" in bad_text["message"]


def test_business_error_messages_pass_through_verbatim(client: TestClient) -> None:
    # 不存在的草坪走 HTTP 404，detail 原样
    missing = client.get("/api/lawn/999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "草坪 999 不存在或已归档"

    # 非法动作走 ActionResult.ok=False，message 原样
    bad_action = client.post("/api/lawn/1/actions", json={"values": {"action": "乱操作"}})
    assert bad_action.json()["ok"] is False
    assert "乱操作" in bad_action.json()["message"]

    # 状态不对：#3 已是退化，不能再登记斑秃
    wrong_status = client.post("/api/lawn/3/actions", json={"values": {"action": "登记斑秃"}})
    body = wrong_status.json()
    assert body["ok"] is False
    assert "退化" in body["message"]


def test_acceptance_flow_only_after_rejuvenation(client: TestClient) -> None:
    # 斑秃状态不能直接验收
    early = client.post("/api/lawn/2/actions", json={"values": {"action": "验收复壮"}}).json()
    assert early["ok"] is False
    assert "斑秃" in early["message"]

    client.post("/api/lawn/2/actions", json={"values": {"action": "复壮作业", "班次": "白班"}})
    accepted = client.post("/api/lawn/2/actions", json={"values": {"action": "验收复壮"}}).json()
    assert accepted["ok"] is True
    assert accepted["entry"]["草坪状态"] == "已复壮"

    again = client.post("/api/lawn/2/actions", json={"values": {"action": "验收复壮"}}).json()
    assert again["ok"] is False and "已复壮" in again["message"]


def test_create_keeps_all_fields(client: TestClient) -> None:
    resp = client.post("/api/lawn", json={"values": {
        "草坪编号": "LAWN-NEW",
        "草种类型": "剪股颖",
        "草坪面积": "300",
        "斑秃面积": "30",
        "修剪频率": "每周1次",
        "灌溉方式": "喷灌",
        "返青情况": "少量返青",
    }})
    body = resp.json()
    assert body["ok"] is True, body
    entry = body["entry"]
    assert entry["草种类型"] == "剪股颖"
    assert entry["草坪面积"] == 300 and entry["斑秃面积"] == 30
    assert entry["修剪频率"] == "每周1次" and entry["返青情况"] == "少量返青"

    missing = client.post("/api/lawn", json={"values": {"草坪编号": "LAWN-X"}}).json()
    assert missing["ok"] is False and "缺少必填字段" in missing["message"]
