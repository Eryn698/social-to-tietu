#!/usr/bin/env python3
"""
图文转贴图 v2.0 - AI二创 + AI写文章 + 贴图
后端：Flask
AI：星洞AI (api.lk888.ai) - gpt-5.4 + gpt-image-2
"""

import os
import sys
import json
import time
import tempfile
import logging
import subprocess
import re
import base64
import traceback
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = r'C:\Users\83718\.qclaw\skills\wechat-article-publisher\scripts'

# Add script dir to path
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Import social_to_tietu
try:
    import social_to_tietu as stt
    logger.info('social_to_tietu module loaded')
except Exception as e:
    logger.error(f'Failed to load social_to_tietu: {e}')
    stt = None

# ============ Config ============
CONFIG_DIR = os.path.join(BASE_DIR, 'server', 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default or {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# API keys
apikey_path = os.path.join(CONFIG_DIR, 'apikey.json')
apikey_config = load_json(apikey_path, {})
XINGDONG_API_KEY = apikey_config.get('xingdong', '')

def get_xingdong_key():
    """Allow runtime API key update"""
    global XINGDONG_API_KEY
    c = load_json(apikey_path, {})
    XINGDONG_API_KEY = c.get('xingdong', '')
    return XINGDONG_API_KEY

# ============ AI API helpers ============

def ai_chat(prompt, system_prompt=None, model='gpt-5.4', max_retries=2):
    """Call XingDong AI chat API"""
    api_key = get_xingdong_key()
    if not api_key:
        raise ValueError('Please configure XingDong AI API key in settings')
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'messages': []
    }
    if system_prompt:
        payload['messages'].append({'role': 'system', 'content': system_prompt})
    payload['messages'].append({'role': 'user', 'content': prompt})
    
    for attempt in range(max_retries):
        try:
            import urllib.request
            req = urllib.request.Request(
                'https://api.lk888.ai/api/v1/chat/completions',
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except Exception as e:
            logger.warning(f'AI chat attempt {attempt+1} failed: {e}')
            if attempt == max_retries - 1:
                raise
            time.sleep(2)
    return None

def ai_generate_image(prompt, max_retries=2):
    """Call XingDong AI image generation (async polling)"""
    api_key = get_xingdong_key()
    if not api_key:
        raise ValueError('Please configure XingDong AI API key in settings')
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'gpt-image-2',
        'prompt': prompt,
        'size': '1024x1024'
    }
    
    for attempt in range(max_retries):
        try:
            import urllib.request
            # Submit task
            req = urllib.request.Request(
                'https://api.lk888.ai/api/v1/media/generate',
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                task_id = result.get('task_id') or result.get('data', {}).get('task_id')
                if not task_id:
                    raise ValueError(f'No task_id in response: {result}')
            
            # Poll for result
            for poll in range(120):  # max 10 minutes
                time.sleep(5)
                poll_url = f'https://api.lk888.ai/api/v1/skills/task-status?task_id={task_id}'
                poll_req = urllib.request.Request(poll_url, headers=headers)
                with urllib.request.urlopen(poll_req, timeout=30) as poll_resp:
                    poll_data = json.loads(poll_resp.read().decode('utf-8'))
                
                if poll_data.get('is_final') or poll_data.get('data', {}).get('is_final'):
                    result_url = poll_data.get('result_url') or poll_data.get('data', {}).get('result_url')
                    if result_url:
                        return result_url
                logger.info(f'Image gen poll #{poll}: not ready yet')
            
            raise TimeoutError('Image generation timed out after 10 minutes')
        except Exception as e:
            logger.warning(f'Image gen attempt {attempt+1} failed: {e}')
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    return None

def download_url(url, filepath):
    """Download URL to file"""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(filepath, 'wb') as f:
            f.write(resp.read())

def compress_image(input_path, max_kb=800):
    """Compress image to under max_kb"""
    from PIL import Image
    img = Image.open(input_path)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.save(input_path, 'JPEG', quality=85, optimize=True)
    # If still too big, reduce quality
    while os.path.getsize(input_path) > max_kb * 1024 and os.path.exists(input_path):
        from PIL import Image as Img2
        img2 = Img2.open(input_path)
        w, h = img2.size
        img2 = img2.resize((int(w*0.8), int(h*0.8)), Img2.LANCZOS)
        img2.save(input_path, 'JPEG', quality=75, optimize=True)

# ============ Routes ============

@app.route('/')
def index():
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'index.html')

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'module_loaded': stt is not None,
        'script_dir': SCRIPT_DIR,
        'accounts_count': len(get_accounts_list()),
        'has_ai_key': bool(get_xingdong_key())
    })

