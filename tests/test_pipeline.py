from pathlib import Path

from app.tasks import pipeline


def test_redo_removes_downstream_artifacts(tmp_path, monkeypatch):
    store = pipeline.TaskStore(tmp_path)
    monkeypatch.setattr(pipeline, "store", store)
    monkeypatch.setattr(pipeline, "start_task", lambda *a, **k: None)

    meta = store.create("测试文本", {})
    task_id = meta["id"]
    ws = store.dir(task_id)
    (ws / "infographic.png").write_bytes(b"png")
    (ws / "regions.json").write_text("[]")
    (ws / "mask.json").write_text("{}")
    (ws / "index.html").write_text("<html></html>")
    (ws / "final.mp4").write_bytes(b"mp4")

    pipeline.redo(task_id, "regions")

    assert not (ws / "regions.json").exists()
    assert not (ws / "mask.json").exists()
    assert not (ws / "index.html").exists()
    assert not (ws / "final.mp4").exists()
    # 上游产物保留
    assert (ws / "infographic.png").exists()
    assert store.load(task_id)["status"] == "pending"
