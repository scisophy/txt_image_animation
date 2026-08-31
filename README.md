# AI 信息图遮罩动画生成器

将一段文字自动转换为 16:9 信息图，并按照讲解顺序逐步揭示信息图中的内容区域，最终渲染为 1080p MP4 视频。

项目始终使用同一张完整信息图。尚未讲解的区域会被主背景色遮住；进入对应讲解点时，遮罩按顺序收起，已经揭示的内容保持可见。

## 工作流程

```text
用户原文
  ↓
GPT 提炼 3～6 个讲解点
  ↓
gpt-image-2 生成完整 16:9 信息图
  ↓
视觉模型定位每个讲解点的归一化 bbox
  ↓
统计整张图片中占比最高的背景颜色簇
  ↓
在完整信息图上生成顺序遮罩
  ↓
HyperFrames + GSAP 生成可定位动画时间线
  ↓
渲染 1920×1080 MP4
```

遮罩颜色不是写死的。程序会缩小图片作为统计样本，将相近 RGB 像素聚类，并取像素数量最多的颜色簇均值作为遮罩色。这样可以容忍轻微渐变和图片噪声。

## 功能

- 自动理解原文并生成结构化信息图内容方案
- 自动生成 2048×1152 高质量信息图
- 使用视觉模型定位每个讲解点的完整视觉区域
- 自动统计信息图主背景色
- 未讲区域遮罩，讲解区域按顺序累计揭示
- 浏览器中预览遮罩颜色和揭示顺序
- 支持重新生成整图、重新识别区域和重新渲染
- SSE 实时展示任务进度
- 任务状态和中间产物持久化，支持断点续跑
- HyperFrames 渲染前自动执行完整检查

## 环境要求

- Python 3.10 或更高版本
- Node.js 22 或更高版本
- `npm`
- FFmpeg，并已加入 `PATH`
- 可用的 OpenAI API Key

可以先检查本机环境：

```powershell
python --version
node --version
npm --version
ffmpeg -version
```

## 安装

以下命令以 Windows PowerShell 为例。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm install --no-audit --no-fund
Copy-Item .env.example .env
```

编辑 `.env`，至少填写：

```dotenv
OPENAI_API_KEY=sk-你的_API_Key
```

不要提交或分享包含真实 API Key 的 `.env` 文件。

## 启动

```powershell
python run.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

使用步骤：

1. 输入需要转换的信息或讲解文本。
2. 根据需要调整开场、单个讲解点、揭示转场和结尾时长。
3. 点击“开始生成”。
4. 在预览页点击讲解步骤，检查遮罩颜色和累计揭示顺序。
5. 如果区域或整图不合适，可以重新生成整图或重新识别区域。
6. 点击“生成视频”，等待 HyperFrames 检查并渲染 MP4。

## 配置

配置通过 `.env` 读取。可用变量如下：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 无 | 必填，OpenAI API Key |
| `PLANNER_MODEL` | `gpt-5.6-sol` | 内容规划和视觉区域检测模型 |
| `IMAGE_MODEL` | `gpt-image-2` | 信息图生成模型 |
| `IMAGE_SIZE` | `2048x1152` | 信息图尺寸 |
| `IMAGE_QUALITY` | `high` | 图片生成质量 |
| `INTRO_DURATION` | `2` | 开场时长，秒 |
| `POINT_DURATION` | `4` | 每个讲解点时长，秒 |
| `TRANSITION_DURATION` | `0.8` | 遮罩揭示时长，秒 |
| `OUTRO_DURATION` | `2` | 结尾整图时长，秒 |
| `SERVER_HOST` | `127.0.0.1` | 服务监听地址 |
| `SERVER_PORT` | `8000` | 服务端口 |

网页中填写的动画参数会覆盖对应任务的默认时长。

如果有 `N` 个讲解点，视频总时长为：

```text
开场时长 + N × 单个讲解点时长 + 结尾时长
```

遮罩揭示动画发生在每个讲解点的开始位置，并包含在该讲解点时长内。

## 任务产物

每个任务保存在 `output/<任务 ID>/`：

```text
output/<task-id>/
├── meta.json          # 任务状态、原文、内容方案、动画参数
├── infographic.png    # 完整信息图
├── regions.json       # 视觉模型返回的讲解区域
├── mask.json          # 遮罩色、RGB 和顺序区域规格
├── gsap.min.js        # 本地 GSAP 运行时
├── index.html         # HyperFrames composition
└── final.mp4          # 最终视频，渲染后出现
```

`mask.json` 示例：

```json
{
  "color": "#f8fafd",
  "rgb": [248, 250, 253],
  "regions": [
    {
      "id": 1,
      "title": "什么是冲突？",
      "bbox": {
        "x1": 0.026,
        "y1": 0.233,
        "x2": 0.204,
        "y2": 0.835
      }
    }
  ]
}
```

