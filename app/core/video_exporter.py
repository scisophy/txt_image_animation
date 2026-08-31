"""阶段 3b：调用固定版本的本地 HyperFrames CLI 校验并渲染 final.mp4。"""
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

RENDER_TIMEOUT = 1800  # 1080p/30fps 逐帧渲染约 2-5 分钟，留足余量
CHECK_TIMEOUT = 300
PROJECT_ROOT = Path(__file__).resolve().parents[2]
HYPERFRAMES_CLI = PROJECT_ROOT / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"


class RenderError(RuntimeError):
    pass


def _node() -> str:
    found = shutil.which("node")
    if found:
        return found
    raise RenderError("找不到 node：请确认 Node.js 22+ 已安装并在 PATH 中")


def _command(args: list[str]) -> list[str]:
    if not HYPERFRAMES_CLI.is_file():
        raise RenderError("找不到本地 HyperFrames CLI：请先在项目根目录运行 npm install")
    return [_node(), str(HYPERFRAMES_CLI), *args]


def _creation_flags() -> int:
    # 不使用 DETACHED_PROCESS：它会让控制台子系统的 chrome-headless-shell 弹出黑窗。
    # Python 层仅隐藏 Node CLI 控制台；Puppeteer 层仍由 windowsHide: true 隐藏浏览器窗口。
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NO_WINDOW


def _run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    cmd = _command(args)
    logger.info("执行：%s（cwd=%s）", " ".join(cmd), cwd)
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
        )
    except FileNotFoundError as exc:
        raise RenderError("无法启动本地 HyperFrames CLI") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"HyperFrames 命令超时（{timeout}s）：{' '.join(args)}") from exc


def lint_composition(workspace: Path) -> None:
    """lint 失败（错误级）则中止，避免渲染出不可预期的结果。"""
    proc = _run(["lint"], workspace, CHECK_TIMEOUT)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RenderError(f"HyperFrames lint 未通过：\n{output[-4000:]}")
    logger.info("lint 通过")


def check_composition(workspace: Path) -> str:
    """运行完整浏览器检查；错误级发现项阻断渲染。"""
    proc = _run(["check"], workspace, CHECK_TIMEOUT)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RenderError(f"HyperFrames check 未通过：\n{output[-4000:]}")
    else:
        logger.info("check 通过")
    return output


def render_video(workspace: Path, output_name: str = "final.mp4", fps: int = 30) -> Path:
    out_path = workspace / output_name
    if out_path.exists():
        out_path.unlink()
    proc = _run(
        ["render", "--output", output_name, "--fps", str(fps)],
        workspace,
        RENDER_TIMEOUT,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or not out_path.exists():
        raise RenderError(f"HyperFrames 渲染失败：\n{output[-4000:]}")
    logger.info("渲染完成：%s", out_path)
    return out_path


def export_video(workspace: Path, fps: int = 30) -> Path:
    """渲染前运行包含 lint 的完整 check，最后输出 final.mp4。"""
    check_composition(workspace)
    return render_video(workspace, fps=fps)
