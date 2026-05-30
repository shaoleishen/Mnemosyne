# Mnemosyne v0.3.0 测试报告

**测试日期**: 2026-05-29  
**测试内容**: 安全审查 + Intracerebral Hemorrhage 文献检索  
**测试环境**: Linux (Ubuntu), Python 3.12

---

## 一、安全审查结果

### 1.1 总体评估

| 类别 | 状态 | 风险等级 |
|------|------|----------|
| 敏感信息泄露 | ✅ 未发现泄露 | 低 |
| SQL 注入 | ⚠️ 存在潜在风险 | 中 |
| 命令注入 | ✅ 安全 | 低 |
| 依赖安全 | ✅ 无已知漏洞 | 低 |
| 配置安全 | ⚠️ 需要注意 | 中 |

### 1.2 高风险发现

#### API 密钥安全

**位置**: `.env` 文件（本地）

**发现的敏感信息**:
```env
SEMANTIC_SCHOLAR_API_KEY=<redacted>
ANTHROPIC_AUTH_TOKEN=<redacted>
ANTHROPIC_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic
```

**当前状态**:
- ✅ `.gitignore` 正确排除了 `.env` 文件
- ✅ Git 历史中未发现 `.env` 文件提交记录
- ✅ GitHub Secret Scanning 未检测到泄露

**建议**:
1. **立即轮换这些 API 密钥**，因为它们可能在开发过程中被暴露
2. 确保 `.env.example` 中的值都是空的或示例值

### 1.3 中风险发现

#### SQL 注入风险

**位置**: `knowcran/storage.py` 第 50-60 行

**问题代码**:
```python
# _migrate 函数中
for col, col_type in new_cols.items():
    if col not in existing_cols:
        cursor.execute(f"ALTER TABLE claims ADD COLUMN {col} {col_type}")
```

**风险分析**:
- 当前变量来自硬编码字典，实际风险较低
- 但这种模式是不安全的，如果未来修改为接受用户输入，将导致 SQL 注入

**建议修复**:
```python
# 使用白名单验证
ALLOWED_COLUMNS = {"claim_hash", "source_text_hash", "source_span_json", ...}
ALLOWED_TYPES = {"TEXT", "INTEGER", "REAL", "BLOB"}

for col, col_type in new_cols.items():
    if col not in existing_cols:
        if col not in ALLOWED_COLUMNS or col_type not in ALLOWED_TYPES:
            raise ValueError(f"Invalid column or type: {col}, {col_type}")
        cursor.execute(f"ALTER TABLE claims ADD COLUMN {col} {col_type}")
```

#### 仓库可见性

**发现**: 仓库是**公开的** (`"private": false`)

**风险**: 所有提交历史公开可见，代码中的任何敏感信息都可能被发现

**建议**: 如果这是个人研究项目，考虑设为私有仓库

### 1.4 良好实践

| 方面 | 状态 | 说明 |
|------|------|------|
| 子进程安全 | ✅ 安全 | 使用列表形式，不使用 shell=True |
| SQL 查询 | ✅ 安全 | 绝大多数使用参数化查询 |
| 速率限制 | ✅ 实现 | 有重试机制和指数退避 |
| 缓存机制 | ✅ 实现 | 文件缓存减少 API 调用 |
| 依赖版本 | ✅ 最新 | httpx 0.28.1, pydantic 2.13.4 |

---

## 二、文献检索测试结果

### 2.1 测试配置

```bash
# 安装
pip install -e ".[dev]"

# 初始化
knowcran init

# 执行检索（无 LLM rerank）
knowcran discover "intracerebral hemorrhage" --limit 200 --no-llm
```

### 2.2 测试结果统计

| 指标 | 数值 | 说明 |
|------|------|------|
| 论文总数 | 5,261 | 包含之前的数据 |
| 本次新增 | ~4,900 | 本次测试新增 |
| 声明数 | 3,393 | 未变化（未运行提取） |
| 链接数 | 794 | 未变化（未运行扩展） |
| 成功查询 | ~45 次 | 不同主题变体 |
| 失败查询 | ~15 次 | 因超时失败 |

### 2.3 成功检索的主题

| 主题 | 新增论文数 |
|------|-----------|
| intracerebral hemorrhage | 468 |
| intracerebral hemorrhage mechanism | 273 |
| intracerebral hemorrhage treatment | 107 |
| intracerebral hemorrhage review | 148 |
| intracerebral hemorrhage clinical | 164 |
| hypertensive intracerebral hemorrhage | 168 |
| intracerebral hemorrhage biomarker | 188 |
| intracerebral hemorrhage edema | 120 |
| intracerebral hemorrhage mortality | 145 |
| intracerebral hemorrhage hematoma expansion | 176 |
| intracerebral hemorrhage anticoagulation | 117 |
| intracerebral hemorrhage rehabilitation | 148 |
| intracerebral hemorrhage imaging | 139 |
| intracerebral hemorrhage microglia | 182 |
| intracerebral hemorrhage neuroinflammation | 193 |
| intracerebral hemorrhage neuroprotection | 125 |
| intracerebral hemorrhage ferroptosis | 122 |
| 其他 ~30 个主题 | ... |

