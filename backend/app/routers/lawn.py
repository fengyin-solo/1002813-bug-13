"""草坪管理接口：维护草坪，覆盖斑秃登记、复壮登记与验收、班次汇总、养护看板。

所有面积类数字以服务层实时计算为准，接口不直接接收“斑秃面积”保存值，
业务校验失败统一返回 400，detail 即面向用户的原文原因，前端直接展示。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.lawn import BusinessError, LawnService

router = APIRouter(prefix="/api/lawn", tags=["草坪管理"])

service = LawnService()

STATUSES = ["良好", "斑秃", "退化", "已复壮"]
SHIFTS = ["早班", "中班", "晚班"]


def _required(values: dict[str, Any], key: str) -> Any:
    if key not in values or str(values.get(key) or "").strip() == "":
        raise HTTPException(status_code=400, detail=f"缺少必填参数：{key}")
    return values.get(key)


# 注意：具体路径要声明在 /{entry_id} 之前，否则会被当成编号匹配。

@router.get("/dashboard")
def lawn_dashboard() -> dict[str, Any]:
    """养护看板：斑秃面积合计随斑秃/复壮明细实时重算。"""
    return service.dashboard()


@router.get("/rejuvenations")
def list_rejuvenations(
    shift: str | None = Query(default=None, description="按班次筛选：早班、中班、晚班"),
) -> dict[str, Any]:
    """复壮明细：每行带出主表当前的草种与斑秃面积，和列表/详情同源。"""
    items = service.list_rejuvenations(shift)
    return {"total": len(items), "items": items}


@router.get("/shifts/summary")
def shift_summary() -> dict[str, Any]:
    """班次汇总：斑秃合计由复壮明细逐行累加，合计必与明细一致。"""
    items = service.shift_summary()
    return {"items": items}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出草坪管理清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "lawn", "total": total, "items": items}


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


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条草坪明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"草坪 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一片草坪，缺字段或面积非法时说明原因而不是静默丢弃。"""
    try:
        entry, missing = service.create_entry(payload.values)
    except BusinessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="草坪已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改草坪基础资料（草种、面积、返青情况等），保存后立即按明细重算斑秃面积。

    斑秃面积超过草坪面积时拒绝保存，原因原样返回。
    """
    try:
        entry = service.update_entry(entry_id, payload.values)
    except BusinessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ActionResult(ok=True, message="草坪资料已保存", entry=entry)


@router.post("/{entry_id}/bald", response_model=ActionResult)
def register_bald(entry_id: int, payload: EntryPayload) -> ActionResult:
    """登记斑秃：写入斑秃明细；累计斑秃面积超过草坪面积时拒绝并写明原因。"""
    values = payload.values
    bald_area = _required(values, "斑秃面积")
    shift = _required(values, "班次")
    try:
        record = service.register_bald(
            entry_id,
            bald_area=bald_area,
            shift=str(shift),
            green_status=str(values.get("返青情况") or "").strip() or None,
        )
    except BusinessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    entry = service.get_entry(entry_id)
    return ActionResult(
        ok=True,
        message="斑秃已登记，待处理斑秃面积已更新",
        entry={**(entry or {}), "bald_record": record},
    )


@router.post("/{entry_id}/rejuvenations", response_model=ActionResult)
def register_rejuvenation(entry_id: int, payload: EntryPayload) -> ActionResult:
    """登记复壮：合计随即扣减；同一片草坪重复提交只认第一次（request_id 幂等）。"""
    values = payload.values
    shift = _required(values, "班次")
    try:
        record = service.register_rejuvenation(
            entry_id,
            shift=str(shift),
            request_id=str(values.get("request_id") or "").strip() or None,
        )
    except BusinessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    message = "复壮已登记（重复提交，已沿用第一次结果）" if record.get("duplicated") else "复壮已登记，斑秃合计已扣减"
    return ActionResult(ok=True, message=message, entry=record)


@router.post("/rejuvenations/{rejuv_id}/accept", response_model=ActionResult)
def accept_rejuvenation(rejuv_id: int) -> ActionResult:
    """验收复壮：斑秃明细置为已处理，草坪进入已复壮。"""
    try:
        record = service.accept_rejuvenation(rejuv_id)
    except BusinessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ActionResult(ok=True, message="复壮已验收", entry=record)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条草坪执行登记斑秃、复壮作业、验收复壮的旧动作入口（保留兼容）。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
