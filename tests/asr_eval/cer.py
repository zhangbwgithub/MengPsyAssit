"""纯标准库 CER（字符错误率）计算模块。

CER = edit_distance(ref, hyp) / max(len(ref), 1)
- 中文按字符计算，去除空白和中英文标点后比较
- 支持中英混合文本
"""

from __future__ import annotations

import re
import string
import sys

# ── 中英文标点集合 ──────────────────────────────────────────────
_CJK_PUNCT = "，。！？、；：""''（）【】《》—…～·"
_ALL_PUNCT = set(string.punctuation) | set(_CJK_PUNCT)

# 用于去除所有标点和空白的正则
_PUNCT_OR_SPACE_RE = re.compile(
    "[" + re.escape("".join(sorted(_ALL_PUNCT))) + r"\s]+"
)


def normalize(s: str) -> str:
    """去除所有标点符号和空白，返回规范化的纯文本。"""
    return _PUNCT_OR_SPACE_RE.sub("", s)


def _levenshtein(a: str, b: str) -> int:
    """计算两个字符串的 Levenshtein 编辑距离（纯 Python，O(mn) 空间可优化）。"""
    n, m = len(a), len(b)
    # 优化：只用两行
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    curr = [0] * (m + 1)
    for i in range(1, n + 1):
        curr[0] = i
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,      # 删除
                curr[j - 1] + 1,  # 插入
                prev[j - 1] + cost,  # 替换
            )
        prev, curr = curr, prev
    return prev[m]


def cer(ref: str, hyp: str) -> float:
    """计算字符错误率。

    Args:
        ref: 参考文本（黄金标准）
        hyp: 假设文本（ASR 输出）

    Returns:
        CER 值，范围 [0, +inf)；hyp 为空字符串时返回 1.0（如果 ref 非空）。
    """
    r = normalize(ref)
    h = normalize(hyp)
    if len(r) == 0 and len(h) == 0:
        return 0.0
    dist = _levenshtein(r, h)
    return dist / max(len(r), 1)


# ── 自检 ────────────────────────────────────────────────────────
def _selftest() -> None:
    """运行至少 5 条断言自检。"""
    passed = 0
    failed = 0

    def check(desc: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✓ {desc}")
        else:
            failed += 1
            print(f"  ✗ {desc}", file=sys.stderr)

    print("cer.py 自检开始...\n")

    # 1. 完全一致 → CER = 0
    check(
        "完全一致 → CER == 0",
        cer("你好，请坐。这一周过得怎么样？", "你好，请坐。这一周过得怎么样？") == 0.0,
    )

    # 2. 完全不同 → CER > 0
    check(
        "完全不同 → CER > 0",
        cer("你好世界", "再见天地") > 0,
    )

    # 3. 空 hyp（有 ref）→ CER == 1.0
    check(
        "空 hyp → CER == 1.0",
        cer("你好世界", "") == 1.0,
    )

    # 4. 含标点归一：去掉标点后一致 → CER == 0
    check(
        "含标点归一化后一致 → CER == 0",
        cer("你好，世界！", "你好世界") == 0.0,
    )

    # 5. 中英混合
    check(
        "中英混合 'Hello 你好' vs 'Hello 你好' → CER == 0",
        cer("Hello 你好", "Hello 你好") == 0.0,
    )

    # 6. normalize 函数验证
    check(
        "normalize('  你 好 ，世 界！ ') == '你好世界'",
        normalize("  你 好 ，世 界！ ") == "你好世界",
    )

    # 7. 两个都为空 → CER == 0
    check(
        "双空 → CER == 0",
        cer("", "") == 0.0,
    )

    print(f"\n自检完成：{passed} 通过，{failed} 失败")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    _selftest()
