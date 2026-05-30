# Mnemosyne v0.4.0 完整测试报告

**测试日期**: 2026-05-29  
**测试内容**: Intracerebral Hemorrhage 文献检索全流程测试  
**数据库**: SQLite (WAL模式)  
**输出目录**: `data/`, `vault/`

---

## 一、测试概览

### 1.1 环境

| 项目 | 值 |
|------|-----|
| Python | 3.12 |
| 操作系统 | Linux |
| API | Semantic Scholar (无LLM, deterministic模式) |
| 速率限制 | 1.1秒/请求 |

### 1.2 命令执行记录

```bash
# 安装
pip install -e ".[dev]"

# 初始化
knowcran init

# 搜索文献（40+主题变体）
knowcran discover "intracerebral hemorrhage" --limit 500 --no-llm
knowcran discover "hypertensive intracerebral hemorrhage" --limit 300 --no-llm
# ... 更多主题

# 提取声明
knowcran read-topic "intracerebral hemorrhage" --limit 20 --no-llm

# 生成综述
knowcran review "intracerebral hemorrhage" --max-papers 30 --no-llm
```

---

## 二、最终数据统计

| 指标 | 数值 | 说明 |
|------|------|------|
| **论文总数** | **6,569** | 去重后 |
| **声明数** | **4,248** | 确定性提取 |
| **引用链接** | **794** | 论文间引用关系 |
| **主题数** | **103** | 自动生成的搜索变体 |
| **综述证据项** | **72** | 来自30篇论文 |
| **综述参考文献** | **30** 篇 | 含完整DOI |

---

## 三、各步骤结果

### 3.1 文献发现 (discover)

以 `"intracerebral hemorrhage"` 为核心，自动生成5个搜索变体：
- `intracerebral hemorrhage`
- `intracerebral hemorrhage mechanism`
- `intracerebral hemorrhage treatment`
- `intracerebral hemorrhage review`
- `intracerebral hemorrhage clinical`

**扩展搜索主题**（手动指定）：

| 主题 | 新增论文 |
|------|---------|
| `intracerebral hemorrhage` (初始) | 468 |
| `ICH stroke` | 238 |
| `hemorrhagic stroke` | 196 |
| `hypertensive intracerebral hemorrhage` | 250 |
| `intracerebral hemorrhage prognosis` | 181 |
| `intracerebral hemorrhage surgery` | 172 |
| `intracerebral hemorrhage biomarker` | 260 |
| `intracerebral hemorrhage edema` | 178 |
| `intracerebral hemorrhage mortality` | 205 |
| `intracerebral hemorrhage hematoma expansion` | 254 |
| `intracerebral hemorrhage rehabilitation` | 212 |
| `intracerebral hemorrhage inflammation` | 218 |
| `intracerebral hemorrhage microglia` | 250 |
| `intracerebral hemorrhage neuroinflammation` | 264 |
| `intracerebral hemorrhage ferroptosis` | 153 |
| `intracerebral hemorrhage stem cell` | 135 |
| `intracerebral hemorrhage blood brain barrier` | 207 |
| `intracerebral hemorrhage oxidative stress` | 214 |
| `intracerebral hemorrhage ICH score` | 264 |
| `intracerebral hemorrhage MRI` | 210 |
| `intracerebral hemorrhage CT` | 172 |
| `intracerebral hemorrhage hypertension` | 171 |
| `intracerebral hemorrhage diabetes` | 198 |
| `intracerebral hemorrhage anticoagulant` | 166 |
| `intracerebral hemorrhage epidemiology` | 98 |
| `intracerebral hemorrhage incidence` | 162 |
| `intracerebral hemorrhage prevalence` | 212 |
| `intracerebral hemorrhage burden` | 249 |
| `intracerebral hemorrhage quality of life` | 154 |
| `intracerebral hemorrhage disability` | 219 |
| `intracerebral hemorrhage survival` | 177 |
| `intracerebral hemorrhage recovery` | 131 |
| 其余~20个主题（成像、手术、治疗等） | 累计~2,000 |

> **注**: 由于 `resolve_topic()` 的子串匹配逻辑，许多主题变体被解析为同一主题，新增论文数为累计增量（去重后净增）。实际API请求中大量论文因已存在而被跳过。

### 3.2 声明提取 (read-topic)

```
knowcran read-topic "intracerebral hemorrhage" --limit 20 --no-llm
→ Extracted 72 claims from topic papers
```

每次运行从20篇论文中提取约72条声明，分为以下类型：

