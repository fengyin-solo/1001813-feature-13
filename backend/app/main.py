"""城市地下管网巡检养护平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.routers.cctv import service as cctv_service
from app.store import store

app = FastAPI(title="城市地下管网巡检养护平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。

    内窥检测的条数直接取检测服务的统一计数，保证运营概览与检测列表始终一致。
    """
    data = store.overview()
    for item in data["modules"]:
        if item["name"] == "cctv":
            item["created"] = cctv_service.count_entries()
    for card in data["cards"]:
        if card["label"] == "今日新增":
            card["value"] = sum(int(item["created"]) for item in data["modules"])
    return data
