"""内窥检测业务规则：管段分组报告、等级判定口径版本、结论留档与退回重检。

几条核心口径都收在这个文件里，路由层不做业务判断：

- 「最近一次结论」只认状态为已出具的报告；已退回重检的报告不计入结论，
  但仍保留在管段历次检测时间线里，并进入待复核清单。
- 等级判定存在版本口径。确认出具时把当时的口径版本与判定等级冻结到报告上，
  此后口径调整也按当时版本留档展示；还没出结论的报告没有冻结字段，
  一律按当前启用的口径实时重算。
- 页面上所有数量（汇总卡片、待复核条数、管段分组）都在同一份行数据上现算，
  因此运营概览、检测列表、管段报告看到的条数天然一致。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "cctv"
PIPE_MODULE = "pipe"
REQUIRED_FIELDS = ["检测编号", "检测管段", "检测设备"]
OPTIONAL_FIELDS = ["检测长度", "检测人员", "检测日期", "缺陷指数"]
STATUS_ORDER = ["待检测", "检测中", "已出具", "已退回"]
PENDING_STATUSES = {"待检测", "检测中"}
ACTION_RULES = {"安排检测": "检测中", "确认出具": "已出具", "退回重检": "已退回"}

CONCLUDED_STATUS = "已出具"
RETURNED_STATUS = "已退回"

# 等级判定口径：阈值按升序排列，分别是 一/二级、二/三级、三/四级 的缺陷指数分界。
# 新口径（2026 版）整体下调阈值，同一指数可能判出更高等级。
GRADE_VERSIONS: list[dict[str, Any]] = [
    {"id": "v2023", "name": "2023版判定口径", "thresholds": [10, 30, 50]},
    {"id": "v2026", "name": "2026版判定口径", "thresholds": [5, 20, 40]},
]
DEFAULT_VERSION = "v2023"
GRADE_LABELS = {1: "一级", 2: "二级", 3: "三级", 4: "四级"}


def grade_level(score: float, thresholds: list[int]) -> int:
    """按阈值把缺陷指数映射成 1-4 级，指数越高缺陷越重。"""
    if score < thresholds[0]:
        return 1
    if score < thresholds[1]:
        return 2
    if score < thresholds[2]:
        return 3
    return 4


class CctvService:
    def __init__(self) -> None:
        # 现行口径只保存在进程内；切换后所有未出结论的报告立即按新口径重算。
        self.active_version = DEFAULT_VERSION

    # ---- 口径版本 ----
    def grade_versions(self) -> dict[str, Any]:
        return {"active": self.active_version, "versions": GRADE_VERSIONS}

    def activate_version(self, version_id: str) -> dict[str, Any] | None:
        if not any(version["id"] == version_id for version in GRADE_VERSIONS):
            return None
        self.active_version = version_id
        return self.grade_versions()

    def _version(self, version_id: str) -> dict[str, Any]:
        return next(version for version in GRADE_VERSIONS if version["id"] == version_id)

    def _current_grade(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """未出结论（含已退回）的报告按现行口径实时判定；没有指数的还判不了。"""
        score = entry.get("缺陷指数")
        if score is None or str(score).strip() == "":
            return None
        version = self._version(self.active_version)
        level = grade_level(float(score), version["thresholds"])
        return {
            "等级数值": level,
            "缺陷等级": GRADE_LABELS[level],
            "口径版本": version["id"],
            "口径名称": version["name"],
            "留档": False,
        }

    def resolve_grade(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """报告对外展示的等级：已出具读冻结留档，其余按现行口径现算。"""
        if entry.get("status") == CONCLUDED_STATUS and entry.get("判定等级"):
            return {
                "等级数值": entry.get("判定等级数值"),
                "缺陷等级": entry["判定等级"],
                "口径版本": entry.get("等级口径版本"),
                "口径名称": entry.get("等级口径名称"),
                "留档": True,
            }
        return self._current_grade(entry)

    # ---- 列表与明细 ----
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
            rows = [row for row in rows if keyword in str(row.get("检测编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._describe(row) for row in rows[start:start + size]]
        return page_rows, total

    def _describe(self, entry: dict[str, Any]) -> dict[str, Any]:
        """给行数据补上当前可展示的缺陷等级，不改写已留档的判定字段。"""
        view = dict(entry)
        grade = self.resolve_grade(entry)
        view["缺陷等级"] = grade["缺陷等级"] if grade else view.get("缺陷等级") or "待判定"
        view["等级留档"] = bool(grade and grade["留档"])
        return view

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        view = self._describe(entry)
        grade = self.resolve_grade(entry)
        if grade:
            view["当前等级"] = grade["缺陷等级"]
            view["当前等级数值"] = grade["等级数值"]
            view["判定口径名称"] = grade["口径名称"]
            view["等级待重算"] = not grade["留档"] and entry.get("缺陷指数") is not None
        return view

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = self._coerce(field, value)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    @staticmethod
    def _coerce(field: str, value: Any) -> Any:
        if field == "检测长度":
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if field == "缺陷指数":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于内窥检测可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if target == CONCLUDED_STATUS:
            message = self._freeze_conclusion(entry)
            if message:
                return None, message
        entry["status"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = target == RETURNED_STATUS
        return entry, f"检测报告已{action}"

    def _freeze_conclusion(self, entry: dict[str, Any]) -> str | None:
        """确认出具：把现行口径下的判定结果冻结到报告上，后续口径调整不再影响它。"""
        score = entry.get("缺陷指数")
        if score is None or str(score).strip() == "":
            return "报告缺少缺陷指数，无法按口径判定等级，请补录后再出具"
        version = self._version(self.active_version)
        level = grade_level(float(score), version["thresholds"])
        entry["判定等级数值"] = level
        entry["判定等级"] = GRADE_LABELS[level]
        entry["等级口径版本"] = version["id"]
        entry["等级口径名称"] = version["name"]
        entry["结论时间"] = date.today().isoformat()
        return None

    # ---- 管段分组报告 ----
    def all_segments(self) -> list[str]:
        """管段范围 = 管段档案里的管段 ∪ 检测报告里出现过的管段，保证未检测段也能提示。"""
        segments: list[str] = []
        for row in store.rows(PIPE_MODULE):
            name = str(row.get("管段编号") or "").strip()
            if name and name not in segments:
                segments.append(name)
        for row in store.rows(MODULE):
            name = str(row.get("检测管段") or "").strip()
            if name and name not in segments:
                segments.append(name)
        return segments

    @staticmethod
    def _entry_date(entry: dict[str, Any]) -> str:
        return str(entry.get("检测日期") or "")

    def _history_item(self, entry: dict[str, Any]) -> dict[str, Any]:
        grade = self.resolve_grade(entry)
        return {
            "id": entry["id"],
            "检测编号": entry.get("检测编号"),
            "检测日期": entry.get("检测日期"),
            "检测设备": entry.get("检测设备"),
            "检测长度": entry.get("检测长度"),
            "检测人员": entry.get("检测人员"),
            "缺陷指数": entry.get("缺陷指数"),
            "状态": entry.get("status"),
            "有效结论": entry.get("status") == CONCLUDED_STATUS,
            "已退回": entry.get("status") == RETURNED_STATUS,
            "等级留档": bool(grade and grade["留档"]),
            "等级数值": grade["等级数值"] if grade else None,
            "缺陷等级": grade["缺陷等级"] if grade else "待判定",
            "口径名称": grade["口径名称"] if grade else None,
            "结论时间": entry.get("结论时间"),
        }

    def segment_report(self) -> dict[str, Any]:
        rows = sorted(store.rows(MODULE), key=self._entry_date)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("检测管段") or ""), []).append(row)

        segments: list[dict[str, Any]] = []
        for name in self.all_segments():
            history_rows = grouped.get(name, [])
            history = [self._history_item(row) for row in history_rows]
            conclusions = [item for item in history if item["有效结论"]]
            latest = conclusions[-1] if conclusions else None
            previous = conclusions[-2] if len(conclusions) >= 2 else None
            rising = (
                latest is not None
                and previous is not None
                and int(latest["等级数值"]) > int(previous["等级数值"])
            )
            if latest is None:
                state = "uninspected" if not history else "no_conclusion"
            else:
                state = "concluded"
            segments.append({
                "管段": name,
                "状态": state,
                "latest": latest,
                "prevLevel": previous["等级数值"] if previous else None,
                "等级上升": rising,
                "检测次数": len(history),
                "history": history,
            })

        inspected = sum(1 for item in segments if item["状态"] == "concluded")
        return {"total": len(segments), "inspected": inspected, "segments": segments}

    # ---- 待复核清单 ----
    def review_queue(self) -> tuple[list[dict[str, Any]], int]:
        rows = [
            self._describe(row)
            for row in store.rows(MODULE)
            if row.get("status") == RETURNED_STATUS
        ]
        rows.sort(key=self._entry_date, reverse=True)
        return rows, len(rows)

    # ---- 汇总：所有页头数量都从这里取 ----
    def summary(self) -> dict[str, Any]:
        rows = store.rows(MODULE)
        status_counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status_counts[str(row.get("status"))] = status_counts.get(str(row.get("status")), 0) + 1

        report = self.segment_report()
        level4_segments = sum(
            1 for segment in report["segments"]
            if segment["latest"] and int(segment["latest"]["等级数值"]) == 4
        )
        rising_segments = sum(1 for segment in report["segments"] if segment["等级上升"])
        recalculating = sum(
            1 for row in rows
            if row.get("status") != CONCLUDED_STATUS
            and row.get("status") != RETURNED_STATUS
            and row.get("缺陷指数") is not None
        )
        month_prefix = date.today().strftime("%Y-%m")
        month_length = sum(
            float(row.get("检测长度") or 0)
            for row in rows
            if self._entry_date(row).startswith(month_prefix)
        )
        return {
            "total": len(rows),
            "statusCounts": status_counts,
            "pendingReview": status_counts.get(RETURNED_STATUS, 0),
            "segmentTotal": report["total"],
            "inspectedSegments": report["inspected"],
            "level4Segments": level4_segments,
            "risingSegments": rising_segments,
            "recalculating": recalculating,
            "monthLength": month_length,
            "activeVersion": self.grade_versions()["active"],
            "activeVersionName": self._version(self.active_version)["name"],
        }
