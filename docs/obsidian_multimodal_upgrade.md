# Mnemosyne / KnowCran 多模态 Obsidian 导出与跑批稳定性升级说明

为了增强本地知识库的学术可视化能力，并保障大样本量（如 1000+ 文献、500+ PDF）跑批的稳定性，我们在近期对系统进行了深度重构与升级。

本篇文档详细记录了本次源码级别的改动、使用方法及核心设计意图。

---

## 一、 核心升级特性

### 1. Obsidian 笔记卡片原图渲染（双链 + 多模态图表可视化）
* **原有痛点**：PDF 里的插图（Figures）和表格（Tables）被 MinerU 裁剪出来并存储在数据盘中，但在导出的 Obsidian 笔记中，用户只能看到纯文本分析，无法对照查看原图，多模态识别失去了直观的校验意义。
* **升级方案**：我们重构了 `knowcran/obsidian.py` 的导出代码，建立 **文献卡片笔记 ↔ 裁剪原图** 的相对路径关联。
* **生成效果**：
  在导出的 Obsidian 每一篇文献卡片（在 `papers/` 文件夹下）中，新增了 **`## Figures and Tables`** 章节：
  * **直观图表展示**：使用相对路径语法直接渲染 MinerU 截取的 PDF 图表：
    `![Table 1](../../data/runtime/media/文献ID/图片名.png)`
  * **原图注释对照**：原图下方紧跟原文献中该图表的 `Caption` 注释。
  * **VLM 视觉解读**：内嵌 mimo-v2-omni 大模型对图片的视觉详细解析（以 Obsidian Callout 形式呈现）：
    ```markdown
    > [!info] Vision VLM Interpretation
    > Based on the image provided, here is a detailed description...
    ```
  * **表格 Markdown 还原**：如果是 Table 类媒体资产，还将额外附带由 Vision API 识别并转化的纯 Markdown 表格排版，方便复制数据。

### 2. 跑批稳定性提升：大文件解析超时配置 (`MNEMOSYNE_MINERU_TIMEOUT_SECONDS`)
* **原有痛点**：对于页数极多、包含大量图表的复杂学术 PDF，MinerU 在进行高级版面提取和裁剪图表时往往需要消耗大量 CPU 时间。原系统硬编码了 180 秒的 HTTP 超时，容易导致跑批队列中的大文件解析频繁报错并退回 PyMuPDF（导致缺失图表资产）。
* **升级方案**：
  * 在 `knowcran/config.py` 中引入了 `mineru_timeout_seconds` 参数，支持通过 `.env` 中的环境变量 `MNEMOSYNE_MINERU_TIMEOUT_SECONDS` 进行动态配置（推荐调大至 `300` 秒或 `500` 秒）。
  * 将 `knowcran/parsers/mineru.py` 中的 httpx 同步请求超时时间修改为该配置项。

### 3. 多模态 RAG 与 VLM 自动重试与故障隔离 (`knowcran/vision/`)
* **原有痛点**：大规模提取和问答时，调用 mimo 多模态接口如果频繁遇到 429（Too Many Requests）或网络波动，会导致整批提取队列阻塞或终止。且在多模态 RAG 问答中，直接传递本地绝对路径 `file://` 会导致外部 LLM API 无法解析。
* **升级方案**：
  * **自动健康降级** (`knowcran/vision/router.py`)：为 `VisionRouter` 增加了 `chat()` 入口，并在接口层捕获异常，遇到错误自动将当前提供商标记为 `unhealthy` 并**无缝降级**切换到备份 Vision Provider，在运行结束后重置。
  * **图片 Base64 编码** (`knowcran/rag/prompts.py`)：将 `format_multimodal_prompt` 中的绝对路径引用修改为动态 Base64 编码流（以 `data:image/png;base64,...` 的 Data URL 形式），确保远程大模型能顺利读取本地图片。

### 4. 跑批上限控制与防止上下文溢出 (`knowcran/workflow.py`)
* **升级方案**：在 `workflow.py` 的 review 合成步骤中，将文献综述生成的文献数量限制修改为 `max_review_papers = min(100, limit)`。
* **设计意图**：允许您配置最大 limit 提取 1500 篇文献，但最终由大模型撰写 Obsidian 综述时只选取相关度最高的前 100 篇，防止因为一次性输入上千篇文献导致大模型发生上下文溢出（Context Window Overflow）或者触发高额 Token 账单。

---

## 二、 升级文件列表与变动详情

以下是本次更新涉及的文件及修改明细：

| 文件路径 | 变动说明 |
| :--- | :--- |
| `knowcran/config.py` | 增加 `mineru_timeout_seconds` 环境变量读取。 |
| `knowcran/parsers/mineru.py` | 在 httpx 请求中使用配置的超时时限，增强 MinerU 稳定性。 |
| `knowcran/obsidian.py` | 支持 media_assets 相对路径图片导出、VLM 解读渲染和 Markdown 表格追加。 |
| `knowcran/storage.py` | 在 `delete_parsed_content_for_paper` 中增加了对多模态表的级联删除，防止重复解析主键冲突；增加 `update_media_table_extraction` 支持保存提取出的 markdown 表格。 |
| `knowcran/workflow.py` | 将 Obsidian 综述生成的最大学术文献引用上限限制在 100 篇，防上下文溢出。 |
| `knowcran/vision/router.py` | 新增 `chat()` 并实现 Vision Provider 限流故障自动容错隔离。 |
| `knowcran/vision/provider.py` | 支持调用 OpenAI 兼容的 chat 接口，并提供异常捕获健康标记。 |
| `knowcran/rag/prompts.py` | 多模态 RAG 问答时图片改用 Base64 二进制流传输。 |
| `knowcran/discovery.py` | 修复 `_agent_rerank` 评分哈希生成时，若返回为空可能抛出 Key/Attribute 异常的逻辑漏洞。 |
| `tests/` | 增加各多模态服务降级、级联删除与 Base64 转换单元测试。 |

---

## 三、 使用与部署指南

### 1. 配置超时时限
若在进行 1000+ 文献跑批时，为了避免复杂文献解析超时，请在您的 `.env` 文件中追加：
```env
# 调大 MinerU 容器解析请求的超时阈值（单位：秒，默认 180s，推荐 300s）
MNEMOSYNE_MINERU_TIMEOUT_SECONDS=300
```

### 2. 导出 Obsidian 笔记并查阅图片
对于已经跑批完成的主题（例如 `pancreatic_cancer`），可以在本地或服务器上执行：
```bash
knowcran export-obsidian "pancreatic cancer" --data-dir projects/pancreatic_cancer/data --vault-dir projects/pancreatic_cancer/vault
```
* **如何查阅图片**：在 Obsidian 中打开 `projects/pancreatic_cancer/vault` 文件夹。双击打开任意文献笔记卡片（在 `papers/` 目录下），即可在 `Figures and Tables` 小节中直接对照渲染原图。
