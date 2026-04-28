# 企业内部知识库上传式 RAG 系统

当前仓库是一套面向企业内部知识库问答场景的上传式 RAG 基线实现。一期目标不是继续堆 demo 功能，而是把现有系统收敛成一套可内部试点的本地文档上传式 RAG。

> 当前范围口径：
> - 一期只做本地文档上传入库，不做外部 connector
> - 当前检索基线是 `Qdrant dense retrieval + lexical rerank`，还不是一期目标中的 `hybrid retrieval`
> - 当前代码可运行，但不能把“可运行”理解成“已具备生产上线能力”

建议先读：

- [一期范围说明](./document/一期范围说明.md)
- [企业内部知识库上传式RAG开发计划_AI执行版](./document/企业内部知识库上传式RAG开发计划_AI执行版.md)
- [企业级RAG完整学习手册](./document/企业级RAG完整学习手册.md)

本仓库仍然适合学习企业级 RAG 的工程化拆分，但 README 中所有“当前能力”均以仓库现状为准，不把后续规划写成已支持能力。

## 一期范围与当前状态

| 项目 | 当前定义 |
| --- | --- |
| 产品定位 | 企业内部知识库上传式 RAG 系统 |
| 一期目标 | 从课程 demo 升级到可内部试点系统 |
| 一期必须做 | 本地文件上传入库、检索主链路升级、知识库级 ACL 预过滤、结构化回答与拒答、评估观测、基础稳态运行 |
| 当前基线 | 上传入库、异步任务雏形、Qdrant dense 检索、lexical rerank、多知识库选择、LangGraph 澄清与审核工作流、SSE 流式回答、任务中心、审计日志、系统总览 |
| 当前未完成 | 真正的 BM25 / hybrid retrieval、检索前 ACL 过滤、OCR、去重与版本治理、结构化回答强校验、回归评测、限流与降级 |
| 明确不做 | 外部 connector、外部数据源自动同步、多租户、Agentic RAG、多工具编排、复杂实验平台 |

## 当前基线能力

- **多助理管理**：支持创建、编辑、删除助理，配置默认知识库、模型参数、审核规则和版本快照。
- **知识库管理**：支持知识库创建、编辑、删除、文档管理和索引清理。
- **文档入库**：支持批量上传 `TXT / Markdown / CSV / JSON / YAML / XML / HTML / PDF / DOC / DOCX`，自动解析、分块并写入 Qdrant。
- **检索增强问答**：当前基于知识库片段进行问答，返回引用来源，支持多知识库范围检索；检索主链路仍是 dense retrieval + lexical rerank。
- **LangGraph 工作流**：内置问答、意图漂移检测、澄清、审核中断与恢复等节点。
- **SSE 流式输出**：聊天接口支持流式返回模型回答和运行事件。
- **人工审核台**：可配置高风险问题审核规则，命中后进入待审核状态，审核通过或驳回后恢复流程。
- **任务中心**：统一查看文档处理任务和审核任务，支持失败文档任务重试与批量重试。
- **审计日志**：记录普通问答、澄清、审核、失败等关键事件，便于追踪问题链路。
- **运行基线**：提供鉴权、角色权限、Alembic 迁移、Docker Compose、Postgres Checkpointer 和 readiness 概览，但完整稳态运行能力仍在一期里程碑中建设。

## 一期待完成能力

- **M1 检索主链路升级**：补真正的 lexical retrieval、dense + lexical 并行召回、融合、trace 和 context assembly。
- **M2 权限预过滤与知识治理**：补知识库级 ACL 预过滤，以及 `source / version / updated_at / tags / content_hash` 等治理字段。
- **M3 入库工程化**：补更稳定的异步任务机制、幂等、失败分类、重试治理、去重、OCR 与分格式 chunking。
- **M4 生成层可信度**：补结构化回答、引用强校验、低置信度拒答与 prompt 版本化。
- **M5 评估与可观测性**：补 golden dataset、retrieval/generation 分层回归和关键指标面板。
- **M6 稳态运行与上线准备**：补限流、超时、重试、降级梯度、readiness checklist 和基础告警。

## 技术栈

| 模块     | 技术                                            |
| -------- | ----------------------------------------------- |
| 前端     | Vue 3、TypeScript、Vite、Element Plus、Pinia    |
| 后端     | FastAPI、SQLAlchemy、Pydantic Settings、Uvicorn |
| 工作流   | LangGraph                                       |
| RAG      | LlamaIndex 分块、Qdrant 向量检索、词法重排      |
| 数据库   | 开发环境 SQLite，生产环境推荐 PostgreSQL        |
| 文档解析 | pypdf、python-docx、antiword                    |
| 部署     | Docker、Docker Compose、Alembic                 |

