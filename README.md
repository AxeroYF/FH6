# FH6Auto 3.0

FH6Auto 是一个基于 Python、图像识别和输入自动化的 FH6 自动化工具，支持循环跑图、批量买车、超级抽奖、技能路径配置、模块串联、运行统计、暂停/停止，以及可选的 AI 辅助选车。

> 本项目仅用于 Python 自动化、图像识别与本地脚本技术交流学习。请勿用于商业用途、破坏游戏平衡或违反相关服务条款。因使用本工具造成的任何后果，包括但不限于账号异常、封禁、数据损失等，均由使用者自行承担。

## 项目来源

本项目来自 [YOUSTHEONE/FH6Auto](https://github.com/YOUSTHEONE/FH6Auto)。当前 V3.0 版本是在原项目基础上，针对现有游戏版本进行的本地维护、适配和功能优化。

## V3.0 更新重点

- 优化超级抽奖循环：点完技能树返回车辆菜单后，通过 `designpaint` 进入设计与涂装流程，再进入 `choosecar` 选择下一辆全新车辆，减少反复从外层菜单进入车辆列表的不稳定性。
- 适配设计编辑器提示弹窗：点击 `designpaint` 后会先尝试识别 `choosecar`，如果没有出现才按一次 `Enter` 确认提示，兼容已勾选“不再显示该消息”的用户。
- 新增 `designpaint-w.png` / `designpaint-b.png` 识别模板，用于进入设计与涂装入口。
- 保留并复用原有严格选车逻辑：`全新标签 -> B600 等级 -> 目标车辆卡片` 多段验证。
- 新增 `AI优先` 开关。开启 `AI辅助 + AI优先` 后，超级抽奖选车会优先使用 YOLO 模型识别，再使用模板检测兜底。
- 标准逻辑保持不变：只开启 `AI辅助` 时仍然是模板优先，模板失败后再调用 AI 兜底。
- 保留 `AI自动截图`，便于保存 pass/miss 样本继续训练和排查。
- 继续支持超级抽奖结束后切回带收藏标签的刷图车。

## Release 下载版本

建议在 GitHub Release 中提供两个压缩包：

```text
FH6Auto-3.0-Standard.zip
FH6Auto-3.0-AI.zip
```

### 标准版：FH6Auto-3.0-Standard.zip

适合大多数用户直接使用。

- 不包含 AI 推理依赖，体积较小。
- 解压后运行 `FH6Auto.exe`。
- 不需要用户安装 Python。
- 超级抽奖默认使用普通模板识别逻辑。
- 不建议开启 `AI辅助`；如果误开但缺少 AI 依赖，程序会回退到普通识别并在日志中提示。

### AI 版：FH6Auto-3.0-AI.zip

适合需要更强选车适配能力的用户，尤其是分辨率、UI 缩放或画面表现与 1080p 标准环境不同的情况。

- 包含预训练模型：`models/fh6_car_select_yolo.pt`。
- 打开 `AI辅助`：模板识别失败后使用 YOLO 兜底。
- 同时打开 `AI辅助` 和 `AI优先`：优先使用 YOLO 识别，失败后使用模板兜底。
- AI 模型主要基于 1080p 截图训练，对非 1080p 通常比纯模板更宽容，但不保证适配所有分辨率、HDR、滤镜或画质设置。

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

- 自动进入车辆与收藏、购买与出售页面。
- 通过 `designpaint` / `choosecar` 进入可复用选车界面。
- 自动筛选全新目标消耗车辆。
- 自动上车并进入升级与调校、车辆专精。
- 按用户配置的技能路径点技能。
- 点完技能后返回车辆菜单，继续下一轮 `designpaint -> choosecar -> 选车 -> 点技能` 循环。
- 技能点耗尽或车辆已处理时自动结束。

选车时依次验证：

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

主界面超级抽奖区域有三个相关开关：

- `AI辅助`：启用 YOLO 模型参与选车。
- `AI优先`：只在 `AI辅助` 开启时生效；开启后优先使用 AI，再用模板兜底。
- `AI自动截图`：保存 AI/严格模板识别过程中的样本图，便于复盘和训练。

识别顺序：

```text
默认标准逻辑：
严格模板识别 -> AI 兜底

AI 优先逻辑：
AI 模型识别 -> 严格模板兜底
```

AI 会同时判断 `new_tag`、`class_b600`、`target_car` 三类目标。更多训练、验证和数据集说明请看 [README-AI.md](README-AI.md)。

## 从源码运行

源码运行不会自动安装依赖，需要手动安装。

### 标准环境

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

### AI 环境

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
- `AI辅助` 开关。
- `AI优先` 开关。
- `AI自动截图` 开关。

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

- `designpaint-w.png` / `designpaint-b.png`：设计与涂装入口。
- `choosecar.png` / `choosecar-b.png`：选择车辆入口。
- `CCbrand.png`：消耗车辆品牌。
- `consumablecar.png`：用于点技能的消耗品车辆。
- `newcartag.png`：黄色“全新”标签。
- `classB600.png`：`B 600` 等级标签。
- `newCC.png`：目标车辆卡片。
- `UandT-w.png` / `UandT-b.png`：升级与调校。
- `clsldcnw.png` / `clsldcnb.png`：车辆专精。
- `skillcar.png`：刷图技能点车辆。
- `liketag.png`：收藏标签。

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
- `ai_prefer`
- `ai_auto_capture`
- `ai_model_path`

## 打包说明

标准版打包需要：

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
