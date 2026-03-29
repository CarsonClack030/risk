# 污染场地风险评估系统学习指南

这份文档面向“第一次接触本项目的人”。

目标不是只告诉你“怎么跑起来”，而是帮助你真正看懂：

- 这个项目为什么这样分层
- 前端、Tauri 桌面壳、Python 后端分别负责什么
- 一次完整的“搜索污染物 -> 加入工作区 -> 填浓度 -> 开始计算 -> 查看结果”是怎么流动的
- 如果你想继续维护或二次开发，应该先从哪里下手

---

## 1. 项目定位

本项目是一个跨平台桌面版的“污染场地风险评估系统”。

技术组合如下：

- 前端界面：`React`
- 桌面壳：`Tauri`
- 后端服务：`Python`
- 数据库：`SQLite`

这一套组合的思路是：

- 用 React 写现代桌面界面，开发体验更好
- 用 Tauri 包装成 macOS / Windows 桌面应用，体积比 Electron 更小
- 保留 Python 作为计算核心，最大程度复用旧项目中已经验证过的风险公式
- 用 SQLite 嵌入运行数据库，避免要求用户额外安装数据库服务

---

## 2. 目录总览

建议先对照下面这棵“重要目录树”看：

```text
risk_tauri/
├── src/                              # React 前端
│   ├── App.jsx                       # 主界面与主状态管理
│   ├── api.js                        # 前端请求封装
│   ├── components.jsx                # 通用组件
│   ├── constants.js                  # 表头、路径、表单字段等静态配置
│   ├── main.jsx                      # React 入口
│   └── styles.css                    # 页面样式
├── backend/
│   ├── main.py                       # Python 启动入口
│   ├── build_sidecar.py              # 打包 sidecar 的脚本
│   └── src/risk_backend/
│       ├── api_server.py             # Python HTTP 接口层
│       ├── exporters.py              # Excel 导出
│       ├── models/entities.py        # 数据模型
│       ├── repositories/             # 数据访问层
│       └── services/calculator.py    # 风险公式核心
├── src-tauri/
│   ├── src/main.rs                   # Tauri 桌面壳入口
│   └── tauri.conf.json               # Tauri 打包配置
├── README.md                         # 运行和打包说明
└── LEARNING_GUIDE.md                 # 当前这份学习文档
```

---

## 3. 架构怎么理解

最简单的理解方式是“4 层模型”：

### 3.1 界面层：React

对应目录：`src/`

职责：

- 显示界面
- 维护页面状态
- 接收用户输入
- 调用后端接口
- 展示结果

它不负责：

- 直接访问 SQLite
- 直接做复杂风险公式计算

### 3.2 桌面壳层：Tauri

对应目录：`src-tauri/`

职责：

- 把网页界面变成桌面应用
- 启动 Python 后端
- 处理端口冲突
- 在前端和后端之间传递真实 API 地址

### 3.3 接口层：Python HTTP Server

对应文件：`backend/src/risk_backend/api_server.py`

职责：

- 接收前端发来的请求
- 解析 JSON
- 调用数据库层和计算层
- 把结果变成 JSON 返回前端

### 3.4 数据与公式层：Repository + Service

对应目录：

- `backend/src/risk_backend/repositories/`
- `backend/src/risk_backend/services/`

职责：

- Repository：读写数据库
- Service：执行业务规则和风险公式

---

## 4. 推荐阅读顺序

如果你第一次系统阅读这个项目，我建议严格按下面顺序来。

### 第 1 步：先看前端入口

文件：

- `src/main.jsx`
- `src/App.jsx`

为什么先看这里：

- 你先知道系统界面上有哪些功能区
- 你能先建立“用户视角”
- 后面再看后端时，容易知道这些接口是给谁服务的

重点关注：

- 页面有哪些状态
- 页面启动时会请求哪些接口
- “污染物目录、工作区、参数、结果、管理员”几个区域之间如何联动

### 第 2 步：再看前端 API 封装

文件：

- `src/api.js`

重点关注：

- 前端是怎么拿到真实后端地址的
- 为什么不能把端口写死
- 每个方法分别对应哪个后端接口

### 第 3 步：看 Tauri 如何拉起后端

文件：

- `src-tauri/src/main.rs`

重点关注：

- 为什么需要自动选择端口
- 开发态和发布态的后端启动方式有什么区别
- 应用退出时为什么要手动清理后端进程

### 第 4 步：看 Python 接口层

文件：

- `backend/src/risk_backend/api_server.py`

重点关注：

- 前端每个操作最后落到哪个 HTTP 路由
- `RiskBackend` 这一层如何组织业务
- 结果表为什么要做统一序列化配置

### 第 5 步：看数据模型

文件：

- `backend/src/risk_backend/models/entities.py`

重点关注：

- `Pollutant`
- `PollutantConcentration`
- `SelectedPollutant`
- `ParameterRow`
- `SiteSelection`

这些类会帮你搞清楚“系统里到底在传什么数据”。

### 第 6 步：看数据库访问层

推荐先看：