## 项目结构

```text
rag/
├── server/                         # FastAPI 后端服务
│   ├── app/                        # API、模型、服务、工作流、集成代码
│   ├── tests/                      # 后端测试
│   ├── alembic/                    # 数据库迁移
│   ├── Dockerfile
│   └── docker-compose.yml
├── web/                            # Vue 3 前端应用
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── document/
│   ├── 企业内部知识库上传式RAG开发计划_AI执行版.md
│   ├── 一期范围说明.md
│   ├── 企业级RAG完整学习手册.md
│   └── LangGraph问答工作流完整细节.md
└── rag笔记.md                       # 一期最高设计依据
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- npm 10+
- 可选：Docker / Docker Compose
- 可选：`antiword`，仅本机直接解析 `.doc` 文件时需要；Docker 镜像内已自动安装

### 1. 启动后端

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

后端默认使用本地 SQLite 和嵌入式 Qdrant，适合开发体验，无需额外启动数据库或向量库。

默认地址：

- API：`http://127.0.0.1:8000`
- OpenAPI：`http://127.0.0.1:8000/docs`

### 2. 启动前端

```bash
cd web
npm install
cp .env.example .env
npm run dev
```

默认前端地址：`http://127.0.0.1:5175`

### 3. 登录系统

开发环境内置演示账号，仅用于本地体验，请勿用于生产环境：

| 角色   | 用户名     | 密码             | 说明                     |
| ------ | ---------- | ---------------- | ------------------------ |
| 管理员 | `admin`    | `admin123456`    | 配置管理、运营处理、聊天 |
| 运营   | `operator` | `operator123456` | 运营处理、聊天           |
| 访客   | `viewer`   | `viewer123456`   | 只读聊天                 |

登录后可以创建知识库、上传文档、配置助理并开始问答。

## 模型与 Embedding 配置

项目兼容 OpenAI 风格接口。默认 `.env.example` 中 Embedding 示例使用 SiliconFlow 的 `BAAI/bge-large-zh-v1.5`，LLM 示例使用 OpenAI 的 `gpt-4o-mini`。

常用配置项：

```env
# Embedding
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_EMBEDDING_MODEL_NAME=BAAI/bge-large-zh-v1.5
OPENAI_EMBEDDING_DIMENSIONS=1024
OPENAI_EMBEDDING_API_KEY_ENV_VAR=SILICONFLOW_API_KEY
SILICONFLOW_API_KEY=your-siliconflow-key

# LLM
LLM_PROVIDER=openai
OPENAI_LLM_BASE_URL=https://api.openai.com/v1
OPENAI_LLM_MODEL_NAME=gpt-4o-mini
OPENAI_LLM_API_KEY=your-openai-key
```

如果你使用其他 OpenAI 兼容服务，通常只需要调整 `*_BASE_URL`、`*_MODEL_NAME` 和 API Key。

## Docker Compose 部署

后端目录提供了最小生产依赖编排：

```bash
cd server
docker compose up --build
```

该命令会启动：

- `postgres`：业务数据库和 LangGraph Postgres Checkpointer
- `qdrant`：向量数据库
- `api`：FastAPI 后端服务

Compose 默认会在 API 启动前执行 Alembic 迁移。生产环境请至少修改以下配置：

- `AUTH_SECRET_KEY`
- `DATABASE_URL`
- `WORKFLOW_CHECKPOINTER_POSTGRES_URL`
- `OPENAI_LLM_API_KEY` 或对应模型服务密钥
- `SILICONFLOW_API_KEY` 或对应 Embedding 服务密钥
- `CORS_ORIGINS`

## 常用命令

后端：

```bash
cd server
source .venv/bin/activate
pytest
python -m app.db.migrate describe
python -m app.db.migrate upgrade head
```

前端：

```bash
cd web
npm run dev
npm run build
npm run preview
```

## API 概览

后端默认 API 前缀为 `/api/v1`。

| 能力           | 路径                                 |
| -------------- | ------------------------------------ |
| 登录与当前用户 | `/auth/login`、`/auth/me`            |
| 助理管理       | `/assistants`                        |
| 知识库管理     | `/knowledge-bases`                   |
| 文档上传与删除 | `/knowledge-bases/{id}/documents`    |
| 会话管理       | `/sessions`                          |
| 聊天流式问答   | `/sessions/{session_id}/chat/stream` |
| 任务中心       | `/jobs`                              |
| 审核任务       | `/reviews`                           |
| 系统总览       | `/system/overview`                   |
| 健康检查       | `/health`                            |

