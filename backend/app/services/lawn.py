"""草坪管理业务规则：斑秃登记、复壮登记与验收、字段校验、汇总口径都收在这里。

口径约定（列表、详情、养护看板、班次汇总共用同一份计算，避免两处读出两个数）：
- 每片草坪在主表里只存基础资料（草种类型、草坪面积、返青情况等）。
- 斑秃以明细记录（_lawn_bald）为准：active=True 表示“复壮前还没处理”的斑秃。
- 复壮登记（_lawn_rejuvenations）会关联斑秃明细；登记即视为该斑秃已处理，
  因此“待处理斑秃面积”= 未被任何复壮明细关联的 active 斑秃面积之和。
- 主表上的“斑秃面积”展示字段由上面的明细实时重算，任何接口都不接受外部直接写入，
  所以不存在“改完保存就丢 / 复壮后还停在旧数”。
- 同一片草坪重复提交复壮，按 request_id 幂等：只认第一次，后续原样返回首次结果。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "lawn"
BALD_TABLE = "_lawn_bald"
REJUV_TABLE = "_lawn_rejuvenations"

REQUIRED_FIELDS = ["草坪编号", "草种类型", "草坪面积"]
# 允许在编辑入口修改的基础字段；斑秃面积是派生值，不在此列。
EDITABLE_FIELDS = ["草种类型", "草坪面积", "修剪频率", "灌溉方式", "返青情况"]
NUMERIC_FIELDS = ["草坪面积"]
STATUS_ORDER = ["良好", "斑秃", "退化", "已复壮"]
ACTION_RULES = {"登记斑秃": "斑秃", "复壮作业": "退化", "验收复壮": "已复壮"}
NEGATIVE_ACTIONS = []

SHIFTS = ["早班", "中班", "晚班"]


class BusinessError(Exception):
    """业务校验失败：消息要原样透传给前端，写明原因。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_number(value: Any, field: str) -> float:
    """把面积类输入解析成非负数字；非法输入直接报错而不是静默当 0。"""
    if isinstance(value, bool):
        raise BusinessError(f"{field}必须是不小于 0 的数字")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise BusinessError(f"{field}必须是不小于 0 的数字")
    if number < 0:
        raise BusinessError(f"{field}不能为负数")
    return number


