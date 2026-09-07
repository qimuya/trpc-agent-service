# 基于 tRPC-Agent 设计多租户节点化 Agent 部署平台

## 背景和价值
企业在落地 Agent 应用时，通常不会只部署一个单体机器人，而是希望面向多个部门、多个业务线、多个 IM 入口和多个数据后端
，构建一套可统一管理的 Agent 平台。例如：客服团队希望把 Agent 接入企业微信，研发团队希望接入内部群机器人，运营团队>希望接入微信公众号或微信客服，不同租户又需要隔离会话、记忆、知识库、工具权限和审计日志。
tRPC-Agent-Python 已经具备 Agent 编排、Tool / MCP、Session、Memory、Knowledge、Filter、Telemetry、FastAPI 服务化、OpenClaw / IM 通道、A2A / AG-UI 等能力。该题要求基于这些能力设计一个“多租户、可节点化部署、支持多后端数据同步、可接>入微信 / 企业微信等 IM 软件”的生产级方案。
这个题目解决的业务痛点是：企业希望把 Agent 能力从单点 demo 扩展成平台化服务，同时满足租户隔离、弹性部署、数据一致性
、IM 触达、审计合规和后端可替换等要求。它的价值在于把框架能力真正映射到企业级 Agent 平台架构，而不是只停留在单个 Agent 脚本。 
根据需要可以选择Python或者Go语言框架进行实现
任务描述
请设计一个基于 tRPC-Agent-Python 的多租户节点化 Agent 部署平台。平台需要支持多个租户创建和部署自己的 Agent，每个租>户可以绑定不同 IM 通道、选择不同数据后端、配置不同工具权限和知识库，并允许多个 Agent 节点水平扩展。系统需要考虑跨节
点会话路由、数据同步、后端适配、IM 消息接入、监控审计和故障恢复。
本题以架构设计为主，可以包含少量关键伪代码、接口定义或数据模型示例。不要求实现完整系统，但方案必须足够具体，能指导>后续工程落地。

## 具体要求
### 多租户与节点部署
- 设计租户模型，至少包含 tenant_id、应用配置、模型配置、工具权限、IM 通道配置、数据后端配置、审计策略。
- 设计节点部署拓扑，说明 Agent Gateway、Agent Worker、Channel Adapter、Storage Adapter、Admin API、Telemetry Collector 等组件如何协作。
- 支持多节点水平扩展，说明用户消息如何路由到正确租户和正确 session。
- 说明是否需要 sticky session；如果不需要，说明如何依赖共享 Session / Memory 后端实现无状态 Worker。
- 设计租户隔离机制，包括配置隔离、数据隔离、工具权限隔离、日志脱敏和密钥管理。

### 数据同步与多后端支持
- 支持不同租户选择不同数据后端，例如 InMemory、Redis、SQL、向量库、对象存储或外部 Memory 服务。
- 设计统一的数据访问抽象，说明 Session、Memory、Summary、Artifact、Knowledge、Audit Log 分别如何存储。
- 设计数据同步策略，至少覆盖：  
- 多节点并发写入同一 session 的一致性。
- Session event、state、summary 的更新顺序。
- Memory 写入后的跨节点可见性。
- 后端从 Redis 迁移到 SQL 或从本地向量库迁移到远端向量库时的数据迁移方案。
- IM 消息重复投递时的幂等处理。
- 说明不同后端的一致性取舍，例如强一致、最终一致、读写延迟、成本和运维复杂度。
- 给出一个最小数据模型或表结构示例，至少包含 tenant、agent app、session、message/event、memory、summary、channel binding、audit log。

### IM 软件接入
- 设计 IM Channel Adapter，支持企业微信、微信客服、微信公众号、Telegram 或其他 IM 通道中的至少两类。
- 说明外部 IM 消息如何转换为 tRPC-Agent-Python 的用户输入，Agent Event 如何转换为 IM 回复、流式消息或卡片消息。
- 设计 IM 账号和租户绑定方式，包括 webhook URL、token、secret、回调验签、消息去重、用户身份映射。
- 说明群聊和单聊的 session_id 生成规则，以及用户跨群、跨租户时的隔离策略。
- 考虑 IM 平台限制，例如消息长度、频率限制、异步回复、图片 / 文件消息、撤回或失败重试。