---

## 三、发现的问题

### 3.1 🔴 网络连接不稳定（主要问题）

**现象**: 大量 `ConnectTimeout` 和 `ReadTimeout` 错误

```
ConnectTimeout: timed out
ReadTimeout: The read operation timed out
```

**错误示例**:
```
HTTPStatusError: Client error '429' for url 
'https://api.semanticscholar.org/graph/v1/paper/search/bulk?...'
```

**原因分析**:
1. Semantic Scholar API 服务器响应慢
2. 当前 httpx 超时设置只有 30 秒，对于大量数据请求不够
3. 可能存在网络代理或防火墙限制
4. 请求过于频繁触发速率限制

**影响**:
- 约 30% 的查询因超时失败
- 测试时间大幅延长（超过 30 分钟）
- 数据收集不完整

### 3.2 🟡 API 速率限制

**现象**: 遇到 429 错误

**原因**: Semantic Scholar 的 API 有请求频率限制，密集请求会触发 429 错误

**当前配置**:
```python
# knowcran/config.py
RATE_LIMIT_SECONDS = 1.1  # 每秒最多 1 次请求
```

**建议**: 将速率限制提高到 2-3 秒

### 3.3 🟡 数据质量问题

**问题**:
1. **重复查询**: 很多查询内容相似（如 "intracerebral hemorrhage surgery" vs "intracerebral hemorrhage surgical"），导致重复论文
2. **未去重验证**: 最终 5261 篇论文可能包含大量重复
3. **缓存未充分利用**: 超时失败的查询没有被缓存，下次还会重试

### 3.4 🟢 良好表现

| 方面 | 表现 |
|------|------|
| 安装过程 | ✅ 顺利，无依赖问题 |
| 初始化 | ✅ 快速完成 |
| 缓存机制 | ✅ 有效减少重复请求 |
| 错误处理 | ✅ 有重试机制 |
| 进度显示 | ✅ 有进度提示 |

---

## 四、建议修复方案

### 4.1 提高超时设置

**文件**: `knowcran/semantic_scholar.py`

```python
# 当前
self._client = client or httpx.Client(timeout=30.0)

# 建议修改为
self._client = client or httpx.Client(
    timeout=httpx.Timeout(
        connect=30.0,    # 连接超时
        read=120.0,      # 读取超时（增加到 2 分钟）
        write=30.0,      # 写入超时
        pool=10.0        # 连接池超时
    )
)
```

### 4.2 增加速率限制

**文件**: `.env` 或 `knowcran/config.py`

```bash
# 当前
KNOWCRAN_RATE_LIMIT_SECONDS=1.1

# 建议修改为
KNOWCRAN_RATE_LIMIT_SECONDS=2.0
```

### 4.3 改进重试策略

**文件**: `knowcran/semantic_scholar.py`

```python
# 当前
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3

# 建议修改为
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 5  # 增加重试次数
_INITIAL_WAIT = 5  # 初始等待时间（秒）
```

### 4.4 添加断点续传

**建议**: 在 discover 命令中添加 `--resume` 选项，支持中断后继续

### 4.5 改进查询去重

**建议**: 在执行查询前，对相似查询进行合并或去重

---

## 五、测试命令记录

### 5.1 安装与初始化

```bash
cd /home/bioshen/Code/Mnemosyne
pip install -e ".[dev]"
knowcran init
```

### 5.2 文献检索命令

```bash
# 基础检索
knowcran discover "intracerebral hemorrhage" --limit 200 --no-llm

# 扩展检索（带引用/参考文献）
knowcran discover "intracerebral hemorrhage" --limit 500 --expand

# 不同主题变体
knowcran discover "ICH stroke" --limit 200 --no-llm
knowcran discover "hemorrhagic stroke" --limit 200 --no-llm
knowcran discover "cerebral hematoma" --limit 200 --no-llm
knowcran discover "hypertensive intracerebral hemorrhage" --limit 200 --no-llm
# ... 更多变体
```

### 5.3 查看统计

```bash
knowcran stats
# 输出:
# Papers:  5261
# Claims:  3393
# Links:   794
```

---

## 六、总结

### 6.1 优点

1. ✅ 安装简单，依赖清晰
2. ✅ 配置灵活，支持环境变量
3. ✅ 有缓存机制，减少重复请求
4. ✅ 错误处理完善，有重试机制
5. ✅ 进度显示清晰
6. ✅ 代码安全性良好

### 6.2 需要改进

1. 🔴 超时设置过短，需要增加
2. 🟡 速率限制需要调整
3. 🟡 查询去重需要改进
4. 🟡 断点续传功能缺失
5. 🟢 错误日志可以更详细

### 6.3 下一步行动

1. **立即**: 轮换 .env 中的 API 密钥
2. **短期**: 修改超时设置和速率限制
3. **中期**: 添加断点续传和查询去重功能
4. **长期**: 考虑使用 Semantic Scholar 的批量 API 提高效率

---

**报告生成时间**: 2026-05-29  
**测试执行者**: MiMo AI Assistant
