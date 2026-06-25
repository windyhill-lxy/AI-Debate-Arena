"""
辩论资料文件夹 DOCX 批量导入脚本。
将 辩论资料/ 目录下的 .docx 文件提取文本并入库到 RAG 向量存储。

使用方法:
    python scripts/import_debate_materials.py [--folder 辩论资料] [--debate-id shared]

依赖:
    pip install python-docx
    （已在 tools/python 中可用，或通过 bootstrap.bat 安装）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保 backend 可 import
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))


def extract_docx_text(path: Path) -> str:
    try:
        from docx import Document  # type: ignore
    except ImportError:
        print("  [错误] 请先安装 python-docx: pip install python-docx")
        return ""
    try:
        doc = Document(str(path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        print(f"  [错误] 读取 {path.name} 失败: {e}")
        return ""


def import_folder(folder: Path, debate_id: str) -> None:
    from app.services.vector_store import add_document  # type: ignore

    docx_files = sorted(folder.glob("*.docx"))
    if not docx_files:
        print(f"[提示] {folder} 中未找到 .docx 文件。")
        return

    print(f"[开始] 共发现 {len(docx_files)} 个文件，目标 debate_id={debate_id!r}")
    success = 0
    for f in docx_files:
        print(f"  处理: {f.name} ...", end=" ", flush=True)
        text = extract_docx_text(f)
        if not text:
            print("跳过（无内容）")
            continue
        title = f.stem
        try:
            add_document(
                debate_id=debate_id,
                title=title,
                content=text,
                source_file=str(f),
            )
            print(f"OK（{len(text)} 字）")
            success += 1
        except Exception as e:
            print(f"[错误] {e}")

    print(f"[完成] 成功导入 {success}/{len(docx_files)} 个文件。")


def main() -> None:
    parser = argparse.ArgumentParser(description="将辩论资料 DOCX 导入 RAG 向量存储")
    parser.add_argument(
        "--folder",
        default=str(_REPO_ROOT / "辩论资料"),
        help="辩论资料文件夹路径（默认：项目根目录下的 辩论资料/）",
    )
    parser.add_argument(
        "--debate-id",
        default="shared",
        help="关联的 debate_id，用于 RAG 检索范围（默认：shared）",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"[错误] 文件夹不存在: {folder}")
        sys.exit(1)

    import asyncio
    import os

    # 加载 .env
    env_file = _REPO_ROOT / ".env"
    if env_file.exists():
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(str(env_file))

    import_folder(folder, args.debate_id)


if __name__ == "__main__":
    main()
