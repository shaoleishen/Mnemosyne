# Mnemosyne / KnowCran 使用指南

> 本地化科研知识库 + MCP Server，为 AI Agent 提供可溯源的文献发现、证据提取、综述生成和多模态图表理解能力。

---

## 一、系统架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI Agent (Claude / Codex / Pi)           │
│                          ↕ MCP (stdio)                          │
├─────────────────────────────────────────────────────────────────┤
│                   KnowCran MCP Server                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ readonly │  │  curate  │  │  admin   │  │ Vision API   │   │
│  │ 19 tools │  │ 31 tools │  │ 33 tools │  │ (multimodal) │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                    Knowledge Base (SQLite)                       │
│  papers │ claims │ fulltext_chunks │ media_assets │ vlm_desc    │
├─────────────────────────────────────────────────────────────────┤
│  External Services                                              │
│  Semantic Scholar │ MinerU (PDF解析) │ Local Embeddings         │
│  MiMo Vision API  │ DashScope/Qwen   │ Claw (LLM Agent)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、安装与环境

### 2.1 Conda 环境

```bash
# 环境已存在
conda activate Mnemosyne
# Python 3.12.13, 161 packages
```

### 2.2 项目安装（editable 模式）

```bash
cd /home/bioshen/Code/Mnemosyne
pip install -e ".[dev,local,gpu]"
```

### 2.3 环境变量配置 (`.env`)

```bash
# === 核心配置 ===
SEMANTIC_SCHOLAR_API_KEY=<your-s2-key>
KNOWCRAN_DATA_DIR=data
KNOWCRAN_VAULT_DIR=vault

# === LLM Agent (Claw) ===
MNEMOSYNE_LLM_PROVIDER=claw
MNEMOSYNE_CLAW_BIN=/home/bioshen/Code/claw-code-main/rust/target/debug/claw
MNEMOSYNE_CLAW_MODEL=kimi/mimo-v2.5-pro

# === Vision API (多模态图表理解) ===
MNEMOSYNE_VISION_PROVIDERS=mimo
MNEMOSYNE_VISION_MIMO_API_BASE=https://token-plan-cn.xiaomimimo.com/v1
MNEMOSYNE_VISION_MIMO_API_KEY=<your-key>
MNEMOSYNE_VISION_MIMO_MODEL=mimo-v2-omni

# === 本地服务 ===
MNEMOSYNE_EMBEDDING_PROVIDER=local
MNEMOSYNE_LOCAL_EMBEDDING_DEVICE=cuda
MNEMOSYNE_MINERU_MODE=managed
MNEMOSYNE_MINERU_GPU=true
```

---

## 三、MCP Server 启动

### 3.1 三种安全 Profile

| Profile | 命令 | 工具数 | 适用场景 |
|---------|------|--------|----------|
| **readonly** | `knowcran serve-mcp-readonly` | 19 | 长期 Agent 连接，只读查询 |
| **curate** | `knowcran serve-mcp-curate` | 31 | 文献发现、阅读、综述、导出 |
| **admin** | `knowcran serve-mcp-admin` | 33 | 元数据修复、去重维护 |

### 3.2 启动服务

```bash
cd /home/bioshen/Code/Mnemosyne

# 推荐：readonly 模式（安全默认）
knowcran serve-mcp-readonly

# 需要写入操作时
knowcran serve-mcp-curate
```

> ⚠️ 必须在项目目录下运行，`load_dotenv()` 从 CWD 读取 `.env`。

### 3.3 Agent 客户端配置

**Claude Code** (`~/.claude/mcp.json`):
```json
{
  "mcpServers": {
    "knowcran": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory", "/home/bioshen/Code/Mnemosyne",
        "run", "knowcran", "serve-mcp-readonly"
      ],
      "env": {
        "KNOWCRAN_DATA_DIR": "/home/bioshen/Code/Mnemosyne/data",
        "KNOWCRAN_VAULT_DIR": "/home/bioshen/Code/Mnemosyne/vault"
      }
    }
  }
}
```

**Pi Agent**: 已有 pi package `mnemosyne-research`，包含 skills、prompts、extensions。

---

## 四、CLI 工作流（从零开始）

### 4.1 初始化

```bash
knowcran init
```

### 4.2 文献发现

```bash
# 搜索 Semantic Scholar，存储论文元数据
knowcran discover "intracerebral hemorrhage" --limit 100

# 查看数据库状态
knowcran stats
```

### 4.3 Claims 提取

