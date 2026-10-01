"""内窥检测业务规则：状态流转、等级口径版本化、管段分组报告与待复核清单。

等级口径说明：
- 检测报告在「确认出具」时按当时生效的口径定级，并把口径版本与等级一起锁定留档；
  此后口径再调整，已出具的结论仍按当时那一版展示。
- 还没出结论的检测（待检测、检测中、已退回）不锁定等级，每次读取都按当前口径重算。
- 已退回重检的报告是一份被推翻的结论：不计入管段的最近结论，但要落到待复核清单。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "cctv"
PIPE_MODULE = "pipe"
REQUIRED_FIELDS = ["检测编号", "检测管段", "检测设备"]
OPTIONAL_FIELDS = ["检测长度", "检测人员", "检测日期", "缺陷指数"]
STATUS_ORDER = ["待检测", "检测中", "已出具", "已退回"]
ACTION_RULES = {"安排检测": "检测中", "确认出具": "已出具", "退回重检": "已退回"}
NEGATIVE_ACTIONS = []

# 等级判定口径：按缺陷指数从高到低取第一个命中的阈值。
# 2026 版收紧了三级/四级门槛——这就是“口径调整”，未出结论的检测会按它重算。
GRADING_VERSIONS: dict[str, list[tuple[int, str]]] = {
    "2025版": [(80, "四级"), (60, "三级"), (40, "二级"), (0, "一级")],
    "2026版": [(75, "四级"), (55, "三级"), (35, "二级"), (0, "一级")],
}
CURRENT_VERSION = "2026版"

GRADE_ORDER = {"一级": 1, "二级": 2, "三级": 3, "四级": 4}


class CctvService:
    """检测报告的查询、流转与口径计算都集中在这一个服务里，保证各页面计数同源。"""

    def __init__(self) -> None:
        self.current_version = CURRENT_VERSION

    # ---------- 等级口径 ----------

    def grading_overview(self) -> dict[str, Any]:
        """口径配置：当前生效版本 + 各版本阈值，供页面展示判定口径。"""
        return {
            "current": self.current_version,
            "versions": [
                {"version": version, "thresholds": thresholds}
                for version, thresholds in GRADING_VERSIONS.items()
            ],
        }

    def switch_version(self, version: str) -> tuple[dict[str, Any] | None, str]:
        """调整判定口径：只切换当前版本；已出具的报告保持原版本留档，未出具的随读取重算。"""
        if version not in GRADING_VERSIONS:
            return None, f"口径版本「{version}」不存在，可选：{'、'.join(GRADING_VERSIONS)}"
        if version == self.current_version:
            return self.grading_overview(), f"当前生效口径已是{version}"
        self.current_version = version
        return self.grading_overview(), f"判定口径已切换为{version}，未出结论的检测已按新口径重算等级"

    def _grade_for(self, score: Any, version: str) -> str:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return "未定级"
        thresholds = GRADING_VERSIONS.get(version, GRADING_VERSIONS[CURRENT_VERSION])
        for threshold, grade in thresholds:
            if value >= threshold:
                return grade
        return "未定级"

    def _effective_grade(self, row: dict[str, Any]) -> tuple[str, str | None, bool]:
        """返回（有效缺陷等级、判定口径版本、是否已锁定留档）。

        已出具的报告用出具时锁定的等级与版本；其余状态按当前口径实时重算。
        """
        if row.get("status") == "已出具" and row.get("缺陷等级"):
            return str(row["缺陷等级"]), row.get("口径版本") or self.current_version, True
        if row.get("status") == "已退回":
            return "已退回", None, False
        return self._grade_for(row.get("缺陷指数"), self.current_version), self.current_version, False

    # ---------- 序列化 ----------

    def _serialize(self, row: dict[str, Any]) -> dict[str, Any]:
        """把仓库行整理成接口行：检测状态取真实流转状态，等级按口径规则给出。"""
        grade, version, locked = self._effective_grade(row)
        item = dict(row)
        item["检测状态"] = row.get("status")
        item["缺陷等级"] = grade
        item["判定口径"] = version
        item["等级已锁定"] = locked
        return item

    # ---------- 平铺列表（与原页面一致的入口） ----------

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
        page_rows = [self._serialize(row) for row in rows[start:start + size]]
        return page_rows, total

    def count_entries(self) -> int:
        """检测报告总条数：运营概览与检测列表共用这一个口径。"""
        return len(store.rows(MODULE))

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._serialize(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if values.get(field) not in (None, ""):
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._serialize(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于内窥检测可执行范围"
        target = ACTION_RULES[action]

        if action == "确认出具":
            if entry.get("status") == "已退回":
                return None, "该报告已退回重检，原结论不再出具，请基于重检数据重新登记"
            if entry.get("status") == "已出具":
                return None, "该报告已出具结论，如需更改请先退回重检"
            # 出具时按当前口径定级并锁定版本留档
            entry["缺陷等级"] = self._grade_for(entry.get("缺陷指数"), self.current_version)
            entry["口径版本"] = self.current_version
            entry["status"] = target
            entry["pending"] = False
            entry["abnormal"] = False
        elif action == "退回重检":
            if entry.get("status") != "已出具":
                return None, "只有已出具结论的报告才能退回重检"
            # 退回即推翻原结论：清除锁定等级，后续按新口径重算，并落入待复核清单
            entry["status"] = target
            entry["pending"] = True
            entry["abnormal"] = True
            entry.pop("缺陷等级", None)
            entry.pop("口径版本", None)
        else:  # 安排检测
            if entry.get("status") not in ("待检测", "已退回"):
                return None, "报告已在检测流程中，无需重复安排"
            entry["status"] = target
            entry["pending"] = True
            entry["abnormal"] = False
        return self._serialize(entry), f"检测报告已{action}"

    # ---------- 待复核清单（退回重检） ----------

    def review_list(self) -> tuple[list[dict[str, Any]], int]:
        """退回重检的报告全部落到这里，条数随退回/重检动作实时重算。"""
        rows = [row for row in store.rows(MODULE) if row.get("status") == "已退回"]
        rows.sort(key=lambda row: (str(row.get("检测日期") or ""), int(row.get("id", 0))), reverse=True)
        return [self._serialize(row) for row in rows], len(rows)

    # ---------- 管段分组检测报告 ----------

    @staticmethod
    def _all_pipe_segments() -> list[str]:
        """管段全集以管段档案为准，并补上检测里出现但档案缺失的编号，保证不漏组。"""
        names = [str(row.get("管段编号", "")).strip() for row in store.rows(PIPE_MODULE)]
        names = [name for name in names if name]
        for row in store.rows(MODULE):
            name = str(row.get("检测管段", "")).strip()
            if name and name not in names:
                names.append(name)
        return sorted(set(names))

    def grouped_report(self) -> dict[str, Any]:
        """按管段分组的检测报告：最近一次结论、历次对比、上升标记与汇总数量。"""
        rows = sorted(
            store.rows(MODULE),
            key=lambda row: (str(row.get("检测日期") or ""), int(row.get("id", 0))),
        )
        history_by_segment: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            segment = str(row.get("检测管段", "")).strip()
            history_by_segment.setdefault(segment, []).append(self._serialize(row))

        groups: list[dict[str, Any]] = []
        raised_count = 0
        inspected_segments = 0
        pending_conclusion = 0

        for segment in self._all_pipe_segments():
            history = history_by_segment.get(segment, [])
            # 最近结论只认已出具报告：退回重检的原结论已被推翻，不计入。
            conclusions = [item for item in history if item.get("status") == "已出具"]
            latest = conclusions[-1] if conclusions else None
            previous = conclusions[-2] if len(conclusions) >= 2 else None

            raised = False
            if latest is not None and previous is not None:
                latest_rank = GRADE_ORDER.get(str(latest.get("缺陷等级")), 0)
                previous_rank = GRADE_ORDER.get(str(previous.get("缺陷等级")), 0)
                raised = latest_rank > previous_rank
            if raised:
                raised_count += 1

            review_items = [item for item in history if item.get("status") == "已退回"]
            in_progress = [item for item in history if item.get("status") in ("待检测", "检测中")]
            if history:
                inspected_segments += 1
            pending_conclusion += len(in_progress) + len(review_items)

            groups.append({
                "管段编号": segment,
                "检测次数": len(history),
                "尚未检测": not history,
                "最近结论": None if latest is None else {
                    "检测编号": latest.get("检测编号"),
                    "检测日期": latest.get("检测日期"),
                    "缺陷等级": latest.get("缺陷等级"),
                    "检测长度": latest.get("检测长度"),
                    "检测设备": latest.get("检测设备"),
                    "检测人员": latest.get("检测人员"),
                    "判定口径": latest.get("判定口径"),
                },
                "上次结论": None if previous is None else {
                    "检测编号": previous.get("检测编号"),
                    "检测日期": previous.get("检测日期"),
                    "缺陷等级": previous.get("缺陷等级"),
                },
                "等级上升": raised,
                "进行中数量": len(in_progress),
                "待复核数量": len(review_items),
                "最新检测日期": history[-1].get("检测日期") if history else None,
                "历史检测": history,
            })

        # 稳定排序：先让最新检测日期近的靠前，再按“等级上升优先、已检测优先”重排，
        # 最终顺序为：等级上升管段 → 其余已检测管段 → 尚未检测管段。
        groups.sort(key=lambda group: str(group["最新检测日期"] or ""), reverse=True)
        groups.sort(key=lambda group: (1 if group["尚未检测"] else 0, 0 if group["等级上升"] else 1))

        _, review_total = self.review_list()
        summary = {
            "管段总数": len(groups),
            "已检测管段": inspected_segments,
            "尚未检测管段": len(groups) - inspected_segments,
            "等级上升管段": raised_count,
            "检测报告总数": self.count_entries(),
            "待出具检测": pending_conclusion,
            "待复核条数": review_total,
            "判定口径": self.current_version,
        }
        return {"summary": summary, "groups": groups, "grading": self.grading_overview()}
