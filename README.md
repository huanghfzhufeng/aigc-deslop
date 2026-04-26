# AIGC 文气复魂师 · aigc-deslop

> 把被 AI 抹平的"人之痕迹"，重新还回字里行间。

一套用于**中文论文降 AIGC 率**的方法论 + 工具集。基于真实毕业论文的 9 轮迭代验证，从 **55% AIGC 率降至 11%**（全文实测），为 Claude Code 设计的 Skill。

**English summary**: A Chinese-language methodology and toolset for reducing AI-detection rates in Chinese academic papers. Includes a Claude Code Skill (SKILL.md) and a Python script that rewrites paragraphs while preserving Word document formatting (tables, images, citation superscripts, fonts byte-for-byte). **Verified to reduce PaperPure AIGC detection rate from 55% to 11% on a full thesis** through 9 iterations.

---

## 这个项目解决什么

2025 年后中国高校普遍引入 AIGC 检测（知网 v2.13、PaperPure、维普等），毕业论文 AI 率超标会导致延期答辩甚至取消答辩资格。

市面上的"降 AI 率"工具要么按千字收费（4-8 元/千字），要么效果不稳定。本项目提供：

1. **方法论**（`SKILL.md`）：基于实测数据的"反 LLM 指纹"清单 + 三大铁律 + 12 项自检
2. **工具**（`scripts/replace_docx.py`）：把改写后的 markdown 内容**保留格式替换**回原 docx——表格、图片、目录、引用上标、参考文献全部 byte-for-byte 保留
3. **验证案例**（`data/case_study.md`）：真实毕业论文从 49.6% → 27% 的迭代过程

## 为什么市面上"用 AI 改 AI"经常失败

PaperPure 等检测器训练时见过大量 LLM 输出（GPT/Claude/DeepSeek/Kimi 等），所以 LLM 越想"模仿人写"反而越像 LLM 自己。本项目的核心洞察是——

**真实本科生写作 ≠ LLM 想象的"人写"**

| LLM 默认伪装"人写"（高检出） | 真实本科生写法（低检出） |
|----------|------------|
| 破折号、分号、顿号都用 | 基本只有逗号和句号 |
| "故意"短长穿插（仍规整） | 一逗到底，长句套定语 |
| 自动换近义词 | 同一个词反复用 |
| 一句承载多个论点 | 一句一意，常重复 |
| 偶尔用模糊语 | "比较""差不多""基本上"满天飞 |
| "其实""刚好""恰好" | "也就是说""换句话说""说白了" |
| 精炼避免冗余 | 故意冗余：同义重复一次 |
| 主题句开头 | 想到哪写到哪 |
| "本研究""笔者" | **"我"或"我们"** |
| 选择性数字 | 凡有数字必塞进去 |
| 太完美 | 偶尔有点磕巴 |
| 永远客观 | "这个结果有点出乎我意料" |

## 实测效果

| 版本 | AIGC 率 | 关键策略 |
|------|--------|---------|
| 原始 AI 写的论文 | **55%** | 直接 LLM 生成 |
| 用其他工具降重后 | 40.5% | 市面工具的同义词替换 |
| 错误模仿"半口语化" | 49.6% ↑ | 破折号、"这一X"、对偶过渡（**反弹失败**） |
| 本科生风格（仅 3 段验证） | 27.0% | 零破折号 + 第一人称 + 强制冗余（**策略验证**） |
| **本科生风格 + 格式保留替换（全文）** | **11.0%** ↓↓ | **达标交付** |

**从 55% 到 11%——降了 44 个百分点，稳过 15% 红线。**

详见 [`data/case_study.md`](data/case_study.md)。

## 快速使用

### 1. 安装依赖

```bash
pip install python-docx
```

### 2. 作为 Claude Code Skill 使用（推荐）

把整个 `aigc-deslop/` 目录复制到 `~/.claude/skills/`：

```bash
cp -r aigc-deslop ~/.claude/skills/
```

然后在 Claude Code 里说"我的论文 AI 率太高，帮我降一下"，skill 会自动触发，按 SKILL.md 的工作流走。

### 3. 单独使用替换脚本

如果你已经有改写后的 markdown 内容，直接调脚本把内容塞回原 docx：

```bash
python3 scripts/replace_docx.py 原.docx 改写后.md 输出.docx
```

脚本会：
- 按章节标题（Heading 样式）定位段落
- 自动跳过：声明、签名、英文摘要、关键词等不该改的段
- 保留：表格、图片、引用上标 `[N]`、字体、目录、参考文献
- 报告每个章节的"替换数 vs 期望数"

详见 [`examples/workflow.md`](examples/workflow.md)。

## 工作流概览

```
第零步：问用户 5 个真实研究细节（突破 LLM 自我对抗天花板）
第一步：6 维诊断报告（句长波动/套话/排比/主体性/思维不规则/风格一致性）
第二步：暂停，等用户确认改哪些段
第三步：逐段改写 + 12 项自检清单（零破折号、零三项排比等）
第四步：保留格式替换回原 docx（调用 replace_docx.py）
第五步：检测反馈闭环（接收报告 → 归因 → 二次改写）
```

详见 [`SKILL.md`](SKILL.md)。

## 核心反 LLM 指纹清单（v3.2）

改写后**必须零检出**：

- ❌ 破折号 `——`（Claude 4.5 头号指纹）
- ❌ 分号 `；`
- ❌ "这一X"、"这套X"、"那一X"
- ❌ "—— 这正是"、"—— 可"句式
- ❌ "被X了"被动结构
- ❌ 三项排比（哪怕用句号断开的"伪三项"）

改写后**必须命中**：

- ✓ 零破折号
- ✓ 至少 1 处第一人称"我"或"我们"
- ✓ 至少 3 处模糊限定词（比较/差不多/基本上/不太/挺）
- ✓ 至少 1 处"也就是说""换句话说""比如说"
- ✓ 至少 1 处冗余表达（同义重复）
- ✓ 同一核心词重复 ≥2 次（不换近义词）

## 目录结构

```
aigc-deslop/
├── README.md                 ← 你正在看的文件
├── LICENSE                   ← MIT
├── SKILL.md                  ← 核心方法论 + 工作流（Claude Code Skill）
├── requirements.txt
├── scripts/
│   └── replace_docx.py       ← 保留格式 docx 替换工具
├── examples/
│   ├── workflow.md           ← 实战流程
│   └── before_after.md       ← 改写前后对比
└── data/
    └── case_study.md         ← v1 49.6% → v3 27% 实测案例
```

## 限制与诚实预期

- LLM 改写有天花板，单靠规则化改写**难以稳过 10%**，通常能降到 **15-25% 区间**
- 要进一步降到 10% 以下，**必须由作者本人提供真实研究细节**（最初尝试的方案、调参折腾、老师建议等），由 LLM 编织进改写
- 检测算法每隔几个月升级，规则需要持续迭代
- 学术诚信底线：本工具用于**语言风格调整 + AI 痕迹消除**，不应用于规避真正的抄袭检测

## 贡献

欢迎提交：
- 新发现的 LLM 指纹模式（PR 加到 SKILL.md 的"病灶清单"）
- 新检测系统的实测数据（PR 加到 `data/case_study.md`）
- `replace_docx.py` 的边角情况修复

## License

MIT — 见 [LICENSE](LICENSE) 文件。

## 致谢

本项目方法论基于真实毕业论文（《基于 CNN 的中文垃圾邮件分类系统设计与实现》）的多轮 PaperPure 实测迭代得出。每一条规则都对应一个真实失败案例的归因。