### 治理、监控和安全
- 使用 Filter 设计租户级治理策略，例如工具白名单、敏感信息脱敏、预算限制、危险工具二次确认、IM 用户权限校验。
- 设计监控指标，例如请求量、模型调用耗时、工具调用耗时、IM 投递成功率、错误率、token 消耗、每租户成本、Session 后端延迟。
- 说明如何接入 OpenTelemetry 或等价 tracing，要求 trace 能串起 IM callback、Runner 执行、Tool 调用、Session / Memory 读写和 IM 回复。
- 设计审计日志字段，至少包含 tenant_id、channel、user_id、session_id、agent_name、tool_name、decision、latency、error_type、cost、trace_id。
- 说明密钥管理和脱敏策略，IM token、模型 API key、数据库密码不能明文出现在日志、trace 或错误报告中。

### 故障恢复与运维
- 设计节点故障、IM 重试、数据库短暂不可用、模型超时、工具执行失败时的降级策略。
- 说明如何做灰度发布和租户级配置回滚。
- 说明如何做容量评估，例如每节点并发 session 数、平均 token 消耗、Redis / SQL QPS、IM 回调峰值。
- 设计最小可运行部署方案和生产推荐部署方案，可以使用 Docker Compose、Kubernetes 或等价部署方式描述。
交付物
- 一份架构设计文档，建议 2000 – 4000 字。
- 一张系统架构图，展示 Gateway、Worker、Channel Adapter、Storage Adapter、Filter、Telemetry、数据库和 IM 平台之间的
关系。
- 一张核心时序图，展示“企业微信用户发消息 → Agent 执行 → Tool 调用 → Session / Memory 写入 → IM 回复”的完整链路。
- 一份数据模型设计，包含核心表结构或 JSON schema。
- 一份数据同步和幂等策略说明。
- 一份多后端适配方案，说明 Redis / SQL / 向量库 / 对象存储分别适合存什么。
- 一份风险清单，列出至少 8 个生产风险及对应缓解措施。 
- 一份基于该设计的github实现的代码 

## 题目难点
- 多租户隔离不是只加一个 tenant_id 字段，还涉及配置、权限、密钥、数据、日志、工具和成本隔离。
- 节点化部署要求 Agent Worker 尽量无状态，但 Agent 又天然依赖 Session、Memory、Summary 和工具上下文，需要设计可靠的
共享状态层。
- IM 通道存在消息乱序、重复投递、响应超时、长度限制和身份映射问题，不能简单等同于 HTTP chat API。
- 不同后端的数据一致性能力不同，Redis、SQL、向量库、对象存储无法用同一种同步策略处理。
- Agent 执行链路包含模型、工具、MCP、知识库、沙箱和外部系统，监控和审计必须跨组件串联。 
- 企业级平台必须考虑灰度、回滚、租户级限流、成本控制和合规审计。 

## 验收标准
1.架构方案必须覆盖多租户、节点化部署、数据同步、多后端支持、IM 接入、治理监控和故障恢复。
2.数据模型必须能表达 tenant、agent、channel binding、session、event、memory、summary、audit log 的关系。
3.必须说明至少两种 IM 通道的接入差异，其中至少包含微信或企业微信。
4.必须说明至少三类后端的数据存储和同步策略，例如 Redis、SQL、向量库或对象存储。
5.必须给出一条完整消息链路的时序说明，包含 trace_id 或 request_id 如何贯穿链路。 
6.必须列出至少 8 个生产风险和缓解措施。 
7.方案需要明确哪些能力可直接复用 tRPC-Agent-Python，哪些需要新增平台层模块。

## tRPC-Agent SDK 最小验证

本仓库提供一个完全离线、无需模型 API Key 的兼容性验证，用于证明验收标准 7
中的框架复用基线：Agent 执行、Event 输出和 Session 管理由固定版本
`trpc-agent-py==1.1.19` 直接提供。该验证不代表多租户、Gateway、IM、共享存储或
生产部署已经实现。

```powershell
uv sync --group dev
uv run python -m trpc_service.agent.sdk_validation
uv run python -m trpc_service.agent.sdk_validation --json
uv run pytest tests/sdk_validation -q
```

完整的运行前提、预期输出、重复性与计时验收方式见
[`specs/001-trpc-agent-sdk-validation/quickstart.md`](specs/001-trpc-agent-sdk-validation/quickstart.md)。

## 第二阶段：多租户本地消息闭环