- `backend/src/risk_backend/repositories/database.py`
- `backend/src/risk_backend/repositories/catalog.py`
- `backend/src/risk_backend/repositories/workspace.py`
- `backend/src/risk_backend/repositories/parameters.py`
- `backend/src/risk_backend/repositories/results.py`

重点关注：

- 首次运行数据库怎么复制到本地
- 工作区为什么不是只写一张表
- 参数和结果表是怎么映射到数据库的

### 第 7 步：最后啃公式核心

文件：

- `backend/src/risk_backend/services/calculator.py`

这是最难的一步，但也是最关键的一步。

建议阅读策略：

1. 先看 `calculate()`
2. 再看 `_calculate_single()`
3. 再看 `_build_empty_state()`
4. 再看 `_run_nonvolatile()` 和 `_run_all_pathways()`
5. 然后按路径逐个看 `_calc_ois()`、`_calc_dcs()` 等
6. 最后再看 `_gaspd()` 和 `_build_summaries()`

不要一上来就盯着一大坨公式。

先搞清楚“框架”，再逐个啃公式会容易很多。

---

## 5. 一次完整业务流程怎么走

这里用一次最典型的用户操作举例。

### 场景：用户添加污染物并计算结果

#### 第 1 步：搜索污染物

前端位置：

- `src/App.jsx`

行为：

- 用户在搜索框输入关键词
- 前端调用 `api.listCatalog(keyword)`

后端链路：

- `api_server.py -> list_catalog()`
- `CatalogRepository.list_pollutants()`

结果：

- 返回污染物列表
- 前端只显示编号、名称、英文名
- 同时弹出建议下拉

#### 第 2 步：加入工作区

前端位置：

- `addCatalogItemToWorkspace()`

后端链路：

- `api_server.py -> add_workspace_item()`
- `WorkspaceRepository.add_pollutant()`

接口返回：

- 后端只返回“新增的这一条工作区记录”和最新总数
- 前端把这条记录直接追加到本地 `workspaceItems`

数据库动作：

- 向 `db_pol_temp` 写入一条工作区记录
- 向 `db_pol_con` 写入一条浓度记录
- 向所有结果表写入占位行

为什么这么做：

- 后续计算和展示都按工作区序号进行
- 同一污染物现在允许重复加入，因此必须用 `workspace_number` 唯一标识每一行
- 当工作区条目很多时，增量返回比“每加一条就回传整张工作区”更快

#### 第 3 步：编辑浓度

前端位置：

- `openConcentrationModal()`
- `handleSaveConcentrations()`

后端链路：

- `api_server.py -> update_concentrations()`
- `WorkspaceRepository.update_concentrations()`

结果：

- 每条工作区记录写入 4 类浓度：
  - 地表浓度
  - 下层土壤浓度
  - 地下水浓度
  - 地下水保护浓度

#### 第 4 步：开始计算

前端位置：

- `handleCalculate()`

提交内容：

- 适用标准
- 用地类型
- 勾选的暴露途径

后端链路：

- `api_server.py -> calculate()`
- `RiskCalculator.calculate()`
- `RiskCalculator._calculate_single()`
- 各路径公式
- `_build_summaries()`
- `ResultRepository.update_table()`

#### 第 5 步：查看结果

前端位置：

- `resultModalOpen`
- `DataTable`

后端来源：

- `serialize_results()`

结果类型：

- 暴露量-致癌
- 暴露量-非致癌
- 风险-致癌
- 风险-危害商
- 贡献率-致癌
- 贡献率-非致癌
- 风险控制值

#### 第 6 步：导出 Excel

后端链路：

- `api_server.py -> export_results()`
- `build_export_rows()`
- `build_xlsx()`

结果：

- 前端拿到 Blob
- 浏览器 / WebView 触发下载

---

## 6. 数据库在项目中的角色

这个项目虽然是桌面应用，但本质上仍然是“本地数据库驱动”的。

### 6.1 模板数据库

项目内置一份模板数据库，作为初始数据来源。

它通常包含：

- 污染物目录
- 参数默认值
- 用户表
- 结果表结构

### 6.2 运行数据库

首次启动时，系统会把模板数据库复制到本地应用目录。

这样做的好处：

- 用户每台机器都有独立的运行数据
- 不会把仓库内的模板数据库直接改脏
- 应用卸载和数据备份更清晰

### 6.3 为什么结果也要写回数据库

有些人第一次看会疑惑：

“既然结果已经算出来了，为什么不直接在内存里显示？”

这里写回数据库有几个明显好处：

- 保持与旧项目的数据组织方式一致
- 导出 Excel 时直接读结果表更方便
- 前端刷新时可以直接重新读取结果，不必依赖上一轮内存状态
- 结果结构天然稳定，适合持久化

---

## 7. 公式层应该怎么学

`calculator.py` 往往是大家最容易被吓到的地方。

我建议你用下面这个方法：

### 7.1 先分清三类值

#### 第一类：输入值

来自三处：

- 污染物理化参数
- 参数模板
- 当前场地浓度

#### 第二类：中间量

例如：

- `VF_subia`
- `VF_gwoa`
- `K_sw`
- `D_eff_s`

这些值通常是为后续路径服务的，不是最终展示给用户的结果。

