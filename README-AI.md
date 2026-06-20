# FH6Auto 3.0 AI 辅助说明

本文说明如何开启 AI 辅助选车，以及如何继续采集数据、训练和验证模型。

## 1. AI 辅助是什么

AI 辅助用于“超级抽奖”的选车环节。V3.0 支持两种识别顺序：

```text
标准逻辑：
严格模板识别成功 -> 直接使用模板结果
严格模板识别失败 -> 如果已开启 AI辅助 -> 调用 YOLO 模型兜底

AI 优先逻辑：
如果已开启 AI辅助 + AI优先 -> 先调用 YOLO 模型
AI 失败 -> 使用严格模板识别兜底
```

这样可以同时保留轻量稳定的模板路径，也可以给分辨率、缩放、HDR 或画面差异较大的用户提供 AI 优先方案。

## 2. 如何开启 AI 辅助

### 使用 Release AI 版

如果下载的是 `FH6Auto-3.0-AI.zip`，压缩包中应包含：

```text
FH6Auto.exe
models/fh6_car_select_yolo.pt
images/
assets/
README.md
README-AI.md
```

使用步骤：

1. 解压压缩包。
2. 运行 `FH6Auto.exe`。
3. 在主界面“超级抽奖”区域打开 `AI辅助`。
4. 如果希望 AI 优先识别，再打开 `AI优先`。
5. 正常运行超级抽奖流程。

如果日志出现：

```text
[AISelect] model not found
```

说明模型文件不存在或路径不正确。请确认模型位于：

```text
models/fh6_car_select_yolo.pt
```

如果日志出现：

```text
[AISelect] cannot load YOLO model: No module named 'ultralytics'
```

说明当前版本没有内置 AI 运行依赖，或者你是从源码运行但没有安装 AI 依赖。请参考下面的源码运行部分。

### 从源码运行

源码运行不会自动安装依赖，需要手动安装。

普通环境：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

如果需要开启 AI 辅助，再安装：

```powershell
python -m pip install -r requirements-ai.txt
```

然后准备模型文件：

```text
models/fh6_car_select_yolo.pt
```

启动：

```powershell
python main.py
```

检查 AI 环境：

```powershell
python -c "import ultralytics, torch; print(ultralytics.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

如果 `torch.cuda.is_available()` 是 `False`，AI 仍可尝试使用 CPU，但推理速度会更慢。想使用 GPU，需要安装匹配显卡驱动和 CUDA 的 PyTorch。

## 3. 识别模式说明

### 只开启 AI辅助

```text
模板优先 -> AI 兜底
```

这是标准模式，适合大多数 1080p、非 HDR、模板稳定的用户。

### 同时开启 AI辅助 和 AI优先

```text
AI 优先 -> 模板兜底
```

适合以下情况：

- 分辨率不是 1920x1080。
- UI 缩放或窗口比例不同。
- 开启 HDR 后模板颜色变化明显。
- 普通模板经常 miss，但 AI 模型能稳定识别。

## 4. 预训练模型如何使用

主程序会按顺序查找以下模型路径：

```text
models/fh6_car_select_yolo.pt
runs/detect/fh6_car_select/yolo11n_all_boxes_v2/weights/best.pt
runs/detect/fh6_car_select/yolo11n_all_boxes/weights/best.pt
runs/detect/runs/fh6_car_select/yolo11n_draft/weights/best.pt
```

普通用户推荐只使用：

```text
models/fh6_car_select_yolo.pt
```

发布 Release 时，可以把训练好的 `best.pt` 重命名为：

```text
fh6_car_select_yolo.pt
```

并放入 `models` 文件夹。

## 5. 分辨率与 HDR 适配说明

当前预训练模型主要基于 1080p 截图训练。

相对纯模板匹配，YOLO 对分辨率缩放、目标位置变化、轻微 UI 尺寸变化通常更宽容，因此在部分非 1080p 环境下可能比原方法更稳。

但它不能保证完全适配所有情况，尤其是：

- 2K / 4K / 21:9 超宽屏。
- 不同 UI 缩放。
- HDR、滤镜、锐化或不同画质设置。
- 游戏 UI 更新导致标签样式变化。

如果非 1080p 或 HDR 用户识别失败，建议开启 `AI自动截图`，收集 `pass` / `miss` 样本后继续补充训练。

## 6. 数据记录

开启 `AI自动截图` 后，AI 尝试过程会保存到：

```text
debug/car_select_ai/raw
debug/car_select_ai/pass
debug/car_select_ai/miss
```

普通严格模板识别也会保存样本到：

```text
debug/car_select/raw
debug/car_select/pass
debug/car_select/miss
```

这些图片可以用于后续复盘、标注和训练。

注意：`debug`、`datasets`、`runs` 等目录是本地训练/调试数据，不建议提交到 GitHub 源码仓库。

## 7. 继续训练模型

### 导出数据集

如果已经有 `debug/car_select` 调试图，可以导出 YOLO 数据集：

```powershell
python tools\export_car_select_dataset.py --debug-dir debug\car_select --output datasets\fh6_car_select
```

生成目录：

```text
datasets/fh6_car_select/images/draft
datasets/fh6_car_select/labels/draft
datasets/fh6_car_select/meta
datasets/fh6_car_select/fh6_car_select.yaml
```

类别：

```text
0: new_tag
1: class_b600
2: target_car
```

### 训练

```powershell
python tools\train_car_select_yolo.py --model yolo11n.pt --epochs 80 --imgsz 960 --batch 8 --device 0
```

训练结果通常位于：

```text
runs/detect/fh6_car_select/yolo11n_draft/weights/best.pt
```

### 离线验证

```powershell
python tools\test_yolo_car_select.py --model runs\detect\fh6_car_select\yolo11n_draft\weights\best.pt --input datasets\fh6_car_select\images\draft --save-debug --device 0
```

如果验证效果满意，可复制为发布模型：

```powershell
mkdir models
copy runs\detect\fh6_car_select\yolo11n_draft\weights\best.pt models\fh6_car_select_yolo.pt
```

## 8. 常见问题

### No module named 'ultralytics'

当前 Python 环境没有安装 AI 依赖：

```powershell
python -m pip install -r requirements-ai.txt
```

### model not found

没有找到模型文件。请把模型放到：

```text
models/fh6_car_select_yolo.pt
```

### GPU 没有被识别

检查：

```powershell
python -c "import torch; print(torch.cuda.is_available())"
```

如果输出 `False`，请安装匹配 CUDA 的 PyTorch，或暂时使用 CPU。
