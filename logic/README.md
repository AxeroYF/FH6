# FH6 Auto 项目逻辑说明

本目录用于说明项目的整体架构、大循环调度方式，以及四个主要业务模块的实现逻辑。

## 文档索引

- [整体架构与大循环](01-system-and-loop.md)
- [Flow Race：循环跑图](02-flow-race.md)
- [Flow Buy：批量买车](03-flow-buy.md)
- [Flow CJ：车辆专精与超级抽奖](04-flow-cj.md)
- [Flow Delete：删除车辆](05-flow-delete.md)
- [后台运行能力与技术对比](06-runtime-and-comparison.md)

## 项目整体架构

```mermaid
flowchart TB
    UI["控制台 UI<br/>次数、路线、车辆方案、技能树"]
    CFG["配置系统<br/>价格、阈值、路线、模型"]
    SCH["统一流程调度器<br/>大循环、步骤切换、失败恢复"]
    LOG["日志与诊断系统<br/>前台摘要、后台匹配记录"]

    subgraph FLOW["四大业务模块"]
        RACE["Flow Race<br/>循环跑图"]
        BUY["Flow Buy<br/>批量买车"]
        CJ["Flow CJ<br/>车辆专精与超级抽奖"]
        DEL["Flow Delete<br/>删除车辆"]
    end

    subgraph VISION["视觉识别层"]
        TM["模板匹配<br/>菜单、按钮、状态标签"]
        YOLO["YOLO 模型<br/>目标车辆选择"]
        BC["后台截图<br/>PrintWindow"]
    end

    subgraph INPUT["输入控制层"]
        KB["后台键盘<br/>PostMessage"]
        MS["后台鼠标<br/>窗口坐标点击"]
        HW["物理输入兜底<br/>SendInput"]
    end

    GAME["Forza Horizon 6"]

    UI --> SCH
    CFG --> UI
    CFG --> SCH
    SCH --> RACE
    SCH --> BUY
    SCH --> CJ
    SCH --> DEL

    RACE --> TM
    BUY --> TM
    CJ --> TM
    CJ --> YOLO
    DEL --> TM

    BC --> TM
    BC --> YOLO
    TM --> SCH
    YOLO --> SCH

    RACE --> KB
    BUY --> KB
    CJ --> KB
    DEL --> KB
    BUY --> MS
    CJ --> MS

    KB --> GAME
    MS --> GAME
    HW --> GAME
    GAME --> BC

    SCH --> LOG
    TM --> LOG
    YOLO --> LOG
```

## 完整业务闭环

```mermaid
flowchart LR
    R["跑图<br/>获得技能点"] --> B["购买消耗车辆"]
    B --> C["点亮车辆技能树<br/>获取超级抽奖"]
    C --> D["删除已消耗车辆<br/>释放车库空间"]
    D --> R
```

完整大循环为：

`循环跑图 → 批量买车 → 超级抽奖 → 删除车辆 → 循环跑图`
