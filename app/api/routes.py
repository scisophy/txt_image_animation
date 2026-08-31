"""HTTP API：任务创建、SSE 进度、文件访问与下载。"""
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.api.schemas import CreateTaskRequest, RedoRequest
from app.tasks import pipeline

router = APIRouter(prefix="/api")


@router.post("/tasks")
def create_task(req: CreateTaskRequest):
    params = {
        "intro_duration": req.intro_duration,
        "outro_duration": req.outro_duration,
        "point_duration": req.point_duration,
        "transition_duration": req.transition_duration,
    }
    meta = pipeline.store.create(req.text.strip(), params)
    pipeline.start_task(meta["id"], target="storyboard")
    return meta


@router.get("/tasks")
def list_tasks():
    return pipeline.store.list()


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    meta = pipeline.store.load(task_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return meta


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str):
    """SSE：推送阶段事件直到任务进入终态。"""
    if pipeline.store.load(task_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def generate():
        cursor = 0
        while True:
            events = pipeline.bus.snapshot(task_id)
            while cursor < len(events):
                payload = json.dumps(events[cursor], ensure_ascii=False)
                yield f"data: {payload}\n\n"
                cursor += 1
            meta = pipeline.store.load(task_id)
            terminal = meta["status"] in ("completed", "failed", "awaiting_render")
            if terminal and cursor >= len(events):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/tasks/{task_id}/render")
def render_task(task_id: str):
    meta = pipeline.store.load(task_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if meta["status"] in ("running", "rendering"):
        raise HTTPException(status_code=409, detail="任务正在执行中")
    pipeline.start_task(task_id, target="render")
    return {"task_id": task_id, "status": "rendering"}


@router.post("/tasks/{task_id}/redo")
def redo_task(task_id: str, req: RedoRequest):
    try:
        target = pipeline.redo(task_id, req.stage)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "target": target}


@router.get("/tasks/{task_id}/files/{file_path:path}")
def task_file(task_id: str, file_path: str):
    workspace = pipeline.store.dir(task_id).resolve()
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    target = (workspace / file_path).resolve()
    if workspace not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)


@router.get("/download/{task_id}")
def download_video(task_id: str):
    meta = pipeline.store.load(task_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    video = pipeline.store.dir(task_id) / "final.mp4"
    if not video.exists():
        raise HTTPException(status_code=404, detail="视频尚未生成")
    return FileResponse(
        video, media_type="video/mp4", filename=f"infographic_video_{task_id}.mp4"
    )