bbox 使用 `0～1` 归一化坐标，原点位于信息图左上角。

## 动画实现

生成的 `index.html` 是一个独立 HyperFrames composition：

- 全片只有一个持续存在的完整信息图图层
- 所有讲解区域初始覆盖主背景色遮罩
- 每个遮罩使用 GSAP `scaleX: 1 → 0` 实现从左向右揭示
- 已经收起的遮罩不会重新出现，因此内容会累计展示
- 所有动画都写入一个 `paused` GSAP timeline，由 HyperFrames 按时间定位
- 总时长由 composition 根节点的 `data-duration` 控制

这种实现可以在动画过程中持续保留完整信息图的画面结构。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/tasks` | 创建任务并生成到遮罩预览阶段 |
| `GET` | `/api/tasks` | 获取任务列表 |
| `GET` | `/api/tasks/{task_id}` | 获取任务详情 |
| `GET` | `/api/tasks/{task_id}/events` | 订阅 SSE 进度事件 |
| `POST` | `/api/tasks/{task_id}/render` | 检查并渲染视频 |
| `POST` | `/api/tasks/{task_id}/redo` | 从指定阶段重新执行 |
| `GET` | `/api/tasks/{task_id}/files/{path}` | 访问任务中间产物 |
| `GET` | `/api/download/{task_id}` | 下载最终 MP4 |

创建任务示例：

```powershell
$body = @{
  text = "Git 冲突是什么，怎么解决"
  intro_duration = 2
  point_duration = 4
  transition_duration = 0.8
  outro_duration = 2
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/tasks `
  -ContentType application/json `
  -Body $body
```

可重跑的阶段为：

```text
plan → image → regions → mask → storyboard → render
```

从某个阶段重跑时，该阶段之后的产物会失效并重新生成。

## 项目结构

```text
app/
├── api/
│   ├── routes.py             # HTTP API 与文件下载
│   └── schemas.py            # 请求模型
├── core/
│   ├── config.py             # 环境变量和默认参数
│   ├── content_planner.py    # 内容规划与图片提示词
│   ├── image_generator.py    # 完整信息图生成
│   ├── region_detector.py    # 视觉区域识别
│   ├── mask_builder.py       # 主背景色统计与遮罩规格
│   ├── storyboard_html.py    # HyperFrames HTML 与 GSAP 时间线
│   └── video_exporter.py     # HyperFrames 检查和视频渲染
├── static/                   # 网页界面
└── tasks/pipeline.py         # 串行任务流水线与持久化

scripts/
├── patch-puppeteer-windows.mjs # Windows 下禁止浏览器脱离父进程
└── smoke_render.py             # 不调用 OpenAI 的真实渲染冒烟测试
tests/                        # 单元测试
package.json                  # 固定 HyperFrames CLI 版本与安装补丁
run.py                       # Uvicorn 启动入口
```

## 测试

运行单元测试：

```powershell
python -m pytest -q
```

检查前端 JavaScript 语法：

```powershell
node --check app\static\app.js
```

运行完整 HyperFrames 冒烟测试：

```powershell
python scripts\smoke_render.py
```

冒烟脚本会在系统临时目录中生成合成信息图、执行 HyperFrames lint/check，并真实渲染一个 MP4，不会调用 OpenAI API。

## 常见问题

### 提示缺少 `OPENAI_API_KEY`

确认已经把 `.env.example` 复制为 `.env`，并填写真实 Key。修改后需要重启服务。

### 提示找不到本地 HyperFrames CLI

安装 Node.js 22 或更高版本，并在项目根目录运行 `npm install --no-audit --no-fund`。项目固定使用 `hyperframes@0.8.20`，安装后会自动保留 Puppeteer 的 `windowsHide: true`，并将 Windows 浏览器进程设为 `detached: false`。

### HyperFrames 渲染失败

确认 Node.js、Chrome/Chromium 和 FFmpeg 可用。可以进入任务目录手动检查：

```powershell
cd output\<task-id>
node ..\..\node_modules\hyperframes\bin\hyperframes.mjs check
```

项目会在渲染前执行完整 `check`。只要存在错误级 lint、运行时、布局或对比度问题，就不会继续输出可能有缺陷的视频。

### 遮罩颜色看起来不合适

先查看任务目录中的 `mask.json`。遮罩色来自整张图的最大颜色簇；如果生成图没有占比明显的统一背景，可以重新生成整图。

### 讲解区域遮住不完整或遮到其他内容

点击“重新识别区域”。区域由视觉模型根据讲解点标题定位，bbox 会尽量包含标题、正文、图标和背景容器。

### 为什么多个任务不会同时生成？

流水线使用单工作线程串行执行，避免多个图片生成任务互相挤占 API 限流额度。
