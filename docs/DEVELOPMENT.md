# PostStudio 0.4 开发接续

2026-09-20：最终本地测试包已重新构建、安装并严格校验本地签名，重开新格式项目和退出成功。62 项回归通过。新模块包括 effects、history、trash、metadata、resources、watermark、border、workflow 及对应控件。`scripts/benchmark_effects.py` 记录小图／24MP／48MP 计算开销；`scripts/validate_v04.py` 记录本轮原生事件到绘制、42 输入场景。后续记录见 [EXECUTION_STATUS](EXECUTION_STATUS.md)。

以下包含运行环境与历史接口说明；0.4 验收证据和边界见 ACCEPTANCE_0_4.md。

# 开发与交接

当前源码与本机构建版本为 PostStudio 0.4.1。2026-09-18 的[执行前最终方案](NEXT_ACTION_PLAN.md)已获批准并实现；上轮计划见[已完成归档](PLAN_0_3_COMPLETED.md)。

## 运行

需要 Python 3.12 或以上；当前验证环境为 Apple Silicon、Python 3.14。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m blockstudio.app
```

本机环境已安装，也可以双击根目录的 `启动工作台.command`。首次安装依赖需要联网，应用运行不使用网络。

## 测试与构建

```sh
.venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m scripts.benchmark
./scripts/build-mac.sh
```

PyInstaller 生成 `dist/PostStudio.app`。构建是 arm64 本机构建，没有 Apple Developer 公证。构建脚本使用 Command Line Tools，不需要修改全局 Xcode 配置。

## 模块

| 文件 | 职责 |
| --- | --- |
| `blockstudio/imaging.py` | 读取、颜色转换、直通 alpha、2×2 降采样、16 位存储和导出 |
| `blockstudio/tools.py` | 工具注册、默认参数和执行函数 |
| `blockstudio/project.py` | 独立资产、输入关系、JSON 清单、原子项目保存、恢复、作品框合成 |
| `blockstudio/canvas.py` | 图像摆放、移动缩放、选区、作品框、视图平移缩放 |
| `blockstudio/widgets.py` | 工具参数、预览、导入导出选项、工作流编辑 |
| `blockstudio/app.py` | 画布与二级工具页面、固定输入会话、后台队列与操作连接 |
| `blockstudio/editor.py` | 原始分辨率预览线程、单输入缓存、请求合并与过期结果丢弃 |
| `blockstudio/qt_runtime.py` | 对带隐藏文件标志的 macOS 工作目录进行 Qt 插件发现兼容处理 |

## 新增工具

1. 在 `tools.py` 注册稳定 ID、名称、参数版本、默认参数和纯处理函数。
2. 处理函数接收 sRGB、uint16、H×W×4、直通 alpha 的数组，不得修改输入数组。返回相同约定的新数组。
3. 参数必须可以写入 JSON。0.3.1 将连续交互预览、静止精细预览和正式计算分开；取样几何始终使用工作图像坐标，不能在缩略图上随意生成不同的整数网格。组合与配色接口见下文。
4. 在 `widgets.py` 增加参数控件；不要将正式图像处理放进界面代码。
5. 补充像素正确性和旧产物不变的验证。未知工具或不兼容参数版本应报错，不可静默替换。

当前仅内置工具注册，不自动执行项目携带的 Python 代码，也不将外部插件安装作为打开项目的前提。后续扩展工具需要定义兼容和分发方案。

## 项目格式 v1

ZIP 容器使用 ZIP_STORED，因为中间 TIFF 已压缩。`manifest.json` 包含：

- `assets`：独立 ID、相对文件路径、宽高、缩略图、parent 输入、root 源图、工具 step、可选 original。
- `boards`：图像摆放引用、x/y、显示宽度、视图模式、作品框。
- `presets`、`workflows`：名称与工具参数或步骤数组。

文件只从 `assets/` 的直接文件名读取，不接受越界路径。保存时只包含被清单引用的文件，通过同目录临时文件和原子替换发布。

版本关系只用于追溯和重新执行，没有自动依赖传播。布局与版本切换属于画布状态，不改变任何资产像素。

## 后续工作

本轮按 [批准方案](NEXT_ACTION_PLAN.md)完成了：状态／引用与兼容 → 删除、取色取消和撤销 → 配色／取样布局、渐变与阴影 → 预设直接执行和资料 → 边框、水印 → 单条节点工作流 → 综合交付。上轮预览优化与 Oklab 配色已经完成，不再列为待开发。

本轮接口约束：区分图像工具与命名／导出动作；工具参数、资源和流程运行使用快照；新增资料来源、可用照片／边框区域、回收站和完整引用检查；保持现有像素契约与不可变产物。节点 UI 仅支持单链。明确区分两项外框比例功能。项目 schema 及参数版本按实际字段升级，旧项目在内存迁移，新格式不得伪装为 v2；工程验收清单见方案 A01～A12。

上述接口已经接入。schema 3 读取旧 v1/v2；新字段和动作节点不能由旧应用重编辑。验收证据见 ACCEPTANCE_0_4.md。

GitHub 尚未创建或发布；项目许可证由作者选择。分发前需要整理 Qt/PySide6 等第三方许可证与依赖声明，不应把本地测试包直接视为正式发布包。

## 0.2 编辑会话与兼容

- 进入二级工具页面时冻结 `editor_selection` 和 `editor_inputs`，画布重新选择或刷新不能改变会话输入。
- `resolve_input` 区分修改同工具步骤与显式追加。旧版没有 `intent` 的连续同工具链会回溯到链前输入；新记录通过 `intent` 保留执行意图。
- `moved_blocks` 是取样参数：键为网格列、行索引字符串，值为 `[dx, dy]`。先移除被移动块的原窗口，再合并新窗口，重叠处取并集。
- 分块取样参数版本为 2，兼容旧版版本 1；旧应用不能重新执行版本 2，但项目仍包含完整独立产物。
- 预览线程只缓存一个完整输入；参数请求保留最新项，主线程还会检查 generation，避免旧结果回写。
- 关闭工具或提交处理会停止预览线程并释放完整输入，然后开始正式处理队列。

本机 Documents 工作目录含文件提供器元数据，可能使本地应用签名失败；测试包复制到 `~/Applications` 后仅清理生成应用上的 FinderInfo/ResourceFork，再做 ad-hoc 签名。不要改动用户项目、源图或其他应用的扩展属性。

## 0.3 配色与预览接口

- `palette.py`：与 Qt 无关的 Oklab 提色；样本上限 32768，按空间分层和 alpha 加权，分析及结果缓存有数量上限。矩阵来自 Oklab 作者的公有领域参考实现。特色模式保留一个非微量、色彩差异明显的候选组；这不是语义识别。
- `palette_render.py`：排版、RGBA16 色条与色卡环绘制、直通 alpha 合成；提取结果与排版分离。
- `palette_widgets.py`：提色/排版页签、锁色与拖动顺序、手动取色。
- `editor.py`：24 ms 合并节流，220 ms 静止精细预览。快速网格用原图坐标积分覆盖率；精细取样分带可让新请求打断。结果按会话边界及单调请求序号呈现。关闭工具异步退出线程，关闭应用等线程退出后清理项目。
- `PreviewWorker` 接收路径或 `(project, asset_id)`；组合的延迟合成必须在后台解析，不能从主线程调用 `project.file()` 合成大图。源像素只读，可用于精确取色。

格式 v2 新增 `kind=palette/composition`、`palette` 分析快照及 `composition` 组件位置。组合 `file=null`，保留缩略图并引用完整源图和色卡组件；`Project.file` 按需生成 `cache/` 下的完整 TIFF。缓存不进入项目包；读取 v1/v2，拒绝其他版本及循环依赖、非法组件范围。普通像素工具仍返回独立 RGBA16 资产。

验证命令：

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m scripts.benchmark_interaction --fast --output artifacts/interaction-optimized.json
.venv/bin/python -m scripts.validate_release
```

