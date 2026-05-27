#!/usr/bin/env python3
"""
社交媒体图文 → 公众号草稿 Web界面 v2.0
新增功能：密码登录 | AI二创(reference xhs-rewriter) | AI写文章发公众号
"""

import os
import sys
import json
import subprocess
import tempfile
import hashlib
import secrets
import time
import logging
import re
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# ====== 初始化 ======
app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts', 'wechat-article-publisher')
TIETU_SCRIPT = os.path.join(SCRIPTS_DIR, 'social_to_tietu.py')
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'server', 'data', 'accounts.json')
PASSWORD_FILE = os.path.join(BASE_DIR, 'server', 'config', 'password.json')
API_KEY_FILE = os.path.join(BASE_DIR, 'server', 'config', 'apikey.json')

# 确保目录存在
os.makedirs(os.path.join(BASE_DIR, 'server', 'data'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'server', 'config'), exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


# ==================== 密码管理系统 ====================

def _hash_password(pwd):
    return hashlib.sha256(f"social_tietu_{pwd}".encode()).hexdigest()


def get_password_hash():
    try:
        with open(PASSWORD_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('password_hash', '')
    except:
        return _hash_password('admin123')  # 初始默认密码


def save_password(new_password):
    data = {'password_hash': _hash_password(new_password)}
    with open(PASSWORD_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)


# 会话令牌（简单实现：内存字典，12小时过期）
_sessions = {}

def _clean_expired_sessions():
    now = datetime.now()
    expired = [k for k, v in _sessions.items() if v['expires'] < now]
    for k in expired:
        del _sessions[k]


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        _clean_expired_sessions()
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if token in _sessions:
                _sessions[token]['expires'] = datetime.now() + timedelta(hours=12)
                return f(*args, **kwargs)
        return jsonify({'status': 'error', 'message': '请先登录', 'code': 'AUTH_REQUIRED'}), 401
    return wrapper


# ==================== AI Key 管理 ====================

def get_ai_key():
    try:
        with open(API_KEY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('api_key', '')
    except:
        return ''


def save_ai_key(key):
    with open(API_KEY_FILE, 'w', encoding='utf-8') as f:
        json.dump({'api_key': key}, f)


# ==================== 公众号配置 ====================

def load_accounts():
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


# ==================== 辅助函数 ====================

def _run_py(script_name, *args, timeout=180):
    """通用 subprocess 调用"""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path] + list(args)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8:surrogateescape'
    env['PYTHONUTF8'] = '1'
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout, cwd=SCRIPTS_DIR, env=env)
    return result


def _verify_wechat_credentials(app_id, app_secret):
    import requests
    resp = requests.get("https://api.weixin.qq.com/cgi-bin/token",
                        params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret}, timeout=30)
    data = resp.json()
    if data.get('errcode', 0) != 0:
        raise Exception(f"[{data.get('errcode')}] {data.get('errmsg')}")
    return True


def _call_ai(messages, model='gpt-5.4', max_tokens=2000, temperature=0.7, timeout=120):
    """调用星洞AI chat/completions"""
    import requests as req
    api_key = get_ai_key()
    if not api_key:
        raise Exception("请先配置星洞AI API Key")
    resp = req.post('https://api.lk888.ai/api/v1/chat/completions', json={
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature
    }, headers={'Authorization': f'Bearer {api_key}'}, timeout=timeout)
    data = resp.json()
    if data.get('error'):
        raise Exception(f"AI: {data['error'].get('message', str(data['error']))}")
    return data['choices'][0]['message']['content']


def _generate_image(prompt, model='gpt-image-2', timeout=600):
    """调用星洞AI生成图片（异步轮询）"""
    import requests as req
    api_key = get_ai_key()
    if not api_key:
        raise Exception("请先配置星洞AI API Key")

    # Step 1: 提交任务
    log.info(f'[image] submit: {prompt[:80]}...')
    resp = req.post('https://api.lk888.ai/api/v1/media/generate', json={
        'model': model,
        'params': {'prompt': prompt, 'size': 'auto', 'quality': 'auto'}
    }, headers={'Authorization': f'Bearer {api_key}'}, timeout=30)
    body = resp.json()
    task_id = body.get('data', {}).get('task_id') or body.get('task_id')
    if not task_id:
        raise Exception(f"提交图片任务失败: {body}")

    # Step 2: 轮询
    log.info(f'[image] task_id={task_id}, polling...')
    for i in range(120):
        time.sleep(5)
        try:
            status_resp = req.get(
                f'https://api.lk888.ai/api/v1/skills/task-status?task_id={task_id}',
                headers={'Authorization': f'Bearer {api_key}'}, timeout=10)
            status_data = status_resp.json()
            if status_data.get('is_final'):
                result_url = status_data.get('result_url', '')
                log.info(f'[image] done: {result_url[:60]}...')
                return result_url
        except:
            pass
    raise Exception("图片生成超时(10分钟)")