#### 第三类：最终输出值

例如：

- `CR_ois`
- `HQ_dcs`
- `PCR_sn`
- `RCVS_n`

这些值会最终进入结果表。

### 7.2 再把路径拆开学

建议一次只看一条路径。

例如先看：

- `_calc_ois()`

问自己三个问题：

1. 它用到了哪些输入参数？
2. 它往 `state` 里写了哪些字段？
3. 这些字段最终会在哪张结果表里出现？

### 7.3 最后再看汇总

当你知道每条路径分别产出什么后，
再去看 `_build_summaries()` 就会顺很多。

因为这一步本质上只是：

- 做加法
- 算比例
- 反推控制值

---

## 8. 前端状态为什么这么多

第一次看 `App.jsx` 时，很容易觉得状态特别多。

这是正常的，因为它承担了整个工作台的状态协调。

你可以把状态分成 6 组理解：

1. 启动与通知
2. 目录搜索
3. 工作区
4. 参数弹窗
5. 结果弹窗
6. 管理员面板

只要按组看，就不会乱。

最重要的经验是：

- 正式数据和草稿数据必须分开

所以你会看到：

- `parameterGroups` 和 `parameterDraft`
- `workspaceItems` 和 `concentrationDraft`

这是一种很典型的“可撤销编辑”设计。

还有一个很实用的性能经验：

- 高频动作尽量返回“增量数据”，不要每次都回传整张大表

例如当前项目里“加入工作区”已经做成：

- 后端只返回新增项
- 前端本地追加

这样当用户连续加入上百条污染物时，界面会顺很多。

---

## 9. 如果你想继续开发，优先改哪里

### 9.1 想改界面

优先看：

- `src/App.jsx`
- `src/components.jsx`
- `src/styles.css`

### 9.2 想新增接口

优先看：

- `src/api.js`
- `backend/src/risk_backend/api_server.py`

开发顺序建议：

1. 前端先定义调用方法
2. 后端加路由
3. 仓储层或服务层补逻辑

### 9.3 想改公式

优先看：

- `backend/src/risk_backend/services/calculator.py`

建议：

- 每次只改一条路径
- 改完就立即做对照测试
- 不要一次同时动汇总和单路径公式

### 9.4 想改数据库结构

优先看：

- `backend/src/risk_backend/repositories/database.py`
- 各 repository

注意：

- 改数据库结构时，前端接口层和导出层往往也要同步调整

---

## 10. 常见阅读误区

### 误区 1：一上来就看公式细节

正确方式：

- 先看整体调用链，再看公式

### 误区 2：把前端和后端分开孤立地看

正确方式：

- 每看一个前端按钮，就立刻追它调用哪个 API
- 再看这个 API 调到哪个仓储或服务

### 误区 3：只盯数据库表，不看实体对象

正确方式：

- 先看 `entities.py`
- 再看 repository

因为对象模型是数据库和前端之间的“翻译层”。

---

## 11. 建议的学习节奏

如果你打算把这个项目真正学透，我建议分 3 天。

### 第一天：看懂产品和结构

目标：

- 跑起来
- 走通一遍业务流程
- 看懂前端和接口层

建议看：

- `README.md`
- `src/App.jsx`
- `src/api.js`
- `src-tauri/src/main.rs`
- `backend/src/risk_backend/api_server.py`

### 第二天：看懂数据层

目标：

- 理解数据库和对象之间如何映射
- 搞清楚参数、工作区、结果表之间的关系

建议看：

- `entities.py`
- `repositories/database.py`
- `repositories/catalog.py`
- `repositories/workspace.py`
- `repositories/parameters.py`
- `repositories/results.py`

### 第三天：看懂计算层

目标：

- 搞清楚每条路径和最终结果字段
- 能自己追一条公式从输入到输出

建议看：

- `services/calculator.py`

---

## 12. 建议你亲手做的 5 个练习

### 练习 1：打印真实后端地址

目标：

- 理解前端为什么不能写死端口

提示：

- 看 `src/api.js`
- 看 `src-tauri/src/main.rs`

### 练习 2：自己加一个前端指标卡

目标：

- 理解 React 页面状态如何驱动 UI

### 练习 3：给结果页再加一个摘要说明

目标：

- 理解结果数据如何从后端到前端

### 练习 4：跟踪一条工作区记录

目标：

- 从加入工作区开始，一路追到数据库与结果表更新

### 练习 5：挑一条路径公式做笔记

目标：

- 真正吃透某一条暴露路径

建议先选：

- `_calc_ois()` 或 `_calc_cgw()`

这两条相对更容易入门。

---

## 13. 最后给你的建议

这个项目最值得学的，不只是“会不会写一个桌面应用”，而是它把下面几件事放到了一起：

- 现代前端界面
- 跨平台桌面壳
- Python 本地服务
- SQLite 嵌入式数据库
- 专业领域公式计算

如果你能把这套链路看懂，以后你再做别的本地工具型项目，会轻松很多。

真正阅读时请记住一句话：

**先看数据怎么流，再看公式怎么算。**

只要这条主线抓住了，这个项目就不会难到无从下手。