```bash
# 从摘要中提取 claims（默认确定性提取）
knowcran read-topic "intracerebral hemorrhage" --limit 50

# 从单篇论文提取
knowcran read-paper <paper_id>
```

### 4.4 全文 PDF 流水线

```bash
# 一键运行：下载 PDF → 解析 → 图表截取 → Vision 描述 → 分块 → 嵌入
knowcran run-topic "intracerebral hemorrhage" --limit 50 --gpu

# 分步执行
knowcran download-topic "intracerebral hemorrhage" --limit 50
knowcran parse-topic "intracerebral hemorrhage"
```

**parse_paper_pdf 流水线（v1.0 新增媒体提取）：**

```
PDF 文件
  │
  ├─① 解析器选择（auto: MinerU → PyMuPDF fallback）
  ├─② 布局解析 → pages + elements（含 figure/table 元素）
  ├─③ 图表截取 → media_assets（PNG 截图保存到 data/runtime/media/）
  ├─④ 正文引用关联 → media_mentions（Figure 1 → 正文引用）
  ├─⑤ Vision API 描述 → vlm_descriptions（MiMo V2 Omni 读图）
  ├─⑥ 文本分块 → paper_chunks
  ├─⑦ 向量嵌入 → chunk_embeddings
  └─⑧ FTS 索引同步
```

### 4.5 综述生成

```bash
# 生成可溯源的综述草稿
knowcran review "intracerebral hemorrhage" --max-papers 50

# 基于全文的综述
knowcran review-fulltext "intracerebral hemorrhage" --max-papers 30
```

### 4.6 Obsidian 导出

```bash
knowcran export-obsidian "intracerebral hemorrhage"
# 输出到 vault/ 目录
```

### 4.7 本地服务管理

```bash
knowcran doctor              # 环境诊断
knowcran services start      # 启动 MinerU + Embedding
knowcran services status     # 查看运行状态
knowcran services stop       # 停止所有服务
```

---

## 五、MCP 工具详解（33 个）

### 5.1 只读查询工具 (16 个)

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `knowcran_search_papers` | 按关键词搜索论文 | `query`, `topic`, `limit` |
| `knowcran_search_claims` | 搜索 claims | `topic`, `evidence_type`, `min_confidence` |
| `knowcran_get_topic_papers` | 获取某主题的论文列表 | `topic`, `limit` |
| `knowcran_get_evidence_matrix` | 证据矩阵（论文×claims） | `topic`, `max_papers`, `include_quotes` |
| `knowcran_get_bibliography` | BibTeX 参考文献 | `topic`, `format` |
| `knowcran_stats` | 知识库健康统计 | — |
| `knowcran_search_fulltext` | FTS5 全文搜索 | `query`, `topic` |
| `knowcran_search_fulltext_hybrid` | 混合搜索（FTS5 + 向量） | `query`, `topic` |
| `knowcran_read_fulltext` | 读取全文分块 | `paper_id`, `page_start`, `page_end` |
| `knowcran_get_pdf_status` | PDF 下载状态 | `topic` |
| `knowcran_get_paper_note` | 论文阅读笔记 | `paper_id` |
| `knowcran_get_evidence_context` | 证据上下文 | `query`, `topic` |
| `knowcran_get_evidence_pack` | 证据包（含全文引用） | `query`, `topic` |
| `knowcran_get_page_context` | 页面级上下文 | `paper_id`, `page_number` |
| `knowcran_get_review_artifacts` | 综述产物 | `topic` |
| `knowcran_answer_rag` | 多模态 RAG 问答 | `query`, `topic` |
| `knowcran_audit_answer` | 答案审计（检测过度声明） | `answer_text`, `topic` |

### 5.2 写入/操作工具 (12 个)

| 工具 | 功能 |
|------|------|
| `knowcran_discover` | 搜索 Semantic Scholar 并存储 |
| `knowcran_read_topic` | 批量提取 claims |
| `knowcran_read_paper` | 单篇提取 claims |
| `knowcran_review` | 生成综述草稿 |
| `knowcran_review_fulltext` | 基于全文的综述 |
| `knowcran_run_topic` | 全文流水线（下载+解析+嵌入） |
| `knowcran_export_obsidian` | 导出 Obsidian 笔记 |
| `knowcran_download_paper_pdf` | 下载单篇 PDF |
| `knowcran_download_topic_pdfs` | 批量下载 PDF |
| `knowcran_parse_paper_pdf` | 解析单篇 PDF |
| `knowcran_parse_topic_pdfs` | 批量解析 PDF |

### 5.3 Vision / 多模态工具 (3 个) 🆕