def _download_image(url, output_path):
    import requests as req
    import urllib.request
    from PIL import Image
    import io

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
               'Referer': 'https://api.lk888.ai/'}
    try:
        raw_resp = req.get(url, headers=headers, timeout=60)
        raw_resp.raise_for_status()
    except:
        req_obj = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req_obj, timeout=60) as urlopen_resp:
            raw_content = urlopen_resp.read()
        raw_resp = type('obj', (), {'content': raw_content, 'headers': {'Content-Type': 'image/jpeg'}})()

    content_type = raw_resp.headers.get('Content-Type', '')
    if 'webp' in content_type or url.lower().endswith('.webp'):
        img = Image.open(io.BytesIO(raw_resp.content))
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(output_path, 'JPEG', quality=90)
    else:
        with open(output_path, 'wb') as f:
            f.write(raw_resp.content)

    # 压缩到800KB以下
    size_kb = os.path.getsize(output_path) / 1024
    if size_kb > 800:
        from PIL import Image as PILImage
        img = PILImage.open(output_path)
        quality = 85
        while quality > 30:
            img.save(output_path, 'JPEG', quality=quality)
            new_size = os.path.getsize(output_path) / 1024
            if new_size <= 800:
                break
            quality -= 10
    return output_path


def _upload_to_wechat(app_id, app_secret, image_path):
    """上传一张图片到微信永久素材"""
    import requests as req
    token_resp = req.get("https://api.weixin.qq.com/cgi-bin/token",
                         params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret}, timeout=30)
    token_data = token_resp.json()
    if token_data.get('errcode', 0) != 0:
        raise Exception(f"获取token失败: {token_data.get('errmsg')}")
    token = token_data['access_token']

    upload_url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
    filename = os.path.basename(image_path)
    with open(image_path, 'rb') as f:
        resp = req.post(upload_url, files={'media': (filename, f, 'image/jpeg')}, timeout=60)
    data = resp.json()
    if data.get('errcode', 0) != 0:
        raise Exception(f"上传图片失败[{data.get('errcode')}]: {data.get('errmsg')}")
    return data.get('media_id')


