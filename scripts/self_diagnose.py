#!/usr/bin/env python3
"""
self_diagnose.py - 用 aigc-deslop SKILL.md v3.2 的规则检测 markdown / docx 文件。

把 SKILL.md 里的"反 LLM 指纹清单"和"6 维诊断标准"落地成可执行检测，
扫描任意文本输出违规位置、必须项缺失、句长分布与套话密度。

Usage:
    python3 self_diagnose.py SKILL.md
    python3 self_diagnose.py data/case_study.md --verbose
    python3 self_diagnose.py paper.docx --json report.json
    python3 self_diagnose.py SKILL.md --skip-examples   # 跳过反例展示区

Exit code: 0 = 0 violations, 1 = 有违规。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


# ============================================================
# 规则定义（按 SKILL.md v3.2 第 332-369 行）
# ============================================================

# 禁忌项：出现即违规
FORBIDDEN = [
    ("em_dash",         r"——",                       "破折号 ——（Claude 头号指纹）",            "critical"),
    ("semicolon",       r"；",                        "分号 ；",                                "critical"),
    ("zhe_yi_X",        r"这一[一-鿿]",       "这一X 句式",                             "critical"),
    ("zhe_tao_X",       r"这套[一-鿿]",       "这套X 句式",                             "critical"),
    ("na_yi_X",         r"那一[一-鿿]",       "那一X 句式",                             "critical"),
    ("dash_zheng_shi",  r"——\s*这正是",              "—— 这正是 句式",                         "critical"),
    ("dash_ke",         r"——\s*[可但]",              "—— 可/—— 但 句式",                       "critical"),
    ("bei_X_le",        r"被[一-鿿]{1,4}了",  "被X了 被动结构",                         "high"),
    ("qishi",           r"其实",                      "其实（Claude 标志过渡词）",              "medium"),
    ("qiaohao",         r"恰好",                      "恰好（Claude 标志过渡词）",              "medium"),
    ("ganghao",         r"刚好",                      "刚好（Claude 标志过渡词）",              "medium"),
    ("luodao_shang",    r"落到[一-鿿]+上",    "落到X上 句式",                           "medium"),
    ("kang_de_zhu",     r"扛得住",                    "扛得住（伪口语化）",                     "medium"),
    ("zou_tong_le",     r"走通了",                    "走通了（伪口语化）",                     "medium"),
]

# 必删的机器套话（参考 SKILL.md 第 271-289 行）
MACHINE_CLICHES = [
    "首先", "其次", "再次",
    "一方面", "另一方面",
    "综上所述", "总而言之", "由此可见",
    "不仅如此", "与此同时",
    "值得注意的是", "需要指出的是", "必须强调的是", "显而易见",
    "在此基础上", "进一步而言", "从某种意义上讲",
]

# 必须命中的"人味"元素（参考 SKILL.md 第 116-128 行的自检清单）
REQUIRED = [
    {
        "name": "first_person",
        "patterns": [r"我们", r"我[^国文界]"],
        "min_count": 1,
        "desc": "第一人称 我/我们",
    },
    {
        "name": "hedge_words",
        "patterns": [r"比较", r"差不多", r"基本上", r"不太", r"挺"],
        "min_count": 3,
        "desc": "模糊限定词（比较/差不多/基本上/不太/挺）",
    },
    {
        "name": "oral_transitions",
        "patterns": [r"也就是说", r"换句话说", r"说白了", r"比如说"],
        "min_count": 1,
        "desc": "口语化过渡（也就是说/换句话说/比如说）",
    },
]


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Violation:
    line: int
    col: int
    rule: str
    desc: str
    severity: str
    snippet: str


@dataclass
class Report:
    file: str
    char_count: int = 0
    violations: list = field(default_factory=list)
    required_missing: list = field(default_factory=list)
    machine_cliche_count: int = 0
    machine_cliche_per_kchar: float = 0.0
    sentence_stats: dict = field(default_factory=dict)
    skip_examples: bool = False

    @property
    def total_violations(self) -> int:
        return len(self.violations) + len(self.required_missing)


# ============================================================
# 文件读取
# ============================================================

def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
        except ImportError:
            sys.exit("缺依赖：pip install python-docx")
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    return path.read_text(encoding="utf-8")


def mask_examples(text: str) -> str:
    """把代码块、行内代码、引用块、显式标记区用空格替换，保留行号，避免反例区误报。

    显式标记格式（用于教学性反例展示，作者主动声明跳过）：
        <!-- diagnose-skip-start -->
        ...
        <!-- diagnose-skip-end -->
    """
    def keep_lines(match):
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"```.*?```", keep_lines, text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", keep_lines, text)
    text = re.sub(r"^>.*$", keep_lines, text, flags=re.MULTILINE)
    text = re.sub(
        r"<!--\s*diagnose-skip-start\s*-->.*?<!--\s*diagnose-skip-end\s*-->",
        keep_lines, text, flags=re.DOTALL,
    )
    return text


# ============================================================
# 检测器
# ============================================================

def pos_to_line_col(text: str, pos: int):
    line = text.count("\n", 0, pos) + 1
    last_nl = text.rfind("\n", 0, pos)
    col = pos - last_nl if last_nl >= 0 else pos + 1
    return line, col


def scan_forbidden(text: str, all_lines: list) -> list:
    found = []
    for rule, pattern, desc, severity in FORBIDDEN:
        for m in re.finditer(pattern, text):
            line, col = pos_to_line_col(text, m.start())
            raw = all_lines[line - 1] if line <= len(all_lines) else ""
            snippet = raw.strip()
            if len(snippet) > 80:
                snippet = snippet[:80] + "..."
            found.append(Violation(line, col, rule, desc, severity, snippet))
    return found


def scan_three_part_parallel(text: str, all_lines: list) -> list:
    """三项排比：连续三个 2-6 字中文短语用顿号或逗号分隔。"""
    pattern = re.compile(
        r"([一-鿿]{2,6})[、，]"
        r"([一-鿿]{2,6})[、，]"
        r"([一-鿿]{2,6})[，。]"
    )
    found = []
    for m in pattern.finditer(text):
        line, col = pos_to_line_col(text, m.start())
        snippet = f"{m.group(1)}、{m.group(2)}、{m.group(3)}"
        found.append(Violation(
            line, col, "three_part_parallel",
            "三项排比 X、Y、Z", "high", snippet,
        ))
    return found


def check_required(text: str) -> list:
    missing = []
    for rule in REQUIRED:
        total = sum(len(re.findall(p, text)) for p in rule["patterns"])
        if total < rule["min_count"]:
            missing.append({
                "rule": rule["name"],
                "desc": rule["desc"],
                "expected_min": rule["min_count"],
                "actual": total,
            })
    return missing


def count_cliches(text: str) -> int:
    return sum(len(re.findall(re.escape(c), text)) for c in MACHINE_CLICHES)


def analyze_sentence_length(text: str) -> dict:
    """按段落（双空行分隔）计算句长标准差。"""
    paragraphs = [p for p in text.split("\n\n") if len(p.strip()) > 50]
    para_stats = []
    for para in paragraphs:
        sentences = re.split(r"[。！？]", para)
        lengths = [len(s.strip()) for s in sentences if 3 < len(s.strip()) < 200]
        if len(lengths) < 3:
            continue
        std = statistics.stdev(lengths)
        para_stats.append({
            "preview": para.strip()[:30].replace("\n", " "),
            "sentence_count": len(lengths),
            "min_len": min(lengths),
            "max_len": max(lengths),
            "std": round(std, 2),
            "unhealthy": std < 6,
        })
    if not para_stats:
        return {"total_paragraphs": 0, "unhealthy_paragraphs": 0, "unhealthy_ratio": 0.0, "details": []}
    unhealthy = sum(1 for p in para_stats if p["unhealthy"])
    return {
        "total_paragraphs": len(para_stats),
        "unhealthy_paragraphs": unhealthy,
        "unhealthy_ratio": round(unhealthy / len(para_stats), 2),
        "details": para_stats,
    }


# ============================================================
# 主流程
# ============================================================

def diagnose(path: Path, skip_examples: bool = False) -> Report:
    raw = read_text(path)
    scan_text = mask_examples(raw) if skip_examples else raw
    lines = raw.split("\n")

    report = Report(file=str(path), skip_examples=skip_examples)
    report.char_count = len(raw)
    report.violations.extend(scan_forbidden(scan_text, lines))
    report.violations.extend(scan_three_part_parallel(scan_text, lines))
    report.required_missing = check_required(raw)
    report.machine_cliche_count = count_cliches(scan_text)
    report.machine_cliche_per_kchar = round(
        report.machine_cliche_count / max(1, report.char_count / 1000), 2,
    )
    report.sentence_stats = analyze_sentence_length(raw)
    return report


# ============================================================
# 输出
# ============================================================

def print_report(r: Report, verbose: bool = False) -> None:
    print()
    print("=" * 72)
    print(f"  AIGC Self-Diagnose Report  (SKILL.md v3.2 ruleset)")
    print(f"  File: {r.file}")
    if r.skip_examples:
        print("  Mode: --skip-examples (代码块/引用块已忽略)")
    print("=" * 72)
    print()

    print(f"  文件长度       {r.char_count} 字符")
    print(f"  违禁项         {len(r.violations)} 处")
    print(f"  必须项缺失     {len(r.required_missing)} 项")
    print(f"  机器套话密度   {r.machine_cliche_per_kchar} 处/千字  (目标 ≤2)")
    print()

    if r.violations:
        by_rule = {}
        for v in r.violations:
            by_rule.setdefault(v.rule, []).append(v)
        print("  违禁项分布")
        order = sorted(by_rule.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        for rule, vs in order:
            sev = vs[0].severity
            tag = {"critical": "X", "high": "!", "medium": "·"}.get(sev, " ")
            print(f"    [{tag}] {vs[0].desc:<40} {len(vs)} 处")
        print()

    if r.required_missing:
        print("  必须命中项缺失")
        for m in r.required_missing:
            print(f"    · {m['desc']}: 需要 >={m['expected_min']}, 实际 {m['actual']}")
        print()

    ss = r.sentence_stats
    if ss and ss["total_paragraphs"] > 0:
        print(f"  句长方差分析")
        print(f"    段落总数 {ss['total_paragraphs']}, "
              f"方差不健康段 {ss['unhealthy_paragraphs']} "
              f"({int(ss['unhealthy_ratio']*100)}%)")
        if verbose and ss["details"]:
            print()
            print("    样本（前 8 段）")
            for d in ss["details"][:8]:
                flag = "X" if d["unhealthy"] else "v"
                print(f"      [{flag}] std={d['std']:>5} "
                      f"range={d['min_len']:>3}-{d['max_len']:>3}  「{d['preview']}」")
        print()

    if verbose and r.violations:
        print("  违规位置详情（前 30 条）")
        for v in r.violations[:30]:
            print(f"    {r.file}:{v.line}:{v.col}  [{v.rule}]  {v.snippet}")
        if len(r.violations) > 30:
            print(f"    ... 共 {len(r.violations)} 条，--json 看完整列表")
        print()

    print("=" * 72)
    if r.total_violations == 0:
        print("  PASS - 0 violations. 本文件符合 aigc-deslop SKILL.md v3.2 标准。")
    else:
        forbidden_n = len(r.violations)
        missing_n = len(r.required_missing)
        print(f"  FAIL - {r.total_violations} violations "
              f"({forbidden_n} 违禁 + {missing_n} 必须项缺失)")
    print("=" * 72)
    print()


def main():
    p = argparse.ArgumentParser(
        description="AIGC Self-Diagnose - 用 aigc-deslop 规则检测 markdown/docx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("file", help="待检测的 markdown 或 docx 文件")
    p.add_argument("--verbose", "-v", action="store_true", help="显示违规位置详情")
    p.add_argument("--json", metavar="PATH", help="输出完整 JSON 报告到指定路径")
    p.add_argument("--skip-examples", action="store_true",
                   help="跳过代码块和引用块（避免反例展示误报）")
    args = p.parse_args()

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"文件不存在：{args.file}")

    report = diagnose(path, skip_examples=args.skip_examples)
    print_report(report, verbose=args.verbose)

    if args.json:
        Path(args.json).write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON 报告：{args.json}\n")

    sys.exit(0 if report.total_violations == 0 else 1)


if __name__ == "__main__":
    main()