| 工具 | 功能 | 参数 |
|------|------|------|
| `knowcran_describe_figure` | 用 Vision API 描述图表 | `media_id` 或 `image_path`, `task_type` |
| `knowcran_extract_table_markdown` | 表格截图 → Markdown | `media_id` 或 `image_path` |
| `knowcran_get_media_assets` | 获取论文的图表资产 | `paper_id` |

### 5.4 管理工具 (2 个)

| 工具 | 功能 |
|------|------|
| `knowcran_repair_metadata` | 修复缺失的论文元数据 |
| `knowcran_dedupe_claims` | 去重 claims |

---

## 六、Agent 使用示例

### 示例 1：文献搜索 + 证据矩阵

```
Agent: 帮我查找关于 ICH 后铁死亡的最新研究

→ 调用 knowcran_search_papers(query="intracerebral hemorrhage ferroptosis", limit=10)
→ 调用 knowcran_get_evidence_matrix(topic="intracerebral hemorrhage ferroptosis")
→ 综合结果，返回带引用的结构化回答
```

### 示例 2：全文 RAG 问答

```
Agent: MISTIE III 试验的主要结论是什么？

→ 调用 knowcran_answer_rag(query="MISTIE III trial results conclusions", topic="intracerebral hemorrhage")
→ 返回带 citation_key 和 source_quote 的可溯源答案
```

### 示例 3：多模态图表理解

```
Agent: 描述这篇论文的 Figure 2

→ 调用 knowcran_get_media_assets(paper_id="xxx")  # 获取图表列表
→ 调用 knowcran_describe_figure(media_id="yyy")    # Vision API 描述
→ 返回图表的详细文字描述
```

### 示例 4：表格提取

```
Agent: 把这篇论文 Table 1 转成 Markdown

→ 调用 knowcran_get_media_assets(paper_id="xxx")
→ 调用 knowcran_extract_table_markdown(media_id="zzz")
→ 返回结构化的 Markdown 表格
```

### 示例 5：综述生成

```
Agent: 帮我写一篇关于 ICH 后自噬的文献综述

→ 调用 knowcran_review_fulltext(topic="intracerebral hemorrhage autophagy", max_papers=30)
→ 返回带完整引用链的综述草稿
```

---

## 七、数据流全景

```
Semantic Scholar API
        │
        ▼
   ┌─────────┐     ┌───────────┐     ┌──────────────┐
   │ discover │────▶│  papers   │────▶│ read-topic   │
   └─────────┘     └───────────┘     │ (提取 claims) │
                                      └──────┬───────┘
                                             │
                                             ▼
                                      ┌─────────────┐
                                      │   claims    │
                                      └──────┬──────┘
                                             │
                        ┌────────────────────┼────────────────────┐
                        ▼                    ▼                    ▼
                 ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
                 │  evidence   │    │   review     │    │  Obsidian    │
                 │  matrix     │    │  (综述生成)   │    │  export      │
                 └─────────────┘    └──────────────┘    └──────────────┘

   PDF 下载 ──▶ MinerU/PyMuPDF 解析 ──▶ 图表截取 ──▶ Vision API 描述
                                             │              │
                                             ▼              ▼
                                      ┌──────────────┐ ┌──────────────┐
                                      │ 分块 + 嵌入  │ │ media_assets │
                                      └──────┬───────┘ │ vlm_desc     │
                                             │         └──────────────┘
                                             ▼
                                      ┌──────────────┐
                                      │ 向量搜索     │
                                      │ FTS 全文搜索  │
                                      └──────────────┘
```

---

## 八、证据溯源契约

每条 claim 必须保留以下字段，确保可追溯：

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

---

## 九、当前数据库状态

```
论文总数:     9,438
Claims 总数:  7,316
主题数量:     100+ (ICH 相关为主)
全文分块:     100
图表资产:     0 (待 PDF 解析流水线运行)
VLM 描述:     0 (待 Vision API 处理)
```

---

## 十、常见问题

**Q: `load_dotenv()` 找不到 `.env`？**
A: 必须 `cd /home/bioshen/Code/Mnemosyne` 后再运行命令。

**Q: Vision API 返回空？**
A: 检查 `MNEMOSYNE_VISION_PROVIDERS` 是否非空，以及对应的 API key 是否正确。

**Q: MinerU 解析失败？**
A: 运行 `knowcran doctor` 检查 Docker 和 GPU 状态。

**Q: MCP 工具在 profile 中不可用？**
A: readonly 只有 19 个只读工具；需要写入工具请用 curate 或 admin profile。