仓库现已实现一个离线、单进程的纵向验证链路：`Local HTTP Channel Adapter →
Gateway → HMAC Channel Binding → tenant-scoped Session → Agent Worker → 官方
tRPC-Agent Runner → 统一回复 → Audit/Metrics`。两个演示租户使用独立运行时密钥，
同租户多轮消息保持上下文，跨租户会话、审计和指标隔离；重复消息、冲突、超时、
取消和审计故障都有稳定语义。

```powershell
uv sync --group dev
$env:TRPC_DEMO_ALPHA_SECRET = "<runtime-generated-secret>"
$env:TRPC_DEMO_BETA_SECRET = "<different-runtime-generated-secret>"
uv run trpc-agent-local-serve --host 127.0.0.1 --port 8000
```

另一个 PowerShell 会话设置相同的临时环境变量后，可发送一条签名消息：

```powershell
uv run trpc-agent-local-send --binding-id binding-alpha --secret-env TRPC_DEMO_ALPHA_SECRET --external-message-id alpha-001 --external-user-id shared-user --conversation-type direct --external-conversation-id shared-conversation --text "Remember validation token ALPHA."
```

完整双租户、多轮、重复、冲突与拒绝演示见
[`specs/002-multitenant-local-message-flow/quickstart.md`](specs/002-multitenant-local-message-flow/quickstart.md)。
自动化验收命令为 `uv run pytest -q`。

本阶段明确只使用 InMemory Repository、单进程锁、本地 MetricsSnapshot 和确定性离线
模型；它不代表真实企业微信、Redis/SQL、跨节点一致性、生产 Telemetry、真实模型、
Kubernetes 或管理后台已经完成。Repository/Adapter 端口已保留，后续后端必须复用
现有契约测试。

## 第三阶段：多节点共享状态消息闭环

仓库进一步提供本地双 Worker 验证：两个独立进程共享 Redis 7.4.11 的幂等、Session、
租约和 fencing 状态，以及 PostgreSQL 17.11 的权威租户配置、Audit 和 RecoveryMarker。
同一会话可跨节点继续；同一消息并发到达时只有一个 owner；同会话串行而不同会话并行；
配置或状态后端不可用时失败关闭，不回退到进程内状态。

```powershell
uv sync --group dev
# 先在当前 PowerShell 设置两个 Channel secret、Redis/PostgreSQL 临时密码和共享 DSN
docker compose -f deploy/local-shared/compose.yaml up -d --wait
$env:TRPC_RUNTIME_PROFILE = "shared"
uv run trpc-agent-shared-init
uv run trpc-agent-shared-serve --node-id worker-a --host 127.0.0.1 --port 8001
# 另一个设置相同运行时环境的 PowerShell 启动 worker-b，端口使用 8002
```

完整的临时凭据生成、双节点消息、故障测试、结果判读和安全清理步骤见
[`specs/003-shared-state-multinode-flow/quickstart.md`](specs/003-shared-state-multinode-flow/quickstart.md)，
答辩摘要见
[`specs/003-shared-state-multinode-flow/阶段成果记录.md`](specs/003-shared-state-multinode-flow/阶段成果记录.md)。

本阶段仍不包含真实企业微信、向量库、Kubernetes、管理后台、真实模型 API 或生产级
Telemetry，也不宣称生产 HA 或跨 Redis/PostgreSQL 的生产 exactly-once。

## 代码目录

```txt
|-- README.md  # 说明文档,包含设计, 安装,使用
|-- build.sh   # 开发的时候,用于构建项目
|-- clean.sh   # 清理当前项目的中间产物 
|-- coverage.sh # 运行单测覆盖率 
|-- data     # 存储服务需要的数据文件夹
|-- docs    # 各模块的说明文档目录 
|-- format.sh # 格式化项目代码风格
|-- lint_flake8.sh # 格式化项目代码风格
|-- start.sh  # 运行脚本可以启动服务 
|-- stop.sh  # 运行脚本可以停止服务 
`-- trpc_service # 源码项目
    |-- _cli.py # cli 可以直接命令行运行
    |-- agent   # agent 的源码
    |-- channels # 对接im 的channel
    |-- config   # 需要的配置 
    |-- log   # 日志代码,可以设置日志文件级别的操作
    |-- metrics # 监控
    |-- skill # 可以运行的skill文件
    |-- tenant # 多租户的代码 
    |-- tool # 需要使用的tool
    |-- version.py # 版本
    |-- web # 提供网页版本页面可以访问服务
    `-- workspace # 工作目录,包含本地,容器等沙箱环境
```
