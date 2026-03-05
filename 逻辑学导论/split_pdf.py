#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将《逻辑学导论》PDF 拆分为 50 份。
输入目录：/mnt/d/book，输出目录：在 book 下新建子目录。
"""

from pathlib import Path

# 配置
BOOK_DIR = Path("/mnt/d/book")
OUTPUT_SUBDIR = "逻辑学导论_拆分"   # 在 book 下新建的目录名
NUM_PARTS = 50
DEFAULT_PDF_NAME = "逻辑学导论.pdf"  # 若未传入参数则使用此文件名


def _compute_page_ranges(total_pages: int, num_parts: int) -> list[tuple[int, int]]:
    """计算每份的起止页范围 (0-based)，尽量均分。"""
    if total_pages == 0 or num_parts <= 0:
        return []
    base_size, remainder = divmod(total_pages, num_parts)
    ranges = []
    start = 0
    for i in range(num_parts):
        size = base_size + (1 if i < remainder else 0)
        if size == 0:
            continue
        ranges.append((start, start + size))
        start += size
    return ranges


def split_pdf(pdf_path: Path, output_dir: Path, num_parts: int = NUM_PARTS) -> None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise SystemExit(
            "请先安装 PyMuPDF: pip install PyMuPDF\n"
            "若清华源报错，可改用官方源: pip install PyMuPDF -i https://pypi.org/simple"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem  # 用于输出文件名

    with fitz.open(str(pdf_path)) as doc:
        total_pages = len(doc)
        if total_pages == 0:
            raise SystemExit("PDF 无有效页面。")

        page_ranges = _compute_page_ranges(total_pages, num_parts)
        if not page_ranges:
            raise SystemExit("无法拆分：份数需大于 0。")

        for i, (start, end) in enumerate(page_ranges, start=1):
            out_path = output_dir / f"{stem}_第{i:02d}份.pdf"
            with fitz.open() as part:
                part.insert_pdf(doc, from_page=start, to_page=end - 1)
                part.save(str(out_path), garbage=4, deflate=True)
            print(f"已生成: {out_path} (页 {start+1}-{end})")

    print(f"\n共拆分 {len(page_ranges)} 份，输出目录: {output_dir}")


def main() -> None:
    import sys
    pdf_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_NAME
    pdf_path = BOOK_DIR / pdf_name
    output_dir = BOOK_DIR / OUTPUT_SUBDIR

    if not pdf_path.exists():
        print(f"未找到 PDF: {pdf_path}")
        print(f"用法: python {Path(__file__).name} [PDF文件名]")
        print(f"  若不传参数，默认使用: {DEFAULT_PDF_NAME}")
        raise SystemExit(1)

    split_pdf(pdf_path, output_dir, NUM_PARTS)


if __name__ == "__main__":
    main()
