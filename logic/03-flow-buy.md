# Flow Buy：批量买车

## 流程图

```mermaid
flowchart TB
    A["开始 Flow Buy"] --> B["进入主菜单"]
    B --> C["打开收藏簿"]
    C --> D["进入车辆收集"]
    D --> E["打开制造商筛选"]

    E --> F{"当前车辆方案"}
    F -- "斯巴鲁" --> G["识别 CCbrand<br/>Subaru"]
    F -- "马自达" --> H["识别 CCbrand_Mazda"]

    G --> I["识别斯巴鲁 22B 车辆卡"]
    H --> J["识别 Mazda 808 车辆卡"]
    I --> K["执行购买序列"]
    J --> K

    K --> L["购买计数 +1"]
    L --> M{"达到目标数量？"}
    M -- "否" --> K
    M -- "是" --> N["退出购买界面"]

    PRICE["车辆价格参数<br/>22B：330,000 CR<br/>Mazda：95,000 CR"]
    PRICE --> LIMIT["根据 CR 计算购买上限"]
    LIMIT --> K
```

## 车辆方案

| 方案 | 品牌模板 | 车辆模板 | 单价 |
|---|---|---|---:|
| 斯巴鲁 22B | `CCbrand.png` | `consumablecar.png` | 330,000 CR |
| Mazda 808 | `CCbrand_Mazda.png` | `consumablecar_Mazda.png` | 95,000 CR |

## 关键实现

- 斯巴鲁与马自达共用已经稳定的购买主流程。
- 车辆切换只改变品牌模板、车辆模板和价格参数。
- CR 限制根据车辆单价计算最多可购买数量。
- 达到购买数量或 CR 上限后，返回统一调度器。