完整接口请访问启动后的 OpenAPI 文档：`http://127.0.0.1:8000/docs`。

## 文档上传说明

当前支持以下格式：

- 文本类：`txt`、`md`、`csv`、`json`、`yaml`、`yml`、`xml`、`html`
- PDF：`pdf`
- Word：`doc`、`docx`

说明：

- `.pdf` 使用 `pypdf` 提取文本，不包含 OCR；扫描件 PDF 需要额外接入 OCR。
- `.docx` 使用 `python-docx` 提取段落和表格文本。
- `.doc` 使用 `antiword` 提取文本；Docker 环境已内置，本机运行需自行安装。
- 上传后会创建异步处理任务，可在任务中心查看进度、失败原因和重试入口。

## 二期方向与非本期目标

以下方向可以作为二期以后考虑，但当前仓库不要把它们理解为“已支持”或“一期正在做”：

- 外部 connector，以及对应的 webhook / polling / reconciliation 同步链路
- 多租户隔离和更细粒度权限体系
- Agentic RAG、多工具编排、复杂任务自动化
- 大规模 A/B test 和在线 LLM-as-judge 实验平台

详细阶段记录见：

- [一期范围说明](./document/一期范围说明.md)
- [企业内部知识库上传式RAG开发计划_AI执行版](./document/企业内部知识库上传式RAG开发计划_AI执行版.md)
- [企业级RAG完整学习手册](./document/企业级RAG完整学习手册.md)
- [LangGraph问答工作流完整细节](./document/LangGraph问答工作流完整细节.md)

## 贡献指南

欢迎提交 Issue 和 Pull Request。建议在提交前运行：

```bash
cd server
pytest

cd ../web
npm run build
```

如果改动涉及数据库结构，请同时补充 Alembic 迁移；如果改动涉及核心问答流程，请同步更新相关文档。

## License

开源前请根据你的发布计划补充许可证文件，例如 MIT、Apache-2.0 或其他许可证。

## 单机 Docker Compose（个人 Demo）

如果你只是个人演示或自用，可以直接使用根目录的 `docker-compose.yml` 同时启动前后端，后端使用本地 `SQLite + Qdrant local mode`，只需要一个持久化卷保存数据。

### 1. 准备环境变量

可以直接在执行命令前导出，或在 Coolify 中填写：

```bash
export AUTH_SECRET_KEY='replace-with-a-random-secret'
export SILICONFLOW_API_KEY='your-siliconflow-key'
export OPENAI_LLM_API_KEY='your-openai-key'
export VITE_API_BASE_URL='http://localhost:8000/api/v1'
```

如果前端和后端会分别挂到不同域名，请把 `VITE_API_BASE_URL` 换成后端公网地址，并同步修改后端 `CORS_ORIGINS`。

### 2. 启动服务

```bash
cd /path/to/rag
docker compose up --build -d
```

启动后默认地址：

- 前端：`http://127.0.0.1:8080`
- 后端 API：`http://127.0.0.1:8000`
- OpenAPI：`http://127.0.0.1:8000/docs`

### 3. 数据持久化

`docker-compose.yml` 中已经声明卷 `api_storage`，会保存：

- SQLite 数据库文件
- Qdrant 本地索引文件
- 上传文档和处理中间文件

迁移到 Coolify 时，给 `api` 服务挂载持久化卷到 `/app/storage` 即可。

### 4. 使用 `.env` 文件（推荐）

```bash
cd /path/to/rag
cp .env.example .env
# 按需修改里面的 key 和地址

docker compose --env-file .env up --build -d
```

### 5. 在 Coolify 里怎么用这个 compose

如果你想在 Coolify 里直接使用这个根目录编排文件，可以这样配：

- 选择 `Docker Compose` 部署方式
- Compose 文件使用仓库根目录的 `docker-compose.yml`
- 在环境变量中填写 `.env.example` 里的 key
- 给 `api` 服务挂持久化卷到 `/app/storage`
- 对外暴露：前端 `80`，后端如果不想直接暴露也可以只走内网

更推荐的域名方式：

- `web` 绑一个域名，例如 `rag.your-domain.com`
- `api` 可不单独暴露；若需要调试再绑 `api.your-domain.com`

如果前端通过公网域名访问后端，记得把 `VITE_API_BASE_URL` 改成真实后端地址，并把 `CORS_ORIGINS` 改成前端实际域名。