def _md_to_wechat_html(md_content, title=''):
    """使用 doocs 脚本将 markdown 转换为微信 HTML"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(md_content)
        md_path = f.name
    html_path = md_path.replace('.md', '.html')
    try:
        result = _run_py('markdown_to_wechat_doocs.py', '-i', md_path, '-o', html_path, '--theme', 'orange', timeout=30)
        if result.returncode != 0:
            log.warning(f'markdown_to_wechat_doocs warning: {result.stderr[-200:]}')
        if os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as f:
                return f.read()
        return f"<h1>{title}</h1>" + "".join(f"<p>{line}</p>" for line in md_content.split('\n') if line.strip())
    finally:
        if os.path.exists(md_path):
            os.unlink(md_path)
        if os.path.exists(html_path):
            os.unlink(html_path)


# ==================== 认证路由 ====================

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'invalid JSON'}), 400
    password = data.get('password', '')
    stored_hash = get_password_hash()
    if _hash_password(password) != stored_hash:
        return jsonify({'status': 'error', 'message': '密码错误'}), 401
    token = secrets.token_urlsafe(32)
    _sessions[token] = {'expires': datetime.now() + timedelta(hours=12)}
    return jsonify({'status': 'success', 'token': token})


@app.route('/api/auth/change-password', methods=['POST'])
@require_auth
def change_password():
    data = request.get_json()
    old_pwd = data.get('old_password', '')
    new_pwd = data.get('new_password', '')
    if len(new_pwd) < 4:
        return jsonify({'status': 'error', 'message': '新密码至少4位'}), 400
    if _hash_password(old_pwd) != get_password_hash():
        return jsonify({'status': 'error', 'message': '原密码错误'}), 400
    save_password(new_pwd)
    return jsonify({'status': 'success', 'message': '密码已修改'})


@app.route('/api/auth/verify', methods=['GET'])
@require_auth
def verify_token():
    return jsonify({'status': 'success'})


# ==================== AI Key 路由 ====================

@app.route('/api/ai-key', methods=['GET'])
@require_auth
def get_api_key():
    key = get_ai_key()
    return jsonify({'api_key': key[:8] + '****' + key[-4:] if len(key) > 12 else ''})


@app.route('/api/ai-key', methods=['POST'])
@require_auth
def set_api_key():
    data = request.get_json()
    key = data.get('api_key', '').strip()
    if not key:
        return jsonify({'status': 'error', 'message': '请输入API Key'}), 400
    save_ai_key(key)
    return jsonify({'status': 'success', 'message': 'API Key已保存'})


@app.route('/api/ai/test-key', methods=['POST'])
@require_auth
def test_api_key():
    data = request.get_json()
    key = data.get('api_key', '').strip() or get_ai_key()
    if not key:
        return jsonify({'success': False, 'error': '请先填写 API Key'})
    try:
        import requests as req
        resp = req.post('https://api.lk888.ai/api/v1/chat/completions', json={
            'model': 'gpt-5.4', 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5
        }, headers={'Authorization': f'Bearer {key}'}, timeout=10)
        return jsonify({'success': True, 'model': 'gpt-5.4'})
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            status = e.response.status_code
            err_msg = 'API Key 无效或已过期' if status in (401, 403) else f'连接失败({status})'
        return jsonify({'success': False, 'error': err_msg})


# ==================== 公众号管理路由 ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    accounts = load_accounts()
    safe = [{'name': a['name'], 'app_id': a['app_id'], 'created_at': a.get('created_at', '')} for a in accounts]
    return jsonify({'accounts': safe})


@app.route('/api/accounts/add', methods=['POST'])
@require_auth
def add_account():
    data = request.get_json()
    name = data.get('name', '').strip()
    app_id = data.get('app_id', '').strip()
    app_secret = data.get('app_secret', '').strip()
    if not name or not app_id or not app_secret:
        return jsonify({'status': 'error', 'message': '请填写完整信息'}), 400
    if not app_id.startswith('wx'):
        return jsonify({'status': 'error', 'message': 'AppID格式错误'}), 400
    accounts = load_accounts()
    if any(a['name'] == name for a in accounts):
        return jsonify({'status': 'error', 'message': f'"{name}" 已存在'}), 400
    try:
        _verify_wechat_credentials(app_id, app_secret)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'凭证无效: {e}'}), 400
    accounts.append({'name': name, 'app_id': app_id, 'app_secret': app_secret,
                     'created_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})
    save_accounts(accounts)
    return jsonify({'status': 'success', 'message': f'"{name}" 添加成功'})


@app.route('/api/accounts/delete', methods=['POST'])
@require_auth
def delete_account():
    data = request.get_json()
    name = data.get('name', '').strip()
    accounts = load_accounts()
    original = len(accounts)
    accounts = [a for a in accounts if a['name'] != name]
    if len(accounts) == original:
        return jsonify({'status': 'error', 'message': f'"{name}" 不存在'}), 400
    save_accounts(accounts)
    return jsonify({'status': 'success', 'message': f'"{name}" 已删除'})


# ==================== 贴图创建 ====================

@app.route('/api/create-draft', methods=['POST'])
@require_auth
def create_draft():
    data = request.get_json()
    url = data.get('url', '').strip()
    account = data.get('account', '').strip()
    if not url or not account:
        return jsonify({'status': 'error', 'message': '请填写URL和选择公众号'}), 400

    log.info(f'[tietu] {account} url={url[:60]}...')
    try:
        result = _run_py('social_to_tietu.py', '--url', url, '--account', account, timeout=180)
        if result.returncode != 0:
            log.error(f'tietu failed: {result.stderr[-300:]}')
            return jsonify({'status': 'error', 'message': f'脚本错误: {result.stderr[-200:]}'}), 500
        if '---RESULT---' in result.stdout:
            return jsonify(json.loads(result.stdout.split('---RESULT---')[1].strip()))
        return jsonify({'status': 'error', 'message': '输出格式异常'}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': '操作超时'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ==================== 解析链接 ====================

@app.route('/api/parse', methods=['POST'])
@require_auth
def parse_url():
    import requests as req
    data = request.get_json()
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'status': 'error', 'message': '请输入链接'}), 400

    try:
        # 先用 api.bugpk.com 解析
        resp = req.get('https://api.bugpk.com/api/short_videos', params={'url': url}, timeout=30)
        apidata = resp.json()
        if apidata.get('code') == 200:
            d = apidata['data']
            images = d.get('images', [])
            author_info = d.get('author', {})
            return jsonify({
                'status': 'success',
                'title': d.get('title', ''),
                'desc': d.get('desc', ''),
                'images': images,
                'image_count': len(images),
                'author': author_info.get('name') or author_info.get('nickname', ''),
                'platform': d.get('type', 'unknown'),
                'source_url': url
            })
        return jsonify({'status': 'error', 'message': f"解析失败: {apidata.get('msg', '未知错误')}"}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'解析失败: {e}'}), 500


# ==================== AI 二创 ====================

@app.route('/api/ai/rewrite-text', methods=['POST'])
@require_auth
def ai_rewrite_text():
    data = request.get_json()
    text = data.get('text', '').strip()
    style = data.get('style', '改写得更吸引人')
    if not text:
        return jsonify({'status': 'error', 'message': '请输入原文'}), 400

    prompt_map = {
        '更吸引人': '你是一个爆款文案改写专家。请将以下文案改写得更吸引人，适合在公众号发布。保持核心信息不变，用更有感染力的语言表达，加入适当的emoji和互动感。字数控制在300-500字。',
        '更专业': '你是一个专业文案编辑。请将以下文案改写得更专业、更有深度。去掉口语化表达，使用正式但不枯燥的语言，条理清晰。字数控制在300-500字。',
        '更简洁': '你是一个精炼文案专家。请将以下文案压缩得更简洁，去掉冗余表达，保留核心精华。提炼出最有力的观点。字数控制在200-300字。',
        '小红书风格': '你是一个小红书种草文案写手。请将以下文案改成小红书风格的种草文案，多用emoji、感叹号、分段式表达。像分享心得一样自然。字数控制在300-500字。',
    }
    system_prompt = prompt_map.get(style, prompt_map['更吸引人'])
    user_prompt = f"原标题：{data.get('title', '')}\n\n原文：{text}"

    try:
        result = _call_ai([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ], model='gpt-5.4', max_tokens=2000, temperature=0.8)
        return jsonify({'status': 'success', 'rewritten': result, 'style': style})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/ai/generate-image', methods=['POST'])
@require_auth
def generate_image():
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'status': 'error', 'message': '请输入图片描述'}), 400
    try:
        result_url = _generate_image(prompt)
        if not result_url:
            return jsonify({'status': 'error', 'message': '图片生成结果为空'}), 500
        return jsonify({'status': 'success', 'image_url': result_url})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ==================== AI写文章 → 草稿箱 ====================

@app.route('/api/ai/write-article', methods=['POST'])
@require_auth
def ai_write_article():
    data = request.get_json()
    topic = data.get('topic', '').strip()
    style = data.get('style', '通用')
    if not topic:
        return jsonify({'status': 'error', 'message': '请输入主题'}), 400

    style_guides = {
        '宠物': '你是一个宠物类公众号作者。文章要有爱心、温暖、接地气。多用具体场景和小故事。不要过度说教。适合养宠人阅读。',
        '花艺': '你是一个花艺生活类公众号作者。文章要优雅、有格调、有生活气息。分享花艺知识的同时传递美好的生活态度。',
        '科技': '你是一个科技类公众号作者。文章要专业但不晦涩，用通俗语言解释技术。适合普通读者理解。',
        '生活': '你是一个生活方式类公众号作者。文章要温暖、治愈、正能量。用讲故事的方式传递生活智慧。',
        '通用': '你是一个优秀的公众号作者。文章要有深度、有观点、易读。用自然流畅的中文，避免AI腔。',
    }

    system_prompt = f"""{style_guides.get(style, style_guides['通用'])}

