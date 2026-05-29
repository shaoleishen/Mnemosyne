# Mnemosyne

**版本：v0.5.0**

基于 Semantic Scholar 的本地化科研文献知识库——文献发现、声明提取、证据矩阵、综述生成一站式工具。

---

## 功能概览

| 功能 | CLI | MCP | 说明 |
|------|:---:|:---:|------|
| 文献搜索 | `discover` | ✅ | Semantic Scholar 搜索，支持分页、扩展引用 |
| 声明提取 | `read-topic` | ✅ | 从摘要确定性提取证据声明 |
| 综述生成 | `review` | ✅ | 三段式综述（Evidence Digest / Thematic Synthesis / Gap Map），论文数和证据项自动缩放 |
| 证据矩阵 | `export-obsidian` | ✅ | CSV/BibTeX/Markdown 输出 |
| 审计 | - | ✅ | 答案审计：引用验证、词汇重叠检测、overclaim 风险 |
| MCP 服务器 | `serve-mcp` | ✅ | FastMCP 协议，read-only 和 curate 双模式 |

---

## 快速开始

```bash
pip install -e ".[dev]"
cp .env.example .env
knowcran init

# 搜索文献
knowcran discover "intracerebral hemorrhage" --limit 200

# 提取声明（默认 100 篇论文，0=全部）
knowcran read-topic "intracerebral hemorrhage" --limit 100

# 生成综述（默认自动使用全部可用论文，上限 500）
knowcran review "intracerebral hemorrhage"

# 查看统计
knowcran stats
```

---

## 配置

环境变量在 `.env` 中：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SEMANTIC_SCHOLAR_API_KEY` | (空) | Semantic Scholar API 密钥（可选） |
| `KNOWCRAN_DATA_DIR` | `data` | SQLite 数据库和 API 缓存目录 |
| `KNOWCRAN_VAULT_DIR` | `vault` | Obsidian 笔记输出目录 |
| `KNOWCRAN_RATE_LIMIT_SECONDS` | `1.1` | API 请求间隔（秒） |
| `MNEMOSYNE_LLM_PROVIDER` | `none` | LLM 提供者（claw / none） |

---

## CLI 命令

```bash
# 文献发现（默认 200 篇，可加 --expand 扩展引用）
knowcran discover "topic" --limit 500 --expand

# 声明提取（limit=0 自动使用全部可用论文）
knowcran read-topic "topic" --limit 100

# 综述生成（max-papers=0 自动缩放，上限 500）
knowcran review "topic" --max-papers 100

# Obsidian 导出
knowcran export-obsidian "topic"

# 数据库统计
knowcran stats

# 查看单篇论文
knowcran show-paper PAPER_ID

# MCP 服务器
knowcran serve-mcp
```

---

## MCP 服务器

Mnemosyne 提供 FastMCP 协议服务器，可作为 Claude Code、Claude Desktop 或其他 MCP 客户端的工具。

```bash
# 启动 MCP 服务器
knowcran serve-mcp

# 配置示例见 docs/mcp/
# - docs/mcp/claude-code.mcp.json.example
# - docs/mcp/claude-desktop.config.json.example
# - docs/mcp/codex.config.toml.example
```

**MCP 工具列表**（12 个）：

| 工具 | 模式 | 说明 |
|------|:----:|------|
| `knowcran_stats` | read | 数据库统计 |
| `knowcran_search_papers` | read | 搜索论文 |
| `knowcran_search_claims` | read | 搜索声明 |
| `knowcran_get_topic_papers` | read | 获取主题论文 |
| `knowcran_get_evidence_matrix` | read | 获取证据矩阵 |
| `knowcran_get_bibliography` | read | 获取 BibTeX |
| `knowcran_audit_answer` | audit | 审计答案 |
| `knowcran_discover` | write | 文献发现 |
| `knowcran_read_topic` | write | 声明提取 |
| `knowcran_read_paper` | write | 单篇论文提取 |
| `knowcran_review` | write | 综述生成 |
| `knowcran_export_obsidian` | write | Obsidian 导出 |

---

## 数据目录结构

```
data/
  knowcran.sqlite          # SQLite 数据库
  raw/semantic_scholar/    # API 响应缓存
vault/
  papers/                  # 论文笔记
  claims/                  # 声明笔记
  topics/                  # 主题索引
  reviews/                 # 综述、证据矩阵、BibTeX
```

---

## 测试

```bash
pytest -v        # 全部 234 项测试
pytest -v -k "topic"  # 主题相关测试
pytest -v -k "mcp"    # MCP 相关测试
```

**测试分类**：

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_topic_resolution.py` | 主题精确匹配、子主题隔离、主题关系树、证据追溯、MCP schema |
| `test_mcp_server.py` | MCP 工具注册、调用、分页、审计、安全 |
| `test_review.py` / `test_review_v2.py` | 综述三段式格式、证据选择、LLM 回退 |
| `test_storage.py` / `test_storage_v2.py` | 存储、声明幂等性、迁移 |
| `test_extraction.py` | 确定性提取、LLM 提取、回退 |
| `test_s2_client.py` | Semantic Scholar API、缓存、重试、速率限制 |

---

## 版本历史

| 版本 | 亮点 |
|------|------|
| v0.5.0 | MCP 路径白名单、主题精确匹配、主题关系树、答案审计增强 |
| v0.4.0 | MCP 服务器重构、uv.lock、mcp 依赖 |
| v0.3.1 | 子进程运行器、超时优化、索引优化 |
| v0.3.0 | 批量执行器、代理系统、注册表 |
| v0.2.0 | 主题分类、综述改进 |
| v0.1.0 | MVP：搜索、提取、Obsidian 导出 |

---

## 许可

Apache-2.0
