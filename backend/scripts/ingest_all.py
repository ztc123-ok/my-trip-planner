# -*- coding: utf-8 -*-
"""一键将 backend/data/knowledge_base/attractions 下的所有 Markdown 攻略导入 Qdrant。"""

import os
import sys

# 统一 Windows 控制台编码
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

# 添加根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.knowledge_service import get_knowledge_service


def main():
    print("🚀 开始批量导入各城市热门景点攻略至 Qdrant 向量库...")
    kb_dir = os.path.join(backend_dir, "data", "knowledge_base", "attractions")
    if not os.path.exists(kb_dir):
        print(f"❌ 目录不存在: {kb_dir}")
        return

    ks = get_knowledge_service()
    results = ks.ingest_all_attractions(kb_dir)

    total_chunks = 0
    print("\n--- 导入明细 ---")
    for filename, count in results.items():
        if isinstance(count, int):
            print(f"  📄 {filename:<20} -> 写入 {count} 个切片")
            total_chunks += count
        else:
            print(f"  ❌ {filename:<20} -> 错误: {count}")

    print(
        f"\n🎉 批量导入完成！共处理 {len(results)} 个城市文件，累计写入 {total_chunks} 个高质量向量切片！"
    )


if __name__ == "__main__":
    main()