@app.route('/api/accounts')
def get_accounts():
    return jsonify({'accounts': get_accounts_list()})

def _load_accounts_raw():
    acc_path = os.path.join(BASE_DIR, 'server', 'data', 'accounts.json')
    return load_json(acc_path, [])

def get_accounts_list():
    raw = _load_accounts_raw()
    if isinstance(raw, list):
        return [a['name'] for a in raw if 'name' in a]
    return list(raw.keys())

def get_account_config(name):
    raw = _load_accounts_raw()
    if isinstance(raw, list):
        for a in raw:
            if a.get('name') == name:
                return a
        return None
    return raw.get(name)

# ============ AI Key ============

@app.route('/api/ai-key', methods=['GET'])
def get_ai_key():
    return jsonify({'key': XINGDONG_API_KEY, 'has_key': bool(XINGDONG_API_KEY)})

@app.route('/api/ai-key', methods=['POST'])
def set_ai_key():
    data = request.get_json()
    key = data.get('key', '').strip()
    save_json(apikey_path, {'xingdong': key})
    get_xingdong_key()
    return jsonify({'ok': True})

@app.route('/api/ai/test-key', methods=['POST'])
def test_ai_key():
    try:
        get_xingdong_key()
        if not XINGDONG_API_KEY:
            return jsonify({'ok': False, 'msg': 'API key not configured'})
        result = ai_chat('Reply with just: OK', max_retries=1)
        return jsonify({'ok': True, 'msg': 'Connection successful'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

# ============ Original: Create Draft (贴图) ============

@app.route('/api/create-draft', methods=['POST'])
def create_draft():
    if stt is None:
        return jsonify({'status': 'error', 'message': 'social_to_tietu module not loaded'}), 500
    
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    account = data.get('account', '').strip()
    
    if not url:
        return jsonify({'status': 'error', 'message': 'Please enter a URL'}), 400
    if not account:
        return jsonify({'status': 'error', 'message': 'Please select an account'}), 400
    
    acc = get_account_config(account)
    if not acc:
        return jsonify({'status': 'error', 'message': f'Unknown account: {account}'}), 400
    
    app_id = acc['app_id']
    app_secret = acc['app_secret']
    
    try:
        parsed = stt.parse_url(url)
        output_dir = os.path.join(tempfile.gettempdir(), f'tietu_{int(time.time())}')
        local_files = stt.download_images(parsed['images'], output_dir)
        if not local_files:
            return jsonify({'status': 'error', 'message': 'No images downloaded'}), 500
        media_ids = stt.upload_images_to_wechat(app_id, app_secret, local_files)
        if not media_ids:
            return jsonify({'status': 'error', 'message': 'Failed to upload images'}), 500
        
        clean = stt.clean_title(parsed['title'])
        author = parsed.get('author', '')
        digest = parsed.get('desc') or parsed['title']
        if len(digest) > 120:
            digest = digest[:117] + '...'
        
        body_html = ''
        if parsed.get('desc'):
            for line in parsed['desc'].split('\n'):
                line = line.strip()
                if line:
                    body_html += f'<p>{line}</p>'
        
        result = stt.create_tietu_draft(
            app_id, app_secret,
            title=clean, author=author, digest=digest,
            content=body_html, image_media_ids=media_ids
        )
        return jsonify(result)
    except Exception as e:
        logger.exception('create_draft error')
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============ AI二创 ============

@app.route('/api/ai/rewrite-text', methods=['POST'])
def ai_rewrite_text():
    """AI rewrite text content"""
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    style = data.get('style', 'general')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    style_prompts = {
        'general': 'You are a social media content expert. Rewrite the following content to be more engaging and original. Keep the core meaning but make it fresh. Output the rewritten text only, no extra commentary.',
        'humorous': 'You are a humorous content creator. Rewrite the following content with funny, witty tone. Add some humor while keeping the core information. Output the rewritten text only.',
        'professional': 'You are a professional content writer. Rewrite the following content in a polished, authoritative tone. Make it sound expert-level. Output the rewritten text only.',
        'emotional': 'You are an emotional storyteller. Rewrite the following content to be warm, touching, and relatable. Create emotional resonance. Output the rewritten text only.',
    }
    
    system = style_prompts.get(style, style_prompts['general'])
    
    try:
        result = ai_chat(f'Rewrite this content:\n\n{text}', system_prompt=system)
        return jsonify({'text': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/generate-image', methods=['POST'])
def ai_generate_image_endpoint():
    """AI generate image"""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400
    
    try:
        url = ai_generate_image(prompt)
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/rewrite-and-draft', methods=['POST'])
def ai_rewrite_and_draft():
    """
    Full AI二创 pipeline:
    1. Parse URL to get text + images
    2. AI rewrite the text
    3. AI generate new images
    4. Upload images to WeChat
    5. Create newspic draft
    """
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    account = data.get('account', '').strip()
    style = data.get('style', 'general')
    
    if not url or not account:
        return jsonify({'error': 'URL and account required'}), 400
    
    acc = get_account_config(account)
    if not acc:
        return jsonify({'error': f'Unknown account: {account}'}), 400
    
    try:
        # Step 1: Parse URL
        parsed = stt.parse_url(url)
        original_text = parsed.get('desc') or ''
        title = stt.clean_title(parsed['title'])
        original_images = parsed.get('images', [])
        
        if not original_text and not original_images:
            return jsonify({'error': 'No text or images found in the post'}), 400
        
        # Step 2: AI rewrite text
        rewritten_text = ''
        rewritten_title = title
        if original_text:
            style_map = {
                'general': 'Rewrite this social media content to be more engaging and original. Keep core meaning but make it fresh.',
                'humorous': 'Rewrite with a funny, witty tone. Add humor while keeping core info.',
                'professional': 'Rewrite in a polished, authoritative, expert tone.',
                'emotional': 'Rewrite to be warm, touching, and emotionally resonant.',
            }
            sys_prompt = style_map.get(style, style_map['general'])
            result = ai_chat(
                f'Rewrite the following content. Also provide a rewritten title (prefix with "TITLE: ").\n\nOriginal title: {title}\n\nOriginal content:\n{original_text}',
                system_prompt=sys_prompt
            )
            # Parse out title if present
            lines = result.strip().split('\n')
            if lines[0].startswith('TITLE:'):
                rewritten_title = lines[0].replace('TITLE:', '').strip()
                rewritten_text = '\n'.join(lines[1:]).strip()
            else:
                rewritten_text = result.strip()
        
        # Step 3: Generate new images
        image_count = min(len(original_images), 6)
        new_image_paths = []
        output_dir = os.path.join(tempfile.gettempdir(), f'ai_tietu_{int(time.time())}')
        os.makedirs(output_dir, exist_ok=True)
        
        for i in range(image_count):
            img_prompt = f'{rewritten_title} - {rewritten_text[:200] if rewritten_text else ""}. Image {i+1} of {image_count}.'
            try:
                img_url = ai_generate_image(img_prompt)
                if img_url:
                    img_path = os.path.join(output_dir, f'ai_img_{i}.jpg')
                    download_url(img_url, img_path)
                    compress_image(img_path)
                    new_image_paths.append(img_path)
                    logger.info(f'Generated image {i+1}/{image_count}: {os.path.getsize(img_path)} bytes')
            except Exception as e:
                logger.warning(f'Image {i+1} gen failed: {e}')
        
        if not new_image_paths:
            # Fallback to original images
            original_dir = os.path.join(tempfile.gettempdir(), f'tietu_orig_{int(time.time())}')
            os.makedirs(original_dir, exist_ok=True)
            new_image_paths = stt.download_images(original_images, original_dir)
            logger.info(f'Using {len(new_image_paths)} original images as fallback')
        
        # Step 4: Upload to WeChat
        app_id = acc['app_id']
        app_secret = acc['app_secret']
        media_ids = stt.upload_images_to_wechat(app_id, app_secret, new_image_paths)
        if not media_ids:
            return jsonify({'error': 'Failed to upload images to WeChat'}), 500
        
        # Step 5: Create newspic draft
        author = parsed.get('author', '')
        body_html = ''
        if rewritten_text:
            for line in rewritten_text.split('\n'):
                line = line.strip()
                if line:
                    body_html += f'<p>{line}</p>'
        
        result = stt.create_tietu_draft(
            app_id, app_secret,
            title=rewritten_title, author=author,
            digest=rewritten_text[:120] if rewritten_text else rewritten_title,
            content=body_html, image_media_ids=media_ids
        )
        
        return jsonify({
            'status': 'success',
            'media_id': result.get('media_id'),
            'title': rewritten_title,
            'image_count': len(media_ids),
            'rewritten_text': rewritten_text,
            'generated_images': len(new_image_paths)
        })
        
    except Exception as e:
        logger.exception('rewrite_and_draft error')
        return jsonify({'error': str(e)}), 500

# ============ AI写文章 ============

@app.route('/api/ai/write-article', methods=['POST'])
def ai_write_article():
    """Generate article content from topic"""
    data = request.get_json() or {}
    topic = data.get('topic', '').strip()
    style = data.get('style', 'general')
    
    if not topic:
        return jsonify({'error': 'Topic required'}), 400
    
    style_map = {
        'general': 'You are an expert content writer for WeChat public accounts. Write a 1200-1500 word article in Chinese.',
        'pet': 'You are an expert pet content writer for WeChat public accounts. Write a 1200-1500 word article about pets in Chinese.',
        'floral': 'You are an expert floral arrangement content writer. Write a 1200-1500 word article about flowers/floral design in Chinese.',
        'tech': 'You are a tech industry content writer. Write a 1200-1500 word article in Chinese.',
        'lifestyle': 'You are a lifestyle content writer. Write a 1200-1500 word article in Chinese.',
    }
    
    system = style_map.get(style, style_map['general'])
    prompt = f'''Write an article in Chinese (1200-1500 words) about: {topic}

Requirements:
1. Output in Markdown format
2. Include a catchy title on the first line (format: # Title)
3. Natural, engaging writing style (not AI-sounding)
4. Well-structured with headers and paragraphs
5. Use emojis sparingly
6. End with a brief summary
7. Output the full article in Markdown only, no extra commentary'''

    try:
        result = ai_chat(prompt, system_prompt=system)
        return jsonify({'article': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/create-article-draft', methods=['POST'])
def ai_create_article_draft():
    """
    Full pipeline: topic → AI write article → generate cover → upload → create draft
    """
    data = request.get_json() or {}
    topic = data.get('topic', '').strip()
    account = data.get('account', '').strip()
    style = data.get('style', 'general')
    
    if not topic or not account:
        return jsonify({'error': 'Topic and account required'}), 400
    
    acc = get_account_config(account)
    if not acc:
        return jsonify({'error': f'Unknown account: {account}'}), 400
    
    try:
        app_id = acc['app_id']
        app_secret = acc['app_secret']
        
        # Step 1: Write article
        style_map = {
            'general': 'Expert content writer for WeChat.',
            'pet': 'Expert pet content writer for WeChat.',
            'floral': 'Expert floral design content writer.',
            'tech': 'Tech industry content writer.',
            'lifestyle': 'Lifestyle content writer.',
        }
        system = style_map.get(style, style_map['general'])
        prompt = f'''Write a Chinese article (1200-1500 words) about: {topic}

Requirements:
1. Markdown format, title on first line as # Title
2. Natural engaging style (not AI-sounding)
3. Well-structured with headers (##, ###)
4. Use emojis sparingly
5. Brief summary at the end
6. Full article in Markdown only'''

        article_md = ai_chat(prompt, system_prompt=system)
        
        # Extract title from markdown
        title_match = re.search(r'^#\s+(.+)', article_md, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else topic
        title = stt.clean_title(title)
        
        # Step 2: Generate cover image
        cover_prompt = f'Cover image for article: {title}. Professional, clean, eye-catching.'
        cover_url = ai_generate_image(cover_prompt)
        
        cover_path = None
        thumb_media_id = None
        output_dir = os.path.join(tempfile.gettempdir(), f'article_{int(time.time())}')
        os.makedirs(output_dir, exist_ok=True)
        
        if cover_url:
            cover_path = os.path.join(output_dir, 'cover.jpg')
            download_url(cover_url, cover_path)
            compress_image(cover_path)
            
            # Upload as thumb for cover
            try:
                import urllib.request
                token_url = f'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}'
                token_req = urllib.request.Request(token_url)
                with urllib.request.urlopen(token_req, timeout=30) as token_resp:
                    token_data = json.loads(token_resp.read().decode('utf-8'))
                access_token = token_data['access_token']
                
                # Upload thumb
                import io
                media_url = f'https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image'
                boundary = '----FormBoundary7MA4YWxkTrZu0gW'
                with open(cover_path, 'rb') as f:
                    img_data = f.read()
                body = (
                    f'--{boundary}\r\n'
                    f'Content-Disposition: form-data; name="media"; filename="cover.jpg"\r\n'
                    f'Content-Type: image/jpeg\r\n\r\n'
                ).encode() + img_data + f'\r\n--{boundary}--\r\n'.encode()
                
                upload_req = urllib.request.Request(
                    media_url,
                    data=body,
                    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
                )
                with urllib.request.urlopen(upload_req, timeout=60) as upload_resp:
                    upload_data = json.loads(upload_resp.read().decode('utf-8'))
                thumb_media_id = upload_data.get('thumb_media_id') or upload_data.get('media_id')
            except Exception as e:
                logger.warning(f'Cover upload failed: {e}')
        
        # Step 3: Convert Markdown to WeChat HTML
        md_file = os.path.join(output_dir, 'article.md')
        html_file = os.path.join(output_dir, 'article.html')
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(article_md)
        
        convert_script = os.path.join(SCRIPT_DIR, 'markdown_to_wechat_doocs.py')
        if os.path.exists(convert_script):
            convert_result = subprocess.run(
                ['python', convert_script, '-i', md_file, '-o', html_file, '--theme', 'orange'],
                capture_output=True, text=True, timeout=30, encoding='utf-8',
                errors='replace'
            )
            if convert_result.returncode == 0 and os.path.exists(html_file):
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                logger.warning(f'MD conversion failed: {convert_result.stderr}')
                html_content = '<p>' + article_md.replace('\n', '</p><p>') + '</p>'
        else:
            html_content = '<p>' + article_md.replace('\n', '</p><p>') + '</p>'
        
        # Step 4: Create article draft (news type, not newspic)
        draft_url = f'https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}'
        draft_body = {
            'articles': [{
                'title': title,
                'author': '',
                'digest': article_md[:120].replace('#', '').replace('*', '').strip(),
                'content': html_content,
                'thumb_media_id': thumb_media_id or '',
                'content_source_url': '',
                'need_open_comment': 0,
                'only_fans_can_comment': 0
            }]
        }
        
        draft_req = urllib.request.Request(
            draft_url,
            data=json.dumps(draft_body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(draft_req, timeout=30) as draft_resp:
            draft_data = json.loads(draft_resp.read().decode('utf-8'))
        
        media_id = draft_data.get('media_id')
        
        return jsonify({
            'status': 'success',
            'media_id': media_id,
            'title': title,
            'has_cover': bool(thumb_media_id)
        })
        
    except Exception as e:
        logger.exception('create_article_draft error')
        return jsonify({'error': str(e)}), 500

# ============ Settings ============

@app.route('/api/parse', methods=['POST'])
def parse_url_api():
    """Parse social media URL (for preview)"""
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL required'}), 400
    try:
        parsed = stt.parse_url(url)
        return jsonify({
            'title': parsed.get('title', ''),
            'desc': parsed.get('desc', ''),
            'author': parsed.get('author', ''),
            'images': parsed.get('images', []),
            'image_count': len(parsed.get('images', []))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'Starting server on http://0.0.0.0:{port}')
    app.run(host='0.0.0.0', port=port, debug=True)
