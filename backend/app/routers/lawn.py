"""草坪管理接口：登记斑秃、复壮作业、验收复壮，以及看板与班次汇总。

错误消息一律来自业务层原文，ActionResult.ok=False / HTTP 400 都带上原因，
前端不允许再用通用文案把它吞掉。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.lawn import LawnError, LawnService

router = APIRouter(prefix="/api/lawn", tags=["草坪管理"])

service = LawnService()

STATUSES = ["良好", "斑秃", "退化", "已复壮"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按草坪编号检索"),
    status: str | None = Query(default=None, description="良好、斑秃、退化、已复壮"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按草坪编号与状态过滤草坪管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/board", response_model=dict)
def lawn_board() -> dict[str, Any]:
    """养护看板：斑秃面积按复壮明细实时重算，只统计复壮前没处理完的斑秃。"""
    return service.board()


@router.get("/shift-summary", response_model=dict)
def lawn_shift_summary(
    shift: str | None = Query(default=None, description="按班次过滤复壮明细，如 白班、夜班"),
) -> dict[str, Any]:
    """班次汇总：斑秃合计、复壮合计与明细同源计算，合计必等于明细之和。"""
    return service.shift_summary(shift=shift)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出草坪管理清单：返回当前全量数据，字段口径与列表、详情一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "lawn", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条草坪明细（含复壮明细）；草种、斑秃面积与列表同源。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"草坪 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条草坪，缺字段或面积非法时说明原因而不是静默丢弃。"""
    try:
        entry, missing = service.create_entry(payload.values)
    except LawnError as exc:
        return ActionResult(ok=False, message=str(exc))
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="草坪已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改草坪资料（草种、面积、返青情况等）；斑秃面积超过草坪面积会被拦下并写明原因。"""
    try:
        entry = service.update_entry(entry_id, payload.values)
    except LawnError as exc:
        return ActionResult(ok=False, message=str(exc))
    return ActionResult(ok=True, message="草坪资料已保存", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """登记斑秃 / 复壮作业 / 验收复壮。

    复壮登记重复提交同一片草坪只认第一次；不允许的动作或状态会被拦下，原因原样返回。
    """
    action = str(payload.values.get("action") or "").strip()
    try:
        entry, message = service.run_action(entry_id, action, payload.values)
    except LawnError as exc:
        return ActionResult(ok=False, message=str(exc))
    return ActionResult(ok=True, message=message, entry=entry)