class LawnService:
    # ---- 基础读取 -------------------------------------------------------

    def _bald_rows(self) -> list[dict[str, Any]]:
        return store.rows(BALD_TABLE)

    def _rejuvenation_rows(self) -> list[dict[str, Any]]:
        return store.rows(REJUV_TABLE)

    def _next_id(self, rows: list[dict[str, Any]]) -> int:
        return max((int(row.get("id", 0)) for row in rows), default=0) + 1

    def active_bald_rows(self, lawn_id: int | None = None) -> list[dict[str, Any]]:
        """复壮前还没处理的斑秃明细：active 且没有任何复壮登记关联。

        一条复壮登记可能一次关联多块斑秃（bald_id 兼容旧字段，bald_ids 为准），
        只要出现在任意一笔复壮明细里，就不再计入待处理斑秃。
        """
        handled_bald_ids: set[int] = set()
        for row in self._rejuvenation_rows():
            ids = row.get("bald_ids") or ([row["bald_id"]] if row.get("bald_id") is not None else [])
            handled_bald_ids.update(int(bald_id) for bald_id in ids)
        rows = [
            row for row in self._bald_rows()
            if row.get("active") and int(row.get("id", 0)) not in handled_bald_ids
        ]
        if lawn_id is not None:
            rows = [row for row in rows if int(row.get("lawn_id")) == lawn_id]
        return rows

    def pending_bald_area(self, lawn_id: int) -> float:
        """单片草坪“复壮前还没处理”的斑秃合计——所有界面的斑秃面积都取这个数。"""
        total = sum(float(row.get("斑秃面积", 0) or 0) for row in self.active_bald_rows(lawn_id))
        return int(total) if float(total).is_integer() else round(total, 2)

    def _decorate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """给主表记录挂上统一口径的派生字段。"""
        lawn_id = int(entry["id"])
        result = dict(entry)
        result["斑秃面积"] = self.pending_bald_area(lawn_id)
        result["草坪状态"] = entry.get("status")
        return result

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("草坪编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._decorate(entry) if entry else None

    # ---- 保存：登记 / 编辑 ---------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if str(values.get(field) or "").strip() == ""]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        number = _to_number(values.get("草坪面积"), "草坪面积")
        entry = {"id": self._next_id(rows)}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["草坪面积"] = int(number) if number.is_integer() else number
        entry.update({
            field: values.get(field) for field in EDITABLE_FIELDS if field not in REQUIRED_FIELDS
        })
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._decorate(entry), []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> dict[str, Any]:
        """修改基础资料并立即落库。斑秃面积由明细重算，保存后不会丢。

        校验先行：任何一项不通过都保持原值不动，避免“保存失败但数据已被改脏”。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            raise BusinessError(f"草坪 {entry_id} 不存在或已归档")

        candidate = dict(entry)
        for field in EDITABLE_FIELDS:
            if field in values:
                candidate[field] = values[field]
        if "草坪面积" in values:
            candidate["草坪面积"] = self._normalized_area(values["草坪面积"])
        candidate_view = self._decorate(candidate)
        bald_area = float(candidate_view["斑秃面积"])
        lawn_area = _to_number(candidate.get("草坪面积"), "草坪面积")
        if bald_area > lawn_area:
            raise BusinessError(
                f"斑秃面积（{bald_area:g} ㎡）超过草坪面积（{lawn_area:g} ㎡），不允许保存；"
                "请先核实草坪面积或处理部分斑秃后再提交"
            )

        for field in EDITABLE_FIELDS:
            if field in values:
                entry[field] = candidate[field]
        return self._decorate(entry)

    def _normalized_area(self, value: Any) -> float | int:
        number = _to_number(value, "草坪面积")
        return int(number) if number.is_integer() else number

    # ---- 斑秃登记 -------------------------------------------------------

    def register_bald(
        self,
        lawn_id: int,
        *,
        bald_area: Any,
        shift: str,
        green_status: str | None = None,
    ) -> dict[str, Any]:
        entry = store.find(MODULE, lawn_id)
        if entry is None:
            raise BusinessError(f"草坪 {lawn_id} 不存在或已归档")
        area = _to_number(bald_area, "斑秃面积")
        if area <= 0:
            raise BusinessError("斑秃面积必须大于 0，没有斑秃无需登记")
        shift = (shift or "").strip()
        if shift not in SHIFTS:
            raise BusinessError(f"班次必须是：{'、'.join(SHIFTS)}")
        new_total = self.pending_bald_area(lawn_id) + area
        lawn_area = _to_number(entry.get("草坪面积"), "草坪面积")
        if new_total > lawn_area:
            raise BusinessError(
                f"登记后斑秃面积合计（{new_total:g} ㎡）将超过草坪面积（{lawn_area:g} ㎡），"
                "不允许保存；请调小本次斑秃面积"
            )
        rows = self._bald_rows()
        record = {
            "id": self._next_id(rows),
            "lawn_id": lawn_id,
            "斑秃面积": int(area) if area.is_integer() else area,
            "返青情况": (green_status or entry.get("返青情况") or "").strip(),
            "班次": shift,
            "登记时间": _now(),
            "active": True,
        }
        rows.append(record)
        # 返青情况随斑秃登记回写主表，保证列表/详情/明细读到同一个值
        if record["返青情况"]:
            entry["返青情况"] = record["返青情况"]
        entry["status"] = "斑秃"
        entry["abnormal"] = True
        return record

    # ---- 复壮登记（幂等）与验收 ----------------------------------------

    def register_rejuvenation(
        self,
        lawn_id: int,
        *,
        shift: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """登记复壮：把该草坪当前所有待处理斑秃一次性挂到一条复壮明细上。

        同一片草坪重复提交只认第一次：
        - 带相同 request_id 的重复请求，原样返回首次结果；
        - 该草坪已有未验收的复壮登记时，拒绝重复登记。
        """
        entry = store.find(MODULE, lawn_id)
        if entry is None:
            raise BusinessError(f"草坪 {lawn_id} 不存在或已归档")
        shift = (shift or "").strip()
        if shift not in SHIFTS:
            raise BusinessError(f"班次必须是：{'、'.join(SHIFTS)}")

        request_id = (request_id or "").strip() or None
        if request_id:
            for prior in self._rejuvenation_rows():
                if prior.get("request_id") == request_id and int(prior.get("lawn_id")) == lawn_id:
                    return self._rejuvenation_view(prior, duplicated=True)

        pending = self.active_bald_rows(lawn_id)
        if not pending:
            raise BusinessError("该草坪没有复壮前待处理的斑秃，无需重复登记复壮")
        for prior in self._rejuvenation_rows():
            if int(prior.get("lawn_id")) == lawn_id and not prior.get("accepted"):
                raise BusinessError("该草坪已有一笔待验收的复壮登记，重复提交只认第一次")

        area = sum(float(row.get("斑秃面积", 0) or 0) for row in pending)
        rows = self._rejuvenation_rows()
        record = {
            "id": self._next_id(rows),
            "lawn_id": lawn_id,
            "bald_id": int(pending[0]["id"]),
            "bald_ids": [int(row["id"]) for row in pending],
            "复壮面积": int(area) if float(area).is_integer() else round(area, 2),
            "班次": shift,
            "登记时间": _now(),
            "验收时间": None,
            "accepted": False,
            "request_id": request_id,
        }
        rows.append(record)
        entry["status"] = "退化"
        entry["pending"] = True
        return self._rejuvenation_view(record)

    def accept_rejuvenation(self, rejuv_id: int) -> dict[str, Any]:
        record = next(
            (row for row in self._rejuvenation_rows() if int(row.get("id", 0)) == rejuv_id),
            None,
        )
        if record is None:
            raise BusinessError(f"复壮记录 {rejuv_id} 不存在")
        if record.get("accepted"):
            return self._rejuvenation_view(record)
        record["accepted"] = True
        record["验收时间"] = _now()
        for bald_id in record.get("bald_ids", [record.get("bald_id")]):
            bald = next(
                (row for row in self._bald_rows() if int(row.get("id", 0)) == int(bald_id)),
                None,
            )
            if bald is not None:
                bald["active"] = False
        entry = store.find(MODULE, int(record["lawn_id"]))
        if entry is not None:
            entry["status"] = "已复壮"
            entry["pending"] = False
            entry["abnormal"] = False
        return self._rejuvenation_view(record)

    def list_rejuvenations(self, shift: str | None = None) -> list[dict[str, Any]]:
        shift = (shift or "").strip() or None
        rows = self._rejuvenation_rows()
        if shift:
            rows = [row for row in rows if row.get("班次") == shift]
        return [self._rejuvenation_view(row) for row in rows]

    def _rejuvenation_view(self, record: dict[str, Any], *, duplicated: bool = False) -> dict[str, Any]:
        """复壮明细视图。

        - 斑秃面积：登记复壮时挂账的面积（快照），班次汇总按它逐行累加，口径不变；
        - 剩余斑秃面积：该草坪当前待处理斑秃面积，与列表/详情/看板同源；
        - 草种类型直接取主表当前值，避免两处读到两个草种。
        """
        entry = store.find(MODULE, int(record["lawn_id"])) or {}
        return {
            "id": record["id"],
            "草坪id": record["lawn_id"],
            "草坪编号": entry.get("草坪编号"),
            "草种类型": entry.get("草种类型"),
            "斑秃面积": record.get("复壮面积"),
            "剩余斑秃面积": self.pending_bald_area(int(record["lawn_id"])),
            "复壮面积": record.get("复壮面积"),
            "班次": record.get("班次"),
            "登记时间": record.get("登记时间"),
            "验收时间": record.get("验收时间"),
            "accepted": record.get("accepted", False),
            "duplicated": duplicated,
        }

    # ---- 班次汇总与看板 -------------------------------------------------

    def shift_summary(self) -> list[dict[str, Any]]:
        """班次汇总的斑秃合计直接由复壮明细逐行累加，保证合计与明细一致。"""
        result = []
        for shift in SHIFTS:
            details = self.list_rejuvenations(shift)
            bald_total = sum(float(row["复壮面积"]) for row in details)
            bald_total = int(bald_total) if float(bald_total).is_integer() else round(bald_total, 2)
            result.append({
                "班次": shift,
                "复壮笔数": len(details),
                "斑秃合计": bald_total,
                "待验收笔数": sum(1 for row in details if not row["accepted"]),
            })
        return result

    def dashboard(self) -> dict[str, Any]:
        """养护看板：斑秃面积随复壮明细实时重算，刷新结果稳定（纯函数口径）。"""
        all_rows = store.rows(MODULE)
        decorated = [self._decorate(row) for row in all_rows]
        pending_total = sum(float(row["斑秃面积"]) for row in decorated)
        status_count = {status: 0 for status in STATUS_ORDER}
        for row in all_rows:
            status_count[str(row.get("status"))] = status_count.get(str(row.get("status")), 0) + 1
        pending_total = int(pending_total) if float(pending_total).is_integer() else round(pending_total, 2)
        return {
            "斑秃面积合计": pending_total,
            "斑秃草坪数": sum(1 for row in decorated if float(row["斑秃面积"]) > 0),
            "状态分布": status_count,
            "班次汇总": self.shift_summary(),
        }

    # ---- 兼容旧的动作入口 ----------------------------------------------

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"草坪 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于草坪管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._decorate(entry), f"草坪已{action}"
