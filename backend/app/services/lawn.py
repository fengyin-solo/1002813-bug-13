"""草坪管理业务规则：斑秃登记、复壮登记、验收与统计口径都收在这里。

口径约定（列表、详情、汇总、看板共用同一份算法，保证同一个数）：
- 草坪表上的「斑秃面积」是登记时的斑秃基数；复壮明细记录每次复壮恢复的面积。
- 对外展示与参与汇总的「斑秃面积」= 斑秃基数 − 该草坪已登记的复壮面积合计，
  即「复壮前还没处理完的斑秃」，任何地方都由 _view 现算，不存副本。
- 一片草坪第一次复壮登记生效后，再次提交一律拒绝，只认第一次。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "lawn"
REJUVENATION_MODULE = "lawn_rejuvenation"

# 列表/详情共用的字段集合，保证两处读到的草种、斑秃面积等完全一致。
LIST_FIELDS = ["草坪编号", "草种类型", "草坪面积", "修剪频率", "灌溉方式", "返青情况", "斑秃面积", "草坪状态"]
EDITABLE_FIELDS = ["草种类型", "草坪面积", "修剪频率", "灌溉方式", "返青情况", "斑秃面积"]
REQUIRED_FIELDS = ["草坪编号", "草种类型", "草坪面积"]
NUMERIC_FIELDS = ["草坪面积", "斑秃面积"]

STATUS_ORDER = ["良好", "斑秃", "退化", "已复壮"]
# 动作只允许在指定状态下执行：既卡住非法流转，也卡住重复提交。
ACTION_PRECONDITIONS = {
    "登记斑秃": ({"良好"}, "斑秃"),
    "复壮作业": ({"斑秃"}, "退化"),
    "验收复壮": ({"退化"}, "已复壮"),
}
DEFAULT_SHIFTS = ["白班", "夜班"]


class LawnError(ValueError):
    """业务校验失败：消息需要原样带给前端，不许替换成通用提示。"""


def _round2(value: float) -> float:
    return round(value + 0.0, 2)


def parse_area(value: Any, field: str) -> float:
    """把面积入参解析成非负数字；空串、文字、负数都给出可读原因。"""
    if value is None or str(value).strip() == "":
        raise LawnError(f"{field}不能为空，请填写数字")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LawnError(f"{field}必须是数字，收到的是「{value}」")
    if number != number or number in (float("inf"), float("-inf")):
        raise LawnError(f"{field}必须是有效数字")
    if number < 0:
        raise LawnError(f"{field}不能为负数（收到 {number}）")
    return _round2(number)


class LawnService:
    # ---------- 基础读取 ----------
    def _rejuvenation_rows(self) -> list[dict[str, Any]]:
        return store.rows(REJUVENATION_MODULE)

    def _details_for(self, lawn_id: int) -> list[dict[str, Any]]:
        return [row for row in self._rejuvenation_rows() if int(row.get("lawn_id", 0)) == lawn_id]

    def _restored_area(self, lawn_id: int) -> float:
        return _round2(sum(float(row.get("复壮面积", 0) or 0) for row in self._details_for(lawn_id)))

    def remaining_bare_area(self, entry: dict[str, Any]) -> float:
        """待复壮斑秃面积 = 斑秃基数 − 已复壮合计，小于 0 按 0 计。"""
        base = float(entry.get("斑秃面积", 0) or 0)
        return max(_round2(base - self._restored_area(int(entry.get("id", 0)))), 0.0)

    def _view(self, entry: dict[str, Any]) -> dict[str, Any]:
        """统一出口：列表、详情、汇总都经过它，字段口径永远一致。"""
        view = {field: entry.get(field) for field in LIST_FIELDS if field != "草坪状态"}
        view["id"] = int(entry.get("id", 0))
        view["草坪状态"] = entry.get("status")
        restored = self._restored_area(view["id"])
        view["累计复壮面积"] = restored
        view["斑秃面积"] = self.remaining_bare_area(entry)
        return view

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = sorted(store.rows(MODULE), key=lambda row: int(row.get("id", 0)))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("草坪编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._view(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        view = self._view(entry)
        view["复壮明细"] = [dict(row) for row in sorted(self._details_for(entry_id), key=lambda r: int(r.get("id", 0)))]
        return view

    # ---------- 登记 / 修改 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in EDITABLE_FIELDS:
            entry[field] = values.get(field)
        entry["草坪编号"] = values["草坪编号"]
        entry["斑秃面积"] = parse_area(values.get("斑秃面积", 0) if str(values.get("斑秃面积", "")).strip() != "" else 0, "斑秃面积")
        entry["草坪面积"] = parse_area(values["草坪面积"], "草坪面积")
        if entry["草坪面积"] <= 0:
            raise LawnError("草坪面积必须大于 0")
        self._validate_areas(entry["斑秃面积"], entry["草坪面积"], restored=0.0)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._view(entry), []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> dict[str, Any]:
        """修改草坪资料。斑秃面积超过草坪面积、小于已复壮面积都不许保存并写明原因。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            raise LawnError(f"草坪 {entry_id} 不存在或已归档")

        merged = {field: entry.get(field) for field in EDITABLE_FIELDS}
        merged.update({field: values[field] for field in EDITABLE_FIELDS if field in values})

        lawn_area = parse_area(merged["草坪面积"], "草坪面积")
        bare_area = parse_area(merged["斑秃面积"], "斑秃面积")
        restored = self._restored_area(entry_id)
        self._validate_areas(bare_area, lawn_area, restored)

        entry["草种类型"] = merged["草种类型"]
        entry["草坪面积"] = lawn_area
        entry["斑秃面积"] = bare_area
        for field in ("修剪频率", "灌溉方式", "返青情况"):
            if field in merged:
                entry[field] = merged[field]
        return self._view(entry)

    @staticmethod
    def _validate_areas(bare_area: float, lawn_area: float, restored: float) -> None:
        if bare_area > lawn_area:
            raise LawnError(
                f"斑秃面积（{bare_area}㎡）超过草坪面积（{lawn_area}㎡），不许保存："
                f"斑秃面积必须小于等于草坪面积"
            )
        if restored > bare_area:
            raise LawnError(
                f"斑秃面积（{bare_area}㎡）小于已复壮面积合计（{restored}㎡），不许保存："
                f"已复壮的斑秃不能被改没"
            )

    # ---------- 动作流转 ----------
    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            raise LawnError(f"草坪 {entry_id} 不存在或已归档")
        if action not in ACTION_PRECONDITIONS:
            raise LawnError(f"动作「{action}」不属于草坪管理可执行范围")

        allowed_status, target = ACTION_PRECONDITIONS[action]
        current = entry.get("status")
        if current not in allowed_status:
            if action == "复壮作业" and self._details_for(entry_id):
                raise LawnError("该草坪已登记复壮，请勿重复提交，只认第一次登记")
            raise LawnError(f"草坪当前状态为「{current}」，不能执行「{action}」（仅 {('、'.join(allowed_status))} 状态可执行）")

        if action == "登记斑秃":
            bare_area = entry.get("斑秃面积", 0) or 0
            if values and values.get("斑秃面积") not in (None, ""):
                bare_area = parse_area(values["斑秃面积"], "斑秃面积")
                lawn_area = parse_area(entry.get("草坪面积", 0) or 0, "草坪面积")
                self._validate_areas(bare_area, lawn_area, restored=0.0)
                entry["斑秃面积"] = bare_area
            if float(bare_area or 0) <= 0:
                raise LawnError("斑秃面积为 0，无法登记斑秃：请先填写斑秃面积再登记")
            if values and str(values.get("返青情况") or "").strip():
                entry["返青情况"] = values["返青情况"]
        elif action == "复壮作业":
            self._register_rejuvenation(entry, values or {})
        elif action == "验收复壮":
            entry["pending"] = False

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = target == "斑秃"
        messages = {
            "登记斑秃": "斑秃已登记",
            "复壮作业": f"复壮已登记，该草坪剩余待复壮斑秃面积 {self.remaining_bare_area(entry)}㎡",
            "验收复壮": "复壮已验收，草坪状态更新为已复壮",
        }
        return self._view(entry), messages[action]

    def _register_rejuvenation(self, entry: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        # 复壮作业只认第一次：已有明细就拒绝（run_action 的状态前置条件之外再兜一层）。
        if self._details_for(int(entry["id"])):
            raise LawnError("该草坪已登记复壮，请勿重复提交，只认第一次登记")
        remaining = self.remaining_bare_area(entry)
        if remaining <= 0:
            raise LawnError("该草坪没有待复壮的斑秃面积，无法登记复壮")
        shift = str(values.get("班次") or "白班").strip() or "白班"
        rows = self._rejuvenation_rows()
        detail = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "lawn_id": int(entry["id"]),
            "草坪编号": entry.get("草坪编号"),
            "草种类型": entry.get("草种类型"),
            "复壮面积": remaining,
            "班次": shift,
            "登记人": str(values.get("登记人") or "").strip(),
            "登记时间": str(values.get("登记时间") or "").strip(),
        }
        rows.append(detail)
        return detail

    # ---------- 统计 ----------
    def _bare_entries(self) -> list[dict[str, Any]]:
        """复壮前还没处理完的斑秃：状态为斑秃且仍有待复壮面积。"""
        return [
            row
            for row in sorted(store.rows(MODULE), key=lambda r: int(r.get("id", 0)))
            if row.get("status") == "斑秃" and self.remaining_bare_area(row) > 0
        ]

    def board(self) -> dict[str, Any]:
        """养护看板：斑秃面积随复壮明细实时重算，不缓存旧数。"""
        rows = sorted(store.rows(MODULE), key=lambda r: int(r.get("id", 0)))
        bare_entries = self._bare_entries()
        bare_total = _round2(sum(self.remaining_bare_area(row) for row in bare_entries))
        restored_total = _round2(sum(float(row.get("复壮面积", 0) or 0) for row in self._rejuvenation_rows()))
        return {
            "斑秃合计面积": bare_total,
            "斑秃草坪数": len(bare_entries),
            "累计复壮面积": restored_total,
            "各状态数量": {status: sum(1 for row in rows if row.get("status") == status) for status in STATUS_ORDER},
            "斑秃明细": [
                {"草坪编号": row.get("草坪编号"), "草种类型": row.get("草种类型"), "斑秃面积": self.remaining_bare_area(row)}
                for row in bare_entries
            ],
        }

    def shift_summary(self, shift: str | None = None) -> dict[str, Any]:
        """班次汇总：合计与明细同源同算，按 id 固定顺序，刷多少次都一样。"""
        details = sorted(self._rejuvenation_rows(), key=lambda row: int(row.get("id", 0)))
        if shift:
            details = [row for row in details if str(row.get("班次") or "") == shift]

        shifts: dict[str, dict[str, Any]] = {}
        for row in details:
            bucket = shifts.setdefault(row.get("班次") or "未填班次", {"班次": row.get("班次") or "未填班次", "复壮条数": 0, "复壮面积合计": 0.0})
            bucket["复壮条数"] += 1
            bucket["复壮面积合计"] = _round2(bucket["复壮面积合计"] + float(row.get("复壮面积", 0) or 0))
        shift_rows = sorted(shifts.values(), key=lambda item: item["班次"])
        rejuvenated_total = _round2(sum(float(row.get("复壮面积", 0) or 0) for row in details))

        board = self.board()
        detail_items = [
            {
                "id": int(row.get("id", 0)),
                "lawn_id": int(row.get("lawn_id", 0)),
                "草坪编号": row.get("草坪编号"),
                "草种类型": row.get("草种类型"),
                "复壮面积": _round2(float(row.get("复壮面积", 0) or 0)),
                "班次": row.get("班次"),
                "登记时间": row.get("登记时间"),
            }
            for row in details
        ]
        return {
            "斑秃合计": board["斑秃合计面积"],
            "斑秃草坪数": board["斑秃草坪数"],
            "复壮面积合计": rejuvenated_total,
            "明细复壮面积之和": rejuvenated_total,  # 与明细同源，供前端/测试对账
            "班次汇总": shift_rows,
            "复壮明细": detail_items,
        }
