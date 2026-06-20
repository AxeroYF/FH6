# FH6Auto 2.2

FH6Auto 是一个基于 Python、图像识别和输入自动化的 FH6 自动化工具，支持循环跑图、批量买车、超级抽奖、技能路径配置、模块串联、运行统计、暂停/停止，以及可选的 AI 辅助选车。

> 本项目仅用于 Python 自动化、图像识别与本地脚本技术交流学习。请勿用于商业用途、破坏游戏平衡或违反相关服务条款。因使用本工具造成的任何后果，包括但不限于账号异常、封禁、数据损失等，均由使用者自行承担。

## 项目来源

本项目来自 [YOUSTHEONE/FH6Auto](https://github.com/YOUSTHEONE/FH6Auto)。当前 2.2 版本是在原项目基础上，针对现有游戏版本进行的本地维护、适配和功能优化。

## 版本更新记录

### V2.2

- 重写主界面 UI，保持黑色主题，优化整体布局、字体、卡片比例和运行信息展示。
- 新增日志面板折叠 / 展开功能，折叠后释放下方日志区域占用空间。
- 优化超级抽奖区域布局，将技能方向按钮、清除按钮和 4x4 技能矩阵放回超级抽奖模块内。
- 新增 `AI自动截图` 开关，默认关闭；开启后才会保存 AI/严格选车识别截图作为训练数据。
- 调整 AI 辅助逻辑，`AI辅助` 只负责启用 YOLO 兜底识别，不再默认保存训练截图。
- 新增蓝图失效识别模板与处理流程，识别到失效蓝图后会返回漫游界面并中断流程。
- 优化作者评价界面处理，兼容 `likeauthor` / `dislikeauthor` 偶发弹窗。
- 拆分 `main.py` 中的基础功能，将 UI、资源路径、图片匹配逻辑拆到独立模块，方便后续维护。
- 修复拆分后的图片子目录引用问题，保留 `images/obstacles` 等模板目录结构。

### V2.1

主要更新：

- 适配当前游戏版本的 UI 流程与图像识别状态。
- 重构主界面布局，移除独立信息监视窗口，运行状态、暂停/停止和统计信息整合到主 UI。
- 删除“支持作者”入口。
- 优化超级抽奖选车逻辑，按“全新标签 + B600 等级 + 目标车辆卡片”进行多段验证。
- 修复超级抽奖结束后切回刷图车的流程，支持自动寻找带收藏标签的刷图车并上车。
- 修复车辆菜单焦点偏移导致误进“车房宝物”等问题。
- 新增可选 `AI辅助`，在模板识别失败时使用 YOLO 模型兜底选车。
- 可选开启 `AI自动截图` 保存识别样本，便于后续继续训练和适配。

## Release 下载版本

建议在 GitHub Release 中提供两个压缩包：

```text
FH6Auto-2.2-Standard.zip
FH6Auto-2.2-AI.zip
```

### 普通版：FH6Auto-2.2-Standard.zip

适合大多数用户直接使用。

- 不包含 AI 推理依赖，体积较小。
- 解压后运行 `FH6Auto.exe`。
- 不需要用户安装 Python。
- 超级抽奖使用普通模板识别逻辑。
- 不建议开启 `AI辅助`；如果误开但缺少 AI 依赖，程序会回退到普通识别并在日志中提示。

### AI 版：FH6Auto-2.2-AI.zip

适合需要更强选车兜底识别的用户。

- 包含预训练模型：`models/fh6_car_select_yolo.pt`。
- 主程序仍优先使用普通模板识别，只有模板识别失败且用户开启 `AI辅助` 时才调用 YOLO。
- 解压后运行 `FH6Auto.exe`，在主界面超级抽奖区域打开 `AI辅助`。
- AI 模型主要基于 1080p 截图训练，对非 1080p 可能比纯模板更宽容，但不保证适配所有分辨率。

## 使用前准备

### 游戏环境

- Windows 系统。
- 游戏语言：简体中文。
- 输入法：英文键盘。
- 推荐分辨率：1920x1080。
- 建议关闭 HDR、滤镜或明显改变画面颜色的后处理。
- 运行脚本时保持游戏在前台，避免频繁切换窗口。

### 刷图车辆

请准备用于循环跑图的车辆：

- 斯巴鲁 Impreza 22B-STi Version。
- 调校到 S2 900。
- 加入收藏。
- 保持默认涂装。

超级抽奖结束后，如果下一步设置为循环跑图，程序会尝试在“我的车辆”中切换回这辆带收藏标签的刷图车。

## 功能模块

### 循环跑图

- 自动进入菜单和 EventLab。
- 自动输入蓝图分享代码。
- 自动匹配目标车辆与赛事。
- 支持按设定次数重复执行。
- 支持超时检测和异常恢复。

### 批量买车

- 自动进入车辆收藏。
- 自动定位目标品牌和目标车辆。
- 自动重复购买指定数量车辆。

### 超级抽奖

- 自动进入“我的车辆”。
- 自动筛选目标消耗车辆。
- 自动进入升级与调校、车辆专精。
- 按用户配置的技能路径点技能。
- 技能点耗尽或车辆已处理时自动结束。
- 选车时依次验证：

```text
全新标签 -> B600 等级 -> 目标车辆卡片
```

### 模块串联

可以将多个模块串联为流水线：

```text
循环跑图 -> 批量买车 -> 超级抽奖 -> 下一轮循环
```

每个模块完成后是否继续到下一模块、总循环次数，都可以在主界面配置。

## AI 辅助

主界面超级抽奖区域有 `AI辅助` 开关。

开启后：

- 普通模板识别仍然优先执行。
- 模板识别失败时，才调用 YOLO 模型兜底。
- AI 会同时判断 `new_tag`、`class_b600`、`target_car` 三类目标。
- 如果同时开启 `AI自动截图`，识别过程会保存样本到：

```text
debug/car_select_ai/raw
debug/car_select_ai/pass
debug/car_select_ai/miss
```

这些样本可用于后续复盘、标注和继续训练。

如果没有开启 `AI自动截图`，程序不会主动留存训练截图。

AI 模型默认查找路径：

```text
models/fh6_car_select_yolo.pt
runs/detect/fh6_car_select/yolo11n_all_boxes_v2/weights/best.pt
runs/detect/fh6_car_select/yolo11n_all_boxes/weights/best.pt
runs/detect/runs/fh6_car_select/yolo11n_draft/weights/best.pt
```

普通用户建议只使用 Release AI 版随包提供的：

```text
models/fh6_car_select_yolo.pt
```

更多训练、验证和数据集说明请看 [README-AI.md](README-AI.md)。

## 从源码运行

源码运行不会自动安装依赖，需要手动安装。

### 普通版源码运行

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

### AI 辅助源码运行

```powershell
python -m pip install -r requirements-ai.txt
```

然后准备模型文件：

```text
models/fh6_car_select_yolo.pt
```

检查 AI 环境：

```powershell
python -c "import ultralytics, torch; print(ultralytics.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

AI 可以使用 CPU，但速度会慢一些。推荐 NVIDIA 显卡用户安装匹配 CUDA 的 PyTorch。

## 主界面参数

主界面可以配置：

- 跑图次数。
- 买车次数。
- 超级抽奖次数。
- 蓝图分享代码。
- 大循环次数。
- 单局超时时间。
- 模块完成后是否继续。
- 技能路径。
- AI 辅助开关。
- AI 自动截图开关。

主界面运行监控会显示：

- 运行状态。
- 当前任务。
- 当前任务进度。
- 大循环进度。
- 本任务耗时。
- 总运行时间。
- 跑图 / 买车 / 超抽累计耗时。
- 暂停 / 停止控制。

## 快捷键

- `F8`：停止当前任务并释放按键。
- `F9`：暂停 / 继续当前任务。
- `F3`：测试找图流程。

停止任务时，程序会尝试释放方向键、确认键、返回键、空格、持续按住的 `W` 等输入，避免异常退出后卡键。

## 图片模板

项目使用 `images` 目录中的模板图进行识别。程序会优先读取外部 `images` 目录，方便用户自行替换模板以适配不同分辨率、画质和游戏 UI 状态。

常见模板包括：

- `skillcar.png`：刷图技能点车辆。
- `liketag.png`：收藏标签。
- `CCbrand.png`：消耗品车辆品牌。
- `consumablecar.png`：用于点技能的消耗品车辆。
- `newcartag.png`：黄色“全新”标签。
- `classB600.png`：`B 600` 等级标签。
- `newCC.png`：目标车辆卡片。

如果识别失败，优先考虑重新截图替换对应模板。

## 配置文件

用户配置保存在项目根目录的 `config.json`。程序启动时会自动补全缺失字段，并兼容迁移旧版配置。

重要配置包括：

- `race_count`
- `buy_count`
- `cj_count`
- `share_code`
- `global_loops`
- `skill_dirs`
- `auto_restart`
- `restart_cmd`
- `race_timeout`
- `ai_assist`
- `ai_auto_capture`
- `ai_model_path`

## 打包说明

普通版打包需要：

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

AI 版打包还需要：

```powershell
python -m pip install -r requirements-ai.txt
```

AI 版需要准备模型：

```text
models/fh6_car_select_yolo.pt
```

模型文件不建议提交到源码仓库，建议放入 GitHub Release 的 AI 压缩包中。

## 技术栈

- `customtkinter`：桌面 UI。
- `opencv-python`：模板匹配与图像识别。
- `numpy`：图像数组处理。
- `pyautogui`：截图与基础自动化。
- `pydirectinput`：游戏场景输入模拟。
- `pynput`：全局热键监听。
- `Pillow`：图像加载与处理。
- `pywin32` / `ctypes`：窗口聚焦、API 适配与底层输入。
- `ultralytics` / `torch`：可选 AI 辅助选车。

## 致谢

感谢原项目 [YOUSTHEONE/FH6Auto](https://github.com/YOUSTHEONE/FH6Auto) 提供的基础实现与思路。
