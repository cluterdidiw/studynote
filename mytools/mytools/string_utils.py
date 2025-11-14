def str_reverse(s: str) -> str:
    """反转字符串"""
    return s[::-1]

def str_count(s: str) -> dict:
    """统计字符出现次数"""
    return {c: s.count(c) for c in set(s)}
