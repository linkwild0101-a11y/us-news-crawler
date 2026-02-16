#!/usr/bin/env python3
"""
提取RSS源数据从Markdown文件
支持多种格式：us_military_news_sources_214.md, us_economy_finance_sources_151.md, us_politics_news_sources_100plus.txt
"""

import re
import json
import os
from pathlib import Path


def parse_markdown_table(content, category):
    """解析Markdown表格格式"""
    sources = []
    lines = content.split("\n")

    # 找到表格开始（包含 | Name | 的行）
    table_start = None
    for i, line in enumerate(lines):
        if "| Name " in line and "| RSS URL " in line:
            table_start = i + 2  # 跳过表头和分隔符
            break

    if table_start is None:
        return sources

    # 解析表格行
    for line in lines[table_start:]:
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        if line.startswith("|---"):
            continue

        # 分割单元格
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue

        # 提取字段
        name = cells[0] if len(cells) > 0 else ""
        listing_url = cells[1] if len(cells) > 1 else ""
        rss_url = cells[2] if len(cells) > 2 else ""
        description = cells[3] if len(cells) > 3 else ""
        anti_scraping = cells[4] if len(cells) > 4 else "None"

        # 清理数据
        name = name.strip()
        rss_url = rss_url.strip()

        # 跳过无效数据
        if not name or not rss_url or rss_url == "RSS URL":
            continue
        if not rss_url.startswith("http"):
            continue

        sources.append(
            {
                "name": name,
                "listing_url": listing_url.strip() if listing_url else "",
                "rss_url": rss_url,
                "description": description.strip() if description else "",
                "category": category,
                "anti_scraping": anti_scraping.strip() if anti_scraping else "None",
                "status": "active",
            }
        )

    return sources


def extract_sources():
    """主函数：从所有源文件提取RSS源"""

    base_dir = Path("/Users/nobody1/Documents/US_newslist")
    all_sources = []
    stats = {"military": 0, "economy": 0, "politics": 0}

    # 文件映射
    files_to_parse = [
        ("us_military_news_sources_214.md", "military"),
        ("us_economy_finance_sources_151.md", "economy"),
        ("us_politics_news_sources_100plus.txt", "politics"),
    ]

    for filename, category in files_to_parse:
        filepath = base_dir / filename

        if not filepath.exists():
            print(f"⚠️  文件不存在: {filename}")
            continue

        print(f"📄 正在解析: {filename} ({category})")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            sources = parse_markdown_table(content, category)
            stats[category] = len(sources)
            all_sources.extend(sources)

            print(f"   ✅ 提取了 {len(sources)} 个源")

        except Exception as e:
            print(f"   ❌ 错误: {e}")

    # 去重（基于rss_url）
    seen_urls = set()
    unique_sources = []
    duplicates = 0

    for source in all_sources:
        url = source["rss_url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(source)
        else:
            duplicates += 1

    # 添加ID
    for i, source in enumerate(unique_sources, 1):
        source["id"] = i

    # 保存JSON
    output_file = base_dir / "data" / "sources.json"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(unique_sources, f, indent=2, ensure_ascii=False)

    # 打印统计
    print("\n" + "=" * 60)
    print("📊 提取统计")
    print("=" * 60)
    print(f"军事 (military):    {stats['military']:3d} 个")
    print(f"经济 (economy):     {stats['economy']:3d} 个")
    print(f"政治 (politics):    {stats['politics']:3d} 个")
    print(f"-" * 60)
    print(f"总计:               {len(all_sources):3d} 个")
    print(f"去重后:             {len(unique_sources):3d} 个")
    print(f"重复数:             {duplicates:3d} 个")
    print(f"\n💾 已保存到: {output_file}")

    # 验证JSON
    print(f"\n🔍 验证JSON格式...")
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"✅ JSON格式正确，共 {len(data)} 条记录")

    # 显示前3个示例
    print(f"\n📋 前3个源示例:")
    for source in data[:3]:
        print(f"   [{source['category']}] {source['name']}")
        print(f"       RSS: {source['rss_url'][:60]}...")

    return unique_sources


if __name__ == "__main__":
    extract_sources()
