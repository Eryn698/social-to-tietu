#!/usr/bin/env python3
"""
微信公众号文章提取并转换为 Markdown
使用 Python 版提取器（从 wechat-article-reader-0 集成）
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import requests
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
except ImportError as e:
    print(f"错误: 缺少必要的库: {e}")
    print("请运行: pip install requests beautifulsoup4 lxml markdownify")
    import sys
    sys.exit(1)


class WechatArticleExporter:
    """微信公众号文章导出器（从 wechat-article-reader-0 集成）"""

    def __init__(self, url):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def extract_meta(self, soup):
        """提取文章元数据"""
        meta = {}

        # 提取标题
        title_tag = soup.find('meta', property='og:title')
        meta['title'] = title_tag.get('content', '未知标题') if title_tag else '未知标题'

        # 提取作者
        author_tag = soup.find('meta', property='og:article:author')
        meta['author'] = author_tag.get('content', '未知作者') if author_tag else '未知作者'

        # 提取发布时间
        time_tag = soup.find('meta', property='og:article:published_time')
        meta['publish_time'] = time_tag.get('content', '未知时间') if time_tag else '未知时间'

        # 提取描述
        desc_tag = soup.find('meta', property='og:description')
        meta['description'] = desc_tag.get('content', '') if desc_tag else ''

        # 提取公众号名称
        account_tag = soup.find('meta', property='og:article:author')
        meta['account'] = account_tag.get('content', '') if account_tag else ''

        return meta

    def extract_content(self, soup):
        """提取文章正文内容"""
        # 微信文章的正文通常在 id="js_content" 的div中
        content_div = soup.find('div', id='js_content')
        return content_div

    def convert_to_markdown(self, html_content):
        """将HTML内容转换为Markdown"""
        if not html_content:
            return ""
        markdown_text = md(str(html_content))
        return markdown_text

    def sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        illegal_chars = r'[<>:"/\\|?*]'
        safe_filename = re.sub(illegal_chars, '_', filename)
        safe_filename = re.sub(r'\s+', '_', safe_filename)
        safe_filename = safe_filename.strip('.')
        return safe_filename

    def export(self):
        """导出文章并返回结果"""
        try:
            response = self.session.get(self.url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            return {
                "error": True,
                "message": f"无法下载文章: {e}"
            }

        # 解析HTML
        soup = BeautifulSoup(response.text, 'lxml')

        # 提取元数据
        meta = self.extract_meta(soup)

        # 提取正文内容
        content_div = self.extract_content(soup)

        if not content_div:
            return {
                "error": True,
                "message": "无法找到文章正文内容，可能需要登录或文章已删除"
            }

        # 转换为Markdown
        markdown_content = self.convert_to_markdown(content_div)

        # 构建结果
        result = {
            "title": meta['title'],
            "author": meta['author'],
            "publishTime": meta['publish_time'],
            "description": meta.get('description', ''),
            "cover": "",  # 需要单独从页面提取
            "link": self.url,
            "content": markdown_content,
            "fullMarkdown": self._build_full_markdown(meta, markdown_content)
        }

        return result

    def _build_full_markdown(self, meta, content):
        """构建完整的 Markdown 文档"""
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        full_md = f"""---
title: {meta['title']}
author: {meta['author']}
publish_time: {meta['publish_time']}
source_url: {self.url}
exported_at: {timestamp}
description: {meta.get('description', '')}
---

# {meta['title']}

> 原文链接: {self.url}

**作者**: {meta['author']}
**发布时间**: {meta['publish_time']}

-----

{content}
"""
        return full_md


def extract_to_markdown(url: str, save_path: str = None) -> dict:
    """
    提取微信公众号文章并转换为 Markdown
    
    Args:
        url: 文章链接 (mp.weixin.qq.com)
        save_path: 保存路径（可选，如果提供则保存 Markdown 文件）
    
    Returns:
        dict: 提取结果
            - title: 文章标题
            - author: 作者
            - publishTime: 发布时间
            - description: 摘要
            - cover: 封面图 URL
            - link: 原文链接
            - content: Markdown 内容
            - fullMarkdown: 完整 Markdown 文档（含元数据）
    """
    try:
        exporter = WechatArticleExporter(url)
        result = exporter.export()
        
        if result.get("error"):
            return result
        
        # 如果提供了保存路径，保存 Markdown 文件
        if save_path:
            save_file = Path(save_path)
            save_file.parent.mkdir(parents=True, exist_ok=True)
            save_file.write_text(result['fullMarkdown'], encoding='utf-8')
            result['saved_to'] = str(save_file)
        
        return result
        
    except requests.Timeout:
        return {
            "error": True,
            "message": "提取超时 (30秒)"
        }
    except Exception as e:
        return {
            "error": True,
            "message": f"未知错误: {e}"
        }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="提取微信公众号文章并转换为 Markdown")
    parser.add_argument("url", help="文章链接 (mp.weixin.qq.com)")
    parser.add_argument("-o", "--output", help="保存 Markdown 文件路径（可选）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式（默认输出 Markdown）")
    
    args = parser.parse_args()
    
    result = extract_to_markdown(args.url, args.output)
    
    if result.get("error"):
        print(f"错误: {result['message']}", file=sys.stderr)
        import sys
        sys.exit(1)
    
    # 输出结果
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result['fullMarkdown'])
    
    if args.output:
        print(f"\n✅ 已保存到: {result['saved_to']}", file=sys.stderr)


if __name__ == "__main__":
    main()
