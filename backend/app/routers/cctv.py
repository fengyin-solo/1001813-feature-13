"""内窥检测接口：检测报告、管段分组报告、待复核清单与等级判定口径。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cctv import CctvService

router = APIRouter(prefix="/api/cctv", tags=["内窥检测"])

service = CctvService()

LIST_FIELDS = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
STATUSES = ["待检测", "检测中", "已出具", "已退回"]


@router.get("/summary")
def summary() -> dict[str, Any]:
    """内窥检测页头汇总：与列表、分组报告共用同一份行数据现算，条数始终一致。"""
    return service.summary()


@router.get("/segments")
def segment_report() -> dict[str, Any]:
    """按检测管段分组的检测报告：最近结论、历次检测对比、等级上升标记。"""
    return service.segment_report()


@router.get("/review-queue", response_model=PageResult[dict])
def review_queue() -> PageResult[dict]:
    """待复核清单：只收退回重检的报告，条数随重算实时变化。"""
    items, total = service.review_queue()
    return PageResult(items=items, total=total, page=1, size=max(total, 1))


@router.get("/grade-versions")
def grade_versions() -> dict[str, Any]:
    """等级判定口径版本列表与当前启用版本。"""
    return service.grade_versions()


@router.post("/grade-versions/activate", response_model=ActionResult)
def activate_grade_version(payload: EntryPayload) -> ActionResult:
    """切换判定口径：已出具的报告留档不变，未出结论的报告随后按新口径重算。"""
    version_id = str(payload.values.get("version") or "").strip()
    result = service.activate_version(version_id)
    if result is None:
        return ActionResult(ok=False, message=f"判定口径「{version_id}」不存在")
    result = service.grade_versions()
    version_name = next(version["name"] for version in result["versions"] if version["id"] == result["active"])
    return ActionResult(ok=True, message=f"已切换为{version_name}，未出结论的报告已按新口径重算")


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
