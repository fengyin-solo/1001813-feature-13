"""内窥检测接口：平铺检测列表、按管段分组的检测报告、待复核清单与判定口径。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cctv import CctvService

router = APIRouter(prefix="/api/cctv", tags=["内窥检测"])

service = CctvService()

LIST_FIELDS = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
STATUSES = ["待检测", "检测中", "已出具", "已退回"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按检测编号检索"),
    status: str | None = Query(default=None, description="待检测、检测中、已出具、已退回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按检测编号与状态过滤内窥检测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/grouped")
def grouped_report() -> dict[str, Any]:
    """按管段分组的检测报告：最近结论、历次对比、上升标记与汇总数量随数据实时计算。"""
    return service.grouped_report()


@router.get("/review")
def review_list() -> dict[str, Any]:
    """待复核清单：仅列出已退回重检的报告，条数与退回动作同步。"""
    items, total = service.review_list()
    return {"items": items, "total": total}


@router.get("/grading")
def grading_overview() -> dict[str, Any]:
    """读取缺陷等级判定口径：当前生效版本与各版本阈值。"""
    return service.grading_overview()


@router.post("/grading/actions")
def switch_grading(payload: EntryPayload) -> ActionResult:
    """切换判定口径版本：未出结论的检测按新口径重算，已出具的按原版本留档。"""
    version = str(payload.values.get("version") or "").strip()
    overview, message = service.switch_version(version)
    if overview is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=overview)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测报告明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测报告 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测报告，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="检测报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测报告执行安排检测、确认出具、退回重检；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出内窥检测清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "cctv", "total": total, "items": items}