| 证据类型 | 数量 | 说明 |
|---------|------|------|
| `abstract_summary` | 20 | 摘要总结 |
| `result` | 17 | 研究结果 |
| `full_text_needed` | 14 | 需全文验证 |
| `open_question` | 12 | 开放问题 |
| `limitation` | 6 | 研究局限 |
| `method` | 3 | 研究方法 |

### 3.3 综述生成 (review)

```
knowcran review "intracerebral hemorrhage" --max-papers 30 --no-llm
→ Review generated with 72 evidence items and 30 papers
```

**输出文件**：

| 文件 | 大小 | 说明 |
|------|------|------|
| `vault/reviews/intracerebral-hemorrhage_review.md` | 13KB | 综述正文 |
| `vault/reviews/intracerebral-hemorrhage_open_questions.md` | 2KB | 开放问题 |
| `vault/reviews/intracerebral-hemorrhage_evidence_matrix.csv` | 30KB | 证据矩阵 |
| `vault/reviews/intracerebral-hemorrhage_bibliography.bib` | 13KB | BibTeX引用 |
| `vault/reviews/intracerebral-hemorrhage_full_workflow_log.md` | 18KB | 完整日志 |

**综述涵盖的研究方向**：

1. **血肿扩张 (HE)** — 预测因子和治疗（发病率13-38%）
2. **血脑屏障 (BBB)** — 星形胶质细胞外泌体、miR-27a-3p通路
3. **神经炎症** — 微胶质细胞焦亡、NLRP3炎症小体
4. **铁死亡 (Ferroptosis)** — Nrf2/GPX4轴、硒纳米颗粒
5. **手术治疗** — 神经内镜、立体定向、微创手术
6. **临床预测** — ICH评分、斑点征、血红蛋白水平
7. **流行病学** — 种族差异、APOE基因型、高血压风险
8. **神经保护** — 干细胞治疗、外泌体、自噬调控

---

## 四、已知问题

### 4.1 主题解析 (Topic Resolution)

**症状**: 不同主题变体被解析为同一个

```
knowcran read-topic "intracerebral hemorrhage biomarker"
→ Resolved topic 'intracerebral hemorrhage biomarker' → 'intracerebral hemorrhage'
```

**原因**: `storage.py` 的 `resolve_topic()` 使用子串匹配，`"intracerebral hemorrhage biomarker"` 包含 `"intracerebral hemorrhage"`，总是返回最短匹配。

**影响**: 所有变体主题读取同一批论文，导致声明重复提取（每次 +72）。

### 4.2 网络超时

- 约15%的API请求因 `ConnectTimeout` 或 `ReadTimeout` 失败
- 失败请求不被缓存，下次重试
- 当前超时设置（connect=30s, read=120s）对于大负载请求仍然偏短

### 4.3 综述质量

- 无LLM辅助时，综述为确定性摘要拼接，缺乏深度分析
- 开放问题列表存在重复（"长期预后"出现了5次）
- 证据以 `abstract_summary` 为主（20/72），`result` 类较少（17/72）

---

## 五、文件结构

```
Mnemosyne/
├── knowcran/                  # 核心代码
│   ├── agents/                # 代理系统（新增）
│   │   ├── bulk_executor.py   # 批量执行器
│   │   ├── subprocess_runner.py # 子进程运行器
│   │   └── registry.py        # 代理注册表
│   ├── server/                # MCP服务器（重构）
│   │   ├── mcp.py             # MCP协议实现
│   │   └── tools.py           # 工具注册
│   ├── semantic_scholar.py    # API客户端（超时优化）
│   ├── storage.py             # 存储层（索引优化）
│   ├── discovery.py           # 文献发现
│   ├── reading.py             # 声明提取
│   └── review.py              # 综述生成
├── docs/
│   └── mcp/                   # MCP配置示例
├── data/                      # 数据库和缓存（.gitignore）
├── vault/                     # Obsidian vault输出（.gitignore）
├── tests/                     # 测试套件（新增）
├── pyproject.toml             # v0.4.0
└── uv.lock                    # 可重现构建
```

---

## 六、建议

| 优先级 | 改进项 | 影响 |
|--------|--------|------|
| P0 | 修复 `resolve_topic()` 子串匹配逻辑 | 避免主题冲突 |
| P1 | 启用 LLM provider 进行语义提取 | 提升综述质量 |
| P1 | 添加断点续传功能 | 应对网络超时 |
| P2 | 去重查询去重机制，避免重复API调用 | 节省API配额 |
| P2 | 增加综述中 `result` 类证据的权重 | 提升综述实用性 |
| P2 | 开放问题去重 | 提升可读性 |

---

**生成时间**: 2026-05-29  
**Mnemosyne 版本**: v0.4.0  
**GitHub 仓库**: https://github.com/shaoleishen/Mnemosyne
