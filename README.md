# 企业级 RAG 助理示例项目

一个面向企业知识库问答场景的 RAG 智能助手示例项目。项目以“可运行、可学习、可扩展”为目标，覆盖从文档入库、向量检索、LangGraph 工作流、SSE 流式问答、人工审核到系统运维的完整闭环。

> 适合用于学习企业级 RAG 架构、二次开发内部知识库助手、验证 LangGraph + FastAPI + Vue 的工程化落地方式。

## 功能特性

- **多助理管理**：支持创建、编辑、删除助理，配置默认知识库、模型参数、审核规则和版本快照。
- **知识库管理**：支持知识库创建、编辑、删除、文档管理和索引清理。
- **文档入库**：支持批量上传 `TXT / Markdown / CSV / JSON / YAML / XML / HTML / PDF / DOC / DOCX`，自动解析、分块并写入 Qdrant。
- **检索增强问答**：基于知识库片段进行问答，返回引用来源，支持多知识库检索。
- **LangGraph 工作流**：内置问答、意图漂移检测、澄清、审核中断与恢复等节点。
- **SSE 流式输出**：聊天接口支持流式返回模型回答和运行事件。
- **人工审核台**：可配置高风险问题审核规则，命中后进入待审核状态，审核通过或驳回后恢复流程。
- **任务中心**：统一查看文档处理任务和审核任务，支持失败文档任务重试与批量重试。
- **审计日志**：记录普通问答、澄清、审核、失败等关键事件，便于追踪问题链路。
- **生产基线**：提供鉴权、角色权限、Alembic 迁移、Docker Compose、Postgres Checkpointer 和 readiness 检查。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia |
| 后端 | FastAPI、SQLAlchemy、Pydantic Settings、Uvicorn |
| 工作流 | LangGraph |
| RAG | LlamaIndex 分块、Qdrant 向量库、混合检索 |
| 数据库 | 开发环境 SQLite，生产环境推荐 PostgreSQL |
| 文档解析 | pypdf、python-docx、antiword |
| 部署 | Docker、Docker Compose、Alembic |

## 项目结构

```text
agent-demo/
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
├── 企业级RAG完整学习手册.md          # 学习手册
├── 企业级RAG项目开发规范.md          # 开发规范
├── 企业级RAG项目开发进度.md          # 进度记录
└── LangGraph问答工作流完整细节.md     # 工作流细节
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
cd agent-demo/server
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
cd agent-demo/web
npm install
cp .env.example .env
npm run dev
```

默认前端地址：`http://127.0.0.1:5175`

### 3. 登录系统

开发环境内置演示账号，仅用于本地体验，请勿用于生产环境：

| 角色 | 用户名 | 密码 | 说明 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `admin123456` | 配置管理、运营处理、聊天 |
| 运营 | `operator` | `operator123456` | 运营处理、聊天 |
| 访客 | `viewer` | `viewer123456` | 只读聊天 |

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
cd agent-demo/server
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
cd agent-demo/server
source .venv/bin/activate
pytest
python -m app.db.migrate describe
python -m app.db.migrate upgrade head
```

前端：

```bash
cd agent-demo/web
npm run dev
npm run build
npm run preview
```

## API 概览

后端默认 API 前缀为 `/api/v1`。

| 能力 | 路径 |
| --- | --- |
| 登录与当前用户 | `/auth/login`、`/auth/me` |
| 助理管理 | `/assistants` |
| 知识库管理 | `/knowledge-bases` |
| 文档上传与删除 | `/knowledge-bases/{id}/documents` |
| 会话管理 | `/sessions` |
| 聊天流式问答 | `/sessions/{session_id}/chat/stream` |
| 任务中心 | `/jobs` |
| 审核任务 | `/reviews` |
| 系统总览 | `/system/overview` |
| 健康检查 | `/health` |

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

## 后续可扩展方向

当前仓库已提供完整的演示闭环，后续可以继续扩展：

- OCR 和更多文档格式解析
- 更精细的权限模型和多租户隔离
- 检索评测、反馈学习和 Prompt 版本管理
- 更完整的 Agent 工具调用和复杂任务编排
- 前端可观测性、指标面板和告警集成

详细阶段记录见：

- [企业级RAG项目开发进度.md](./企业级RAG项目开发进度.md)
- [企业级RAG完整学习手册.md](./企业级RAG完整学习手册.md)
- [LangGraph问答工作流完整细节.md](./LangGraph问答工作流完整细节.md)

## 贡献指南

欢迎提交 Issue 和 Pull Request。建议在提交前运行：

```bash
cd agent-demo/server
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
cd agent-demo
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
cd agent-demo
cp .env.example .env
# 按需修改里面的 key 和地址

docker compose --env-file .env up --build -d
```

### 5. 在 Coolify 里怎么用这个 compose

如果你想在 Coolify 里直接使用这个根目录编排文件，可以这样配：

- 选择 `Docker Compose` 部署方式
- Compose 文件使用 `agent-demo/docker-compose.yml`
- 在环境变量中填写 `.env.example` 里的 key
- 给 `api` 服务挂持久化卷到 `/app/storage`
- 对外暴露：前端 `80`，后端如果不想直接暴露也可以只走内网

更推荐的域名方式：

- `web` 绑一个域名，例如 `rag.your-domain.com`
- `api` 可不单独暴露；若需要调试再绑 `api.your-domain.com`

如果前端通过公网域名访问后端，记得把 `VITE_API_BASE_URL` 改成真实后端地址，并把 `CORS_ORIGINS` 改成前端实际域名。
