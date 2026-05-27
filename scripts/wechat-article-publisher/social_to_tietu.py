#!/usr/bin/env python3
"""
从抖音/小红书图文链接 → 解析 → 下载图片 → 上传微信 → 创建贴图(newspic)类型草稿

完整流程：
1. 调用 api.bugpk.com 解析链接获取图片
2. 下载所有图片到本地（自动转JPG）
3. 批量上传到微信公众号获取永久素材 media_id
4. 创建 newspic 类型草稿（贴图）

用法：
    python social_to_tietu.py --url "抖音/小红书链接" --account "umi花艺"
    python social_to_tietu.py --url "https://xxx" --app_id wx6ed183dfc5eb7a7e --app_secret xxx
"""

import os
import sys
import json
import argparse
import requests
import re
import time
import io

# ====== GBK安全输出（subprocess调用时PYTHONUTF8=1已由调用方设置）======
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# 公众号配置映射
ACCOUNTS = {
    'umi花艺': {
        'app_id': 'wx6ed183dfc5eb7a7e',
        'app_secret': '2efa3a7242deb7c4a877409f796ccad2'
    },
    '潮宠社': {
        'app_id': 'wx6f3ed39c0b34bae2',
        'app_secret': '558f97e523b40c7a85c7d8c6212258f4'
    }
}

# 解析API配置（统一使用 short_videos 接口）
PARSE_API = 'https://api.bugpk.com/api/short_videos'


def get_access_token(app_id, app_secret):
    """获取微信公众号access_token"""
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    if data.get('errcode', 0) != 0:
        raise Exception(f"获取token失败[{data.get('errcode')}]: {data.get('errmsg')}")
    return data['access_token']


def resolve_short_url(url):
    """解析短链接，返回真实URL"""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        return resp.url or url
    except:
        return url


def parse_url(url):
    """
    解析抖音/小红书链接，返回 {title, desc, images: [], author}
    
    支持的平台：
    - 小红书：xhs.com / xiaohongshu.com
    - 抖音：douyin.com / v.douyin.com
    """
    # 先解析短链接
    url = resolve_short_url(url)
    
    # 判断平台
    if any(d in url for d in ['xhs.com', 'xiaohongshu.com']):
        platform = 'xhs'
    elif any(d in url for d in ['douyin.com', 'v.douyin.com']):
        platform = 'douyin'
    else:
        raise Exception(f"不支持的平台，URL需要包含 xhs/douyin 关键字")

    print(f"[1/4] 正在解析{platform}链接...")
    
    # 统一使用 short_videos 接口
    params = {'url': url}
    try:
        resp = requests.get(PARSE_API, params=params, timeout=30)
    except requests.exceptions.SSLError:
        time.sleep(2)
        resp = requests.get(PARSE_API, params=params, timeout=30, verify=False)

    data = resp.json()
    if data.get('code') != 200:
        raise Exception(f"解析失败: {data.get('msg', data)}")

    result = data.get('data', {})
    title = result.get('title', '无标题')
    images = result.get('images', [])
    author_info = result.get('author', {})
    author = author_info.get('name', '') or author_info.get('nickname', '') or ''
    desc = result.get('desc', '')

    if not images:
        raise Exception("解析结果中没有图片，可能该笔记已删除或无权限访问")

    print(f"  标题: {title}")
    print(f"  作者: {author}")
    print(f"  图片数: {len(images)}张")
    
    return {
        'title': title,
        'desc': desc,
        'images': images,
        'author': author,
        'platform': platform
    }


