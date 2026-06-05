# Mnemosyne / KnowCran

> **本地优先的科研知识库 + MCP Server** —— 为 AI Agent 提供可溯源的文献发现、证据提取、综述生成和多模态图表理解能力。

[![CI](https://github.com/shaoleishen/Mnemosyne/actions/workflows/ci.yml/badge.svg)](https://github.com/shaoleishen/Mnemosyne/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](CHANGELOG.md)

---

## 为什么需要 Mnemosyne？

在科研工作中，你是否遇到过这些问题：

- 🔍 **文献搜索效率低** —— 手动翻阅上百篇论文，找不到关键证据
- 📊 **证据溯源困难** —— 综述中的观点无法追溯到原始文献
- 🤖 **AI Agent 缺乏专业知识** —— 通用 AI 无法访问你的文献库
- 📈 **图表理解障碍** —— PDF 中的图表无法被 AI 读取和分析

**Mnemosyne** 就是为解决这些问题而设计的。它是一个**本地运行**的知识库系统，让你可以通过 CLI 或 AI Agent（如 Claude、Codex、Pi）来管理、搜索和分析学术文献。

---

## 核心特性

| 模块 | 能力 |
|------|------|
| 🔎 **文献发现** | 搜索 Semantic Scholar，缓存原始响应，去重论文，存储主题归属 |
| 📖 **Claims 提取** | 从摘要或全文中提取声明，默认使用确定性提取，可选 LLM/Agent 增强 |
| 📋 **证据矩阵** | 构建带引用键、原文引用、证据状态和覆盖摘要的证据矩阵 |
| 📄 **全文处理** | 下载 PDF → MinerU/PyMuPDF 解析 → 图表截取 → Vision API 描述 → 分块 → 嵌入 |
| 🔍 **混合搜索** | FTS5 关键词搜索 + 密集向量相似度搜索（RRF 混合排序） |
| 📝 **综述生成** | 从存储的 claims 生成证据可控的综述草稿 |
| 📦 **Obsidian 导出** | 导出论文、claims、主题、综述、CSV 证据矩阵和 BibTeX |
| 🖼️ **多模态理解** | Vision API 描述图表，表格截图转 Markdown（支持 MiMo V2 Omni） |
| 🤖 **MCP Server** | 为 Claude Code、Claude Desktop、Codex 等 Agent 提供 33 个工具 |
| ✅ **证据审计** | 验证引用，检测常见过度声明风险 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                   AI Agent (Claude / Codex / Pi)                │
│                          ↕ MCP (stdio)                          │
├─────────────────────────────────────────────────────────────────┤
│                     KnowCran MCP Server                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ readonly │  │  curate  │  │  admin   │  │ Vision API   │   │
│  │ 19 tools │  │ 31 tools │  │ 33 tools │  │ (multimodal) │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                     Knowledge Base (SQLite)                     │
│  papers │ claims │ fulltext_chunks │ media_assets │ vlm_desc    │
├─────────────────────────────────────────────────────────────────┤
│  External Services                                              │
│  Semantic Scholar │ MinerU (PDF解析) │ Local Embeddings         │
│  MiMo Vision API  │ DashScope/Qwen   │ Claw (LLM Agent)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 安装

**前置条件：** Python 3.12+

```bash
# 克隆项目
git clone https://github.com/shaoleishen/Mnemosyne.git
cd Mnemosyne

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装（基础版）
pip install -e ".[dev]"

# 安装（含本地嵌入服务）
pip install -e ".[dev,local]"

# 安装（含 GPU 支持，用于 MinerU 和本地嵌入加速）
pip install -e ".[dev,local,gpu]"
```

### 2. 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
```

**最小配置（开箱即用）：**
```env
# Semantic Scholar API Key（可选，有 key 可以提高请求频率）
SEMANTIC_SCHOLAR_API_KEY=

# 数据目录
KNOWCRAN_DATA_DIR=data
KNOWCRAN_VAULT_DIR=vault
```

**完整配置（含 LLM Agent 和 Vision API）：**
```env
# === 核心配置 ===
SEMANTIC_SCHOLAR_API_KEY=your-s2-key
KNOWCRAN_DATA_DIR=data
KNOWCRAN_VAULT_DIR=vault

# === LLM Agent（可选，用于智能提取和综述）===
MNEMOSYNE_LLM_PROVIDER=claw
MNEMOSYNE_CLAW_BIN=/path/to/your/claw/binary
MNEMOSYNE_CLAW_MODEL=kimi/mimo-v2.5-pro

# === Vision API（可选，用于多模态图表理解）===
MNEMOSYNE_VISION_PROVIDERS=mimo
MNEMOSYNE_VISION_MIMO_API_BASE=https://your-api-endpoint/v1
MNEMOSYNE_VISION_MIMO_API_KEY=your-vision-api-key
MNEMOSYNE_VISION_MIMO_MODEL=mimo-v2-omni

# === 本地嵌入服务（可选，用于向量搜索）===
MNEMOSYNE_EMBEDDING_PROVIDER=local
MNEMOSYNE_LOCAL_EMBEDDING_DEVICE=cuda  # 或 cpu

# === MinerU PDF 解析（可选，用于全文解析）===
MNEMOSYNE_MINERU_MODE=managed
MNEMOSYNE_MINERU_GPU=true
```

### 3. 初始化项目

```bash
knowcran init
```

---

## 使用方式

### 方式一：CLI 命令行

#### 文献发现

```bash
# 搜索 Semantic Scholar 并存储论文
knowcran discover "intracerebral hemorrhage" --limit 100

# 查看数据库状态
knowcran stats
```

#### Claims 提取

```bash
# 从摘要中提取 claims（默认使用确定性提取）
knowcran read-topic "intracerebral hemorrhage" --limit 50

# 从单篇论文提取
knowcran read-paper <paper_id>

# 使用 LLM Agent 增强提取
knowcran read-topic "intracerebral hemorrhage" --limit 50 --llm
```

#### 全文 PDF 流水线（需要配置 MinerU）

```bash
# 一键运行完整流水线：下载 PDF → 解析 → 图表截取 → Vision 描述 → 分块 → 嵌入
knowcran run-topic "intracerebral hemorrhage" --limit 50 --gpu

# 分步执行
knowcran download-topic "intracerebral hemorrhage" --limit 50  # 下载 PDF
knowcran parse-topic "intracerebral hemorrhage"                # 解析 PDF
```

**PDF 解析流水线详解：**

```
PDF 文件
  │
  ├─① 解析器选择（auto: MinerU → PyMuPDF fallback）
  ├─② 布局解析 → pages + elements（含 figure/table 元素）
  ├─③ 图表截取 → media_assets（PNG 截图保存）
  ├─④ 正文引用关联 → media_mentions（Figure 1 → 正文引用）
  ├─⑤ Vision API 描述 → vlm_descriptions（MiMo V2 Omni 读图）
  ├─⑥ 文本分块 → paper_chunks
  ├─⑦ 向量嵌入 → chunk_embeddings
  └─⑧ FTS 索引同步
```

#### 搜索

```bash
# FTS5 关键词搜索
knowcran search-fulltext "ferroptosis mechanism" --topic "intracerebral hemorrhage"

# 混合搜索（FTS5 + 向量相似度）
knowcran search-fulltext-hybrid "ferroptosis mechanism" --topic "intracerebral hemorrhage"
```

#### 综述生成

```bash
# 生成可溯源的综述草稿
knowcran review "intracerebral hemorrhage" --max-papers 50

# 基于全文的综述（优先使用全文证据）
knowcran review "intracerebral hemorrhage" --max-papers 30 --fulltext
```

#### Obsidian 导出

```bash
# 导出到 vault/ 目录
knowcran export-obsidian "intracerebral hemorrhage"
```

#### 环境诊断

```bash
# 检查系统状态
knowcran doctor

# 检查 GPU 状态
knowcran doctor --gpu

# 检查 LLM 配置
knowcran llm-doctor

# 检查服务状态
knowcran services status
```

---

### 方式二：MCP Server（为 AI Agent 提供服务）

#### 启动 MCP Server

```bash
# 只读模式（推荐，安全默认，适合长期 Agent 连接）
knowcran serve-mcp-readonly

# 策展模式（包含文献发现、阅读、综述、导出）
knowcran serve-mcp-curate

# 管理模式（元数据修复、去重维护）
knowcran serve-mcp-admin
```

#### 配置 Agent 客户端

**Claude Code** (`~/.claude/mcp.json`):
```json
{
  "mcpServers": {
    "knowcran": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory", "/path/to/Mnemosyne",
        "run", "knowcran", "serve-mcp-readonly"
      ],
      "env": {
        "KNOWCRAN_DATA_DIR": "/path/to/Mnemosyne/data",
        "KNOWCRAN_VAULT_DIR": "/path/to/Mnemosyne/vault"
      }
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "knowcran": {
      "type": "stdio",
      "command": "/path/to/venv/bin/knowcran",
      "args": ["serve-mcp-readonly"],
      "cwd": "/path/to/Mnemosyne",
      "env": {
        "KNOWCRAN_DATA_DIR": "/path/to/Mnemosyne/data",
        "KNOWCRAN_VAULT_DIR": "/path/to/Mnemosyne/vault"
      }
    }
  }
}
```

**Pi Agent**: 已有 pi package `mnemosyne-research`，包含 skills、prompts、extensions。

---

### 方式三：Docker 部署

```bash
# 构建镜像
docker build -t mnemosyne:latest .

# 运行容器
docker run -it --gpus all \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/vault:/app/vault \
  -v $(pwd)/.env:/app/.env \
  mnemosyne:latest knowcran serve-mcp-readonly
```

---

## MCP 工具列表（33 个）

### 只读查询工具（19 个）

| 工具 | 功能 |
|------|------|
| `knowcran_search_papers` | 按关键词搜索论文 |
| `knowcran_search_claims` | 搜索 claims |
| `knowcran_get_topic_papers` | 获取某主题的论文列表 |
| `knowcran_get_evidence_matrix` | 证据矩阵（论文×claims） |
| `knowcran_get_bibliography` | BibTeX 参考文献 |
| `knowcran_stats` | 知识库健康统计 |
| `knowcran_search_fulltext` | FTS5 全文搜索 |
| `knowcran_search_fulltext_hybrid` | 混合搜索（FTS5 + 向量） |
| `knowcran_read_fulltext` | 读取全文分块 |
| `knowcran_get_pdf_status` | PDF 下载状态 |
| `knowcran_get_paper_note` | 论文阅读笔记 |
| `knowcran_get_evidence_context` | 证据上下文 |
| `knowcran_get_evidence_pack` | 证据包（含全文引用） |
| `knowcran_get_page_context` | 页面级上下文 |
| `knowcran_get_review_artifacts` | 综述产物 |
| `knowcran_answer_rag` | 多模态 RAG 问答 |
| `knowcran_audit_answer` | 答案审计（检测过度声明） |
| `knowcran_describe_figure` | Vision API 描述图表 |
| `knowcran_extract_table_markdown` | 表格截图转 Markdown |

### 写入/操作工具（12 个）

| 工具 | 功能 |
|------|------|
| `knowcran_discover` | 搜索 Semantic Scholar 并存储 |
| `knowcran_read_topic` | 批量提取 claims |
| `knowcran_read_paper` | 单篇提取 claims |
| `knowcran_review` | 生成综述草稿 |
| `knowcran_review_fulltext` | 基于全文的综述 |
| `knowcran_run_topic` | 全文流水线 |
| `knowcran_export_obsidian` | 导出 Obsidian 笔记 |
| `knowcran_download_paper_pdf` | 下载单篇 PDF |
| `knowcran_download_topic_pdfs` | 批量下载 PDF |
| `knowcran_parse_paper_pdf` | 解析单篇 PDF |
| `knowcran_parse_topic_pdfs` | 批量解析 PDF |
| `knowcran_get_media_assets` | 获取论文的图表资产 |

### 管理工具（2 个）

| 工具 | 功能 |
|------|------|
| `knowcran_repair_metadata` | 修复缺失的论文元数据 |
| `knowcran_dedupe_claims` | 去重 claims |

---

## Agent 使用示例

### 示例 1：文献搜索 + 证据矩阵

```
你：帮我查找关于 ICH 后铁死亡的最新研究

Agent 调用：
→ knowcran_search_papers(query="intracerebral hemorrhage ferroptosis", limit=10)
→ knowcran_get_evidence_matrix(topic="intracerebral hemorrhage ferroptosis")

返回：带引用的结构化回答
```

### 示例 2：全文 RAG 问答

```
你：MISTIE III 试验的主要结论是什么？

Agent 调用：
→ knowcran_answer_rag(query="MISTIE III trial results conclusions", topic="intracerebral hemorrhage")

返回：带 citation_key 和 source_quote 的可溯源答案
```

### 示例 3：多模态图表理解

```
你：描述这篇论文的 Figure 2

Agent 调用：
→ knowcran_get_media_assets(paper_id="xxx")  # 获取图表列表
→ knowcran_describe_figure(media_id="yyy")    # Vision API 描述

返回：图表的详细文字描述
```

### 示例 4：表格提取

```
你：把这篇论文 Table 1 转成 Markdown

Agent 调用：
→ knowcran_get_media_assets(paper_id="xxx")
→ knowcran_extract_table_markdown(media_id="zzz")

返回：结构化的 Markdown 表格
```

### 示例 5：综述生成

```
你：帮我写一篇关于 ICH 后自噬的文献综述

Agent 调用：
→ knowcran_review_fulltext(topic="intracerebral hemorrhage autophagy", max_papers=30)

返回：带完整引用链的综述草稿
```

---

## 本地服务管理

Mnemosyne 可以自动管理后台服务（MinerU 和本地嵌入服务器）。

### 安装本地服务依赖

```bash
# 安装本地服务依赖
pip install -e ".[local]"

# 如需 GPU 加速（用于 MinerU 和本地嵌入）
pip install -e ".[local,gpu]"
```

### 构建 MinerU Docker 镜像

```bash
# 下载官方 Dockerfile
wget https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile

# 构建本地镜像
docker build -t mineru:latest -f Dockerfile .
```

### 管理服务

```bash
# 启动所有服务
knowcran services start
knowcran services start --gpu  # 启用 GPU 加速

# 查看服务状态
knowcran services status

# 停止所有服务
knowcran services stop

# 查看服务日志
knowcran services logs mineru
knowcran services logs embedding

# 环境诊断
knowcran doctor
knowcran doctor --gpu
```

---

## 证据溯源契约

Mnemosyne 将每条 claim 视为临时性声明，除非能追溯到存储的证据。Agent 面向的输出应保留：

| 字段 | 说明 |
|------|------|
| `paper_id` | 论文唯一标识 |
| `claim_id` | Claim 唯一标识 |
| `citation_key` | 引用键（如 [Zhang2024]） |
| `claim_text` | Claim 文本 |
| `evidence_type` | abstract_summary / method / result / limitation / open_question |
| `confidence` | 置信度 (0-1) |
| `source_quote` | 原文引用 |
| `evidence_status` | fulltext_supported / abstract_only / animal_model |

> ⚠️ 仅基于摘要的证据会被明确标记。综述和答案生成不应将仅基于摘要或动物模型的证据呈现为完整的临床证据。

---

## 配置参考

所有配置项通过 `.env` 文件设置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SEMANTIC_SCHOLAR_API_KEY` | 空 | 可选的 Semantic Scholar API Key |
| `KNOWCRAN_DATA_DIR` | `data` | 数据目录（SQLite 和缓存） |
| `KNOWCRAN_VAULT_DIR` | `vault` | Obsidian 导出目录 |
| `KNOWCRAN_RATE_LIMIT_SECONDS` | `1.1` | Semantic Scholar 请求间隔 |
| `MNEMOSYNE_LLM_PROVIDER` | `none` | LLM 提供商：`none` 或 `claw` |
| `MNEMOSYNE_CLAW_BIN` | 自动检测 | Claw 二进制文件路径 |
| `MNEMOSYNE_CLAW_MODEL` | `sonnet` | Claw 使用的模型 |
| `MNEMOSYNE_PDF_DOWNLOAD_ENABLED` | `true` | 启用/禁用 PDF 下载 |
| `MNEMOSYNE_PDF_STRATEGY` | `fastest` | 下载策略 |
| `MNEMOSYNE_SCIHUB_ENABLED` | `true` | 启用 Sci-Hub 回退 |
| `MNEMOSYNE_LIBGEN_ENABLED` | `true` | 启用 LibGen 回退 |
| `MNEMOSYNE_PDF_PARSER` | `auto` | PDF 解析器：`auto`、`mineru` 或 `pymupdf` |
| `MNEMOSYNE_MINERU_MODE` | `managed` | MinerU 运行模式 |
| `MNEMOSYNE_MINERU_GPU` | `false` | 启用 MinerU GPU 加速 |
| `MNEMOSYNE_EMBEDDING_PROVIDER` | `openai` | 嵌入提供商：`openai`、`local` 或 `none` |
| `MNEMOSYNE_LOCAL_EMBEDDING_MODEL` | `BAAI/bge-m3` | 本地嵌入模型 |
| `MNEMOSYNE_LOCAL_EMBEDDING_DEVICE` | `cpu` | 本地嵌入设备：`cpu` 或 `cuda` |
| `MNEMOSYNE_VISION_PROVIDERS` | 空 | Vision API 提供商列表 |
| `MNEMOSYNE_VISION_MIMO_API_KEY` | 空 | MiMo Vision API Key |

完整配置请参考 [`.env.example`](.env.example)。

---

## Sci-Hub & LibGen 合规声明

> [!WARNING]
> **版权和法律警告：**
> - Mnemosyne 默认启用 Sci-Hub 和 LibGen 集成，以协助研究人员检索学术资料。
> - 通过这些未授权索引源下载受版权保护的科学论文可能违反您所在司法管辖区的知识产权或版权法。
> - **Mnemosyne 的作者和贡献者对用户活动不承担任何责任。**
> - 论文元数据中的直接开放获取 PDF URL 会优先尝试。之后，来源顺序取决于所选策略；使用 `--strategy legal_only` 可避免未授权来源。
> - 要完全关闭未授权来源，请修改 `.env` 文件：
>   ```env
>   MNEMOSYNE_SCIHUB_ENABLED=false
>   MNEMOSYNE_LIBGEN_ENABLED=false
>   ```

---

## 测试

```bash
# 运行所有测试
pytest -v

# 运行测试并生成覆盖率报告
pytest --cov=knowcran --cov-report=term-missing
```

CI 工作流在 Linux、macOS 和 Windows 上运行 Python 3.12 和 3.13 的测试。

---

## 项目结构

```
Mnemosyne/
├── knowcran/                 # 核心代码
│   ├── agents/              # Agent 提供商框架
│   ├── llm/                 # LLM 集成
│   ├── media/               # 媒体提取（图表截取、关联）
│   ├── paper_fetch/         # PDF 下载器（多源）
│   ├── parsers/             # PDF 解析器（MinerU、PyMuPDF）
│   ├── rag/                 # RAG 查询流程
│   ├── server/              # MCP Server
│   ├── services/            # 本地服务管理
│   └── vision/              # Vision API 集成
├── tests/                   # 测试套件
├── docs/                    # 文档
├── scripts/                 # 脚本工具
├── data/                    # 数据目录（gitignore）
├── vault/                   # Obsidian 导出目录（gitignore）
├── .env.example             # 环境变量模板
├── pyproject.toml           # 项目配置
├── Dockerfile               # Docker 构建文件
└── README.md                # 英文文档
```

---

## 相关文档

- [英文文档](README.md)
- [使用指南](docs/USAGE_GUIDE.md)
- [贡献指南](CONTRIBUTING.md)
- [安全政策](SECURITY.md)
- [更新日志](CHANGELOG.md)
- [路线图](ROADMAP.md)
- [WSL2 + GPU 设置指南](docs/local-wsl-gpu-setup.md)
- [全文迁移说明](docs/fulltext-migration-notes.md)
- [发布指南](docs/RELEASE_GUIDE.md)

---

## 许可证

Apache-2.0. 详见 [LICENSE](LICENSE)。

---

## 致谢

- [Semantic Scholar](https://www.semanticscholar.org/) - 学术文献搜索 API
- [MinerU](https://github.com/opendatalab/MinerU) - PDF 解析引擎
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF 处理库
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
- [LangGraph](https://langchain-ai.github.io/langgraph/) - RAG 流程编排