写作要求：
1. 标题要吸引人，15字以内
2. 用Markdown格式，标题用 ## 开头
3. 文章1200-1500字
4. 分3-4个小标题段落
5. 开头要有hook（吸引读者读下去）
6. 结尾要有总结或互动引导
7. 不要用"在当今"、"随着...的发展"这类AI套话
8. 像真人写的，有感情、有态度"""

    try:
        article = _call_ai([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f'写一篇关于"{topic}"的公众号文章'}
        ], model='gpt-5.4', max_tokens=3000, temperature=0.85)

        # 提取标题（第一行 ## 标题）
        title = topic
        lines = article.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('## '):
                title = line.replace('## ', '').strip()
                break
            elif line.startswith('# ') and not line.startswith('## '):
                title = line.replace('# ', '').strip()
                break

        return jsonify({
            'status': 'success',
            'title': title[:30],
            'content_md': article,
            'style': style
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/ai/create-article-draft', methods=['POST'])
@require_auth
def create_article_draft():
    """
    完整流程：生成封面图 → 上传封面 → MD转HTML → 创建草稿
    """
    data = request.get_json()
    account = data.get('account', '').strip()
    title = data.get('title', '').strip()
    content_md = data.get('content_md', '').strip()
    author = data.get('author', '').strip()
    image_prompt = data.get('image_prompt', '').strip()

    if not account or not title or not content_md:
        return jsonify({'status': 'error', 'message': '缺少标题/内容/公众号'}), 400

    # 获取公众号凭证
    accounts = load_accounts()
    acc = next((a for a in accounts if a['name'] == account), None)
    if not acc:
        return jsonify({'status': 'error', 'message': f'公众号 "{account}" 不存在'}), 400

    temp_dir = tempfile.mkdtemp(prefix='article_')

    try:
        # Step 1: 生成封面图
        cover_prompt = image_prompt or f"公众号文章封面图，" + title[:20] + "，简约风格，16:9横屏构图，适合公众号封面"
        log.info(f'[article] generate cover: {cover_prompt[:60]}...')
        cover_url = _generate_image(cover_prompt)
        cover_path = os.path.join(temp_dir, 'cover.jpg')
        _download_image(cover_url, cover_path)
        log.info(f'[article] cover saved: {os.path.getsize(cover_path)/1024:.0f}KB')

        # Step 2: 上传封面到微信
        log.info(f'[article] upload cover to wechat...')
        thumb_media_id = _upload_to_wechat(acc['app_id'], acc['app_secret'], cover_path)
        log.info(f'[article] thumb_media_id: {thumb_media_id[:15]}...')

        # Step 3: MD转HTML
        log.info(f'[article] md to html...')
        html_content = _md_to_wechat_html(content_md, title)

        # Step 4: 创建草稿 (用 subprocess 调用 create_draft.py)
        # 先写入HTML到临时文件
        html_path = os.path.join(temp_dir, 'article.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 直接调用API（避免 subprocess 传 HTML 的问题）
        import requests as req
        token_resp = req.get("https://api.weixin.qq.com/cgi-bin/token",
                             params={"grant_type": "client_credential", "appid": acc['app_id'], "secret": acc['app_secret']},
                             timeout=30)
        token = token_resp.json()['access_token']

        draft_data = {
            'articles': [{
                'title': title,
                'content': html_content,
                'thumb_media_id': thumb_media_id,
                'show_cover_pic': 1,
                'digest': content_md[:100].replace('#', '').replace('*', '').strip()
            }]
        }
        if author:
            draft_data['articles'][0]['author'] = author[:8]

        resp = req.post(f'https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}',
                        data=json.dumps(draft_data, ensure_ascii=False).encode('utf-8'),
                        headers={'Content-Type': 'application/json; charset=utf-8'}, timeout=30)
        result = resp.json()
        if result.get('errcode', 0) != 0:
            raise Exception(f"创建草稿失败[{result.get('errcode')}]: {result.get('errmsg')}")

        media_id = result['media_id']
        log.info(f'[article] draft created: {media_id}')

        return jsonify({
            'status': 'success',
            'media_id': media_id,
            'title': title,
            'type': 'article'
        })

    except Exception as e:
        log.error(f'[article] error: {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==================== 静态文件 + 主页 ====================

@app.route('/')
def index():
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'index.html')


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'script_exists': os.path.isfile(TIETU_SCRIPT),
        'accounts_count': len(load_accounts()),
        'has_password': bool(get_password_hash()),
        'has_ai_key': bool(get_ai_key())
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'Server on port {port} (Auth + AI + WeChat)')
    app.run(host='0.0.0.0', port=port, debug=False)
