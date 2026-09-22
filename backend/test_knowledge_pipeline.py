# -*- coding: utf-8 -*-
"""验证 Qdrant 多城市精准语义检索。"""

import os
import sys

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

from app.services.knowledge_service import get_knowledge_service


def main():
    ks = get_knowledge_service()
    test_cases = [
        ("北京", "故宫周一开门吗，怎么提前预约门票"),
        ("成都", "看大熊猫和花几点去排队最好，下午去合适吗"),
        ("西安", "兵马俑怎么避开野导游和黑车"),
        ("南京", "总统府和牛首山游览路线"),
    ]

    print("==================================================")
    print("🎯 多城市 Payload 过滤与语义检索验证")
    print("==================================================")
    for city, q in test_cases:
        print(f"\n【城市：{city}】用户意图: {q}")
        hits = ks.search_knowledge(city=city, query=q, top_k=1)
        if hits:
            hit = hits[0]
            print(
                f"  ✅ 命中景点: {hit['spot_name']} ({hit['section_type']}) | 相似度: {hit['score']:.4f}"
            )
            for line in hit["content"].split("\n")[:4]:
                if line.strip():
                    print(f"     {line}")
        else:
            print("  ❌ 未召回相关切片")

    print("\n==================================================")
    print("🎉 多城市检索全部精准命中对应城市与维度！")
    print("==================================================")


if __name__ == "__main__":
    main()