def download_images(images, output_dir):
    """
    下载图片列表到本地目录，自动转JPG
    
    Args:
        images: URL列表
        output_dir: 输出目录
        
    Returns:
        list: 本地文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)
    local_files = []
    
    print(f"\n[2/4] 下载{len(images)}张图片...")
    
    for i, img_url in enumerate(images):
        ext = '.jpg'  # 统一转JPG
        local_path = os.path.join(output_dir, f"img_{i+1:02d}{ext}")
        
        # 下载重试：最多3次，超时逐步加大
        downloaded = False
        for attempt in range(3):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.xiaohongshu.com/',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                }
                
                # 超时逐步加大：30s → 60s → 90s
                timeout = 30 * (attempt + 1)
                raw_resp = requests.get(img_url, headers=headers, timeout=timeout, stream=True)
                
                if raw_resp.status_code == 403:
                    import urllib.request
                    req = urllib.request.Request(img_url, headers={
                        'User-Agent': headers['User-Agent'],
                        'Referer': 'https://www.xiaohongshu.com/explore',
                    })
                    with urllib.request.urlopen(req, timeout=30) as urlopen_resp:
                        raw_content = urlopen_resp.read()
                    from io import BytesIO
                    raw_resp._content = raw_content
                    raw_resp.status_code = 200
                    raw_resp.headers['Content-Type'] = 'image/jpeg'
                else:
                    raw_resp.raise_for_status()
            
                content_type = raw_resp.headers.get('Content-Type', '')
                
                # 如果是webp格式，尝试用PIL转换
                if 'webp' in content_type or img_url.lower().endswith('.webp'):
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(raw_resp.content))
                    if img.mode == 'RGBA':
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3])
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(local_path, 'JPEG', quality=90)
                else:
                    with open(local_path, 'wb') as f:
                        for chunk in raw_resp.iter_content(8192):
                            f.write(chunk)
                
                file_size = os.path.getsize(local_path) / 1024
                local_files.append(local_path)
                print(f"  [{i+1}/{len(images)}] OK ({file_size:.0f}KB)" + (f" (重试{attempt+1}次)" if attempt > 0 else ""))
                downloaded = True
                break
                
            except Exception as e:
                if attempt < 2:
                    print(f"  [{i+1}/{len(images)}] 失败: {e}，重试 {attempt+2}/3...")
                    time.sleep(2)
                else:
                    print(f"  [{i+1}/{len(images)}] 最终失败: {e}")
        
        if not downloaded:
            continue
    
    return local_files


def upload_images_to_wechat(app_id, app_secret, image_paths):
    """
    批量上传图片到微信公众号（永久素材）
    
    Returns:
        list: media_id 列表
    """
    token = get_access_token(app_id, app_secret)
    upload_url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
    
    media_ids = []
    print(f"\n[3/4] 上传{len(image_paths)}张图片到微信...")
    
    for i, path in enumerate(image_paths):
        if not os.path.exists(path):
            print(f"  [{i+1}] 文件不存在，跳过: {path}")
            continue
        
        # 重试机制：最多重试3次
        for attempt in range(3):
            try:
                filename = os.path.basename(path)
                with open(path, 'rb') as f:
                    files = {'media': (filename, f, 'image/jpeg')}
                    resp = requests.post(upload_url, files=files, timeout=60)
                
                data = resp.json()
                errcode = data.get('errcode', 0)
                if errcode != 0:
                    print(f"  [{i+1}] 失败: [{errcode}] {data.get('errmsg')}")
                    if attempt < 2:
                        print(f"           重试 {attempt+2}/3...")
                        time.sleep(2)
                        continue
                    else:
                        break
                
                media_id = data.get('media_id')
                media_ids.append(media_id)
                print(f"  [{i+1}/{len(image_paths)}] OK - {media_id[:20]}..." + (f" (重试{attempt+1}次)" if attempt > 0 else ""))
                
                # 避免频率限制
                time.sleep(0.5)
                break
                
            except Exception as e:
                if attempt < 2:
                    print(f"  [{i+1}] 异常: {e}，重试 {attempt+2}/3...")
                    time.sleep(2)
                else:
                    print(f"  [{i+1}] 最终失败: {e}")
            continue
    
    return media_ids


def clean_title(title):
    """
    清理标题：去掉话题标签、多余空格、控制长度
    - 去掉 #话题# 标签
    - 去掉首尾空格和特殊符号
    - 控制在20字以内（微信标题限制64字，但贴图建议短标题）
    """
    if not title:
        return '无标题'
    
    # 去掉所有 #话题# 标签
    title = re.sub(r'#[^#]+#', '', title)
    
    # 去掉首尾空格、|、- 等分隔符
    title = title.strip(' |\\-·~！!？?。.')
    
    # 去掉多余连续空格
    title = re.sub(r'\s+', '', title)
    
    # 如果超过20字，截断并加省略号
    if len(title) > 20:
        title = title[:19] + '…'
    
    return title or '无标题'


def create_tietu_draft(app_id, app_secret, title, author, digest, content, image_media_ids):
    """
    创建贴图类型(newspic)草稿
    
    Args:
        content: 正文内容（HTML格式，写入正文框）
        image_media_ids: 已上传图片的永久素材media_id列表
    """
    token = get_access_token(app_id, app_secret)
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    
    # 微信author字段限制8个字符，超长截断
    if author and len(author) > 8:
        author = author[:7] + '…'
    
    article = {
        'article_type': 'newspic',
        'title': title,
        'author': author or '',
        # 贴图模式：不填digest，避免文字显示在图片下方
        # 'digest': digest or title,
        'image_info': {
            'image_list': [{'image_media_id': mid} for mid in image_media_ids]
        }
    }
    
    # 如果有描述文字，写入正文框
    if content:
        article['content'] = content
    
    data = {'articles': [article]}
    
    print(f"\n[4/4] 创建贴图草稿...")
    
    resp = requests.post(
        url,
        data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json; charset=utf-8'},
        timeout=30
    )
    
    result = resp.json()
    errcode = result.get('errcode', 0)
    if errcode != 0:
        raise Exception(f"创建草稿失败[{errcode}]: {result.get('errmsg')}")
    
    media_id = result.get('media_id')
    print("\n[OK] 贴图草稿创建成功！")
    print(f"   标题: {title}")
    print(f"   图片数: {len(image_media_ids)}张")
    print(f"   media_id: {media_id}")
    
    return {
        'status': 'success',
        'media_id': media_id,
        'title': title,
        'image_count': len(image_media_ids),
        'type': 'newspic'
    }


def main():
    parser = argparse.ArgumentParser(description='抖音/小红书图文 → 公众号贴图草稿')
    parser.add_argument('--url', required=True, help='抖音/小红书图文链接')
    parser.add_argument('--account', default=None, help='公众号名称（umi花艺/潮宠社）')
    parser.add_argument('--app_id', default=None, help='公众号AppID（优先于--account）')
    parser.add_argument('--app_secret', default=None, help='公众号AppSecret')
    parser.add_argument('--author', default=None, help='作者名称（默认从原帖提取）')
    parser.add_argument('--digest', default=None, help='摘要（默认使用标题）')
    parser.add_argument('--output_dir', default=None, help='临时文件目录（默认自动生成）')
    args = parser.parse_args()

    # 确定公众号凭证
    if args.app_id and args.app_secret:
        app_id, app_secret = args.app_id, args.app_secret
    elif args.account and args.account in ACCOUNTS:
        acct = ACCOUNTS[args.account]
        app_id, app_secret = acct['app_id'], acct['app_secret']
    else:
        print("错误: 请指定 --account (umi花艺/潮宠社) 或提供 --app_id + --app_secret")
        sys.exit(1)

    # 临时目录
    import tempfile
    output_dir = args.output_dir or os.path.join(tempfile.gettempdir(), f'tietu_{int(time.time())}')

    try:
        # Step 1: 解析链接
        parsed = parse_url(args.url)

        # Step 2: 下载图片
        local_files = download_images(parsed['images'], output_dir)
        if not local_files:
            raise Exception("没有成功下载任何图片")

        # Step 3: 上传到微信
        media_ids = upload_images_to_wechat(app_id, app_secret, local_files)
        if not media_ids:
            raise Exception("没有成功上传任何图片到微信")

        # Step 4: 创建贴图草稿
        author = args.author or parsed.get('author', '')
        digest = args.digest or parsed.get('desc') or parsed['title']
        
        # 自动精简标题（去话题标签+控制长度）
        clean = clean_title(parsed['title'])
        if clean != parsed['title']:
            print(f"  标题优化: {parsed['title'][:30]}{'...' if len(parsed['title'])>30 else ''} → {clean}")
        
        # 构建正文内容：原帖desc文字 → HTML段落
        body_html = ''
        if parsed.get('desc'):
            for line in parsed['desc'].split('\n'):
                line = line.strip()
                if line:
                    body_html += f'<p>{line}</p>'
        
        # digest 摘要限制120字，超长则截断
        if len(digest) > 120:
            digest = digest[:117] + '…'
        
        result = create_tietu_draft(
            app_id, app_secret,
            title=clean,
            author=author,
            digest=digest,
            content=body_html,
            image_media_ids=media_ids
        )

        # 输出JSON结果
        print("\n---RESULT---")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\n[ERR] 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