最后一个脚本需要 `artifacts/fixtures/Fronalpstock_big.jpg`（来源与许可见同目录 ATTRIBUTION.md），打开原生 Qt 窗口；只使用公开测试图，42 张压力场景重复该图，不代表 42 张不同真实作品。测试照片和演示项目不打入应用包。

安装包复制必须保留符号链接，例如 Python `shutil.copytree(..., symlinks=True)`。普通复制若把 Frameworks 中符号链接展开成目录，会导致 codesign 将资源目录误判为框架而失败。仅对新生成的应用清理 FinderInfo/ResourceFork，然后使用 CLT 完成本地 ad-hoc 签名与校验。

## 0.4 验证与文档再生成

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m scripts.benchmark_effects
.venv/bin/python -m scripts.validate_v04
.venv/bin/python -m scripts.capture_manual
.venv/bin/python scripts/build_user_manual.py
```

`validate_v04` 使用原生 Cocoa；等待后台 Python 工作线程时使用 processEvents 配合短 time.sleep 释放 GIL，不用紧循环 QTest.qWait。它记录事件调度到 Qt 绘制完成，不能当作物理屏幕延迟。`capture_manual` 使用同一公开素材在临时项目捕获当前界面，不读私人照片。

增强取样在拖动时使用 560 px 独立缓存，背景按参数变化失效；普通交互仍为 960 px。所有窗口几何按完整源坐标积分，静止精细渲染和正式生成使用完整源像素。完整渲染的条带检查可在新请求到达后让位；不能把交互缩略图作为正式输入。

## 0.4.1 末端保存约定

`revision_blocker` 检查所有资产（含回收站）的处理和组合依赖。`revise_leaf` 从原 parent 重执行同一工具，再以原 ID 替换记录；像素写入新文件，旧文件保留供会话历史使用。组合缓存按 ID + content_revision 哈希区分。保存前等待旧预览停止，防止旧任务与组件替换竞争。边框参数版本升为 2，继续接受旧参数；项目 schema 仍为 3。

## Git 仓库与本地资料

代码仓库：https://github.com/Eason-young-Zhang/PostStudio 。保留原有 main 分支及 MIT 许可证。根目录 README 面向首次使用者，原始需求与四象限保存在 PROJECT_CONTEXT.md。

`.venv/`、`artifacts/`、`build/`、`dist/`、`*.spec` 和 `*.blockproj` 被忽略。私人项目留在原位置；旧安装包和构建目录已在本机移至项目目录之外的开发归档，未上传。重新构建会自动生成新的 build、dist 和 spec 文件。

运行性能脚本前建立 `artifacts/`。截图和原生大图验证另需从 THIRD_PARTY_NOTICES.md 的来源页面取得 Fronalpstock big.jpg，保存为 `artifacts/fixtures/Fronalpstock_big.jpg`；仓库不包含原始素材。普通 pytest 回归使用生成的测试图像，不需要此素材。

```sh
mkdir -p artifacts/fixtures
PYTHONPATH=. .venv/bin/python scripts/capture_manual.py
.venv/bin/python scripts/build_user_manual.py
```

提交前检查 `git diff --cached`，不要使用强制推送覆盖远端已有历史。

## 0.4.2 数值控件

`number_control.NumberControl` 组合 QDoubleSpinBox 与 QSlider；`effect_controls.number` 为共享入口。存储值来自输入框；阻塞外层信号时仍同步滑条，避免加载和联动残留。滑条范围单独配置，不缩小输入框的合法范围。新增参数需设置可访问名称，并为像素／百分比切换指定常用范围。
