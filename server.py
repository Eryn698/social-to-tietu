#!/usr/bin/env python3
"""
社交媒体图文 → 公众号贴图草稿 Web界面
后端：Flask，通过 subprocess 调用 social_to_tietu.py（彻底隔离GBK问题）

支持动态增删公众号配置文件（JSON文件存储）
"""

import os
import sys
import json
import subprocess
import tempfile
import logging
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# ====== 彻底解决GBK编码问题 ======
# 方案：不import social_to_tietu模块，改用subprocess调用
# 这样模块内任何print/异常都不会影响Flask进程

app = Flask(__name__)
CORS(app)

# 脚本路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(BASE_DIR, 'scripts', 'wechat-article-publisher', 'social_to_tietu.py')
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'server', 'data', 'accounts.json')

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)


# ==================== 公众号配置管理 ====================

def load_accounts():
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.warning(f'load accounts failed: {e}')
        return []


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


def build_accounts_map(accounts_list):
    return {acc['name']: acc for acc in accounts_list}


def _run_script(*args, timeout=180):
    """通过subprocess调用social_to_tietu.py，隔离GBK问题"""
    cmd = [sys.executable, SCRIPT_PATH] + list(args)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8:surrogateescape'
    env['PYTHONUTF8'] = '1'

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
        cwd=os.path.dirname(SCRIPT_PATH),
        env=env
    )
    return result


def _verify_credentials(app_id, app_secret):
    """验证公众号凭证（通过subprocess调用，避免import问题）"""
    # 直接用requests验证token
    import requests
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    if data.get('errcode', 0) != 0:
        raise Exception(f"token failed [{data.get('errcode')}]: {data.get('errmsg')}")
    return True


# ==================== Flask 路由 ====================

@app.route('/')
def index():
    accounts = load_accounts()
    account_names = [acc['name'] for acc in accounts]
    safe_accounts = [{'name': acc['name'], 'app_id': acc['app_id']} for acc in accounts]
    return render_template('index.html', accounts=account_names, safe_accounts=safe_accounts)


@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    accounts = load_accounts()
    safe_accounts = [{
        'name': acc['name'],
        'app_id': acc['app_id'],
        'created_at': acc.get('created_at', '')
    } for acc in accounts]
    return jsonify({'accounts': safe_accounts})


@app.route('/api/accounts/add', methods=['POST'])
def add_account():
    data = request.get_json()
    if data is None:
        return jsonify({'status': 'error', 'message': 'invalid JSON'}), 400

    name = data.get('name', '').strip()
    app_id = data.get('app_id', '').strip()
    app_secret = data.get('app_secret', '').strip()

    if not name:
        return jsonify({'status': 'error', 'message': 'please enter name'}), 400
    if not app_id:
        return jsonify({'status': 'error', 'message': 'please enter AppID'}), 400
    if not app_secret:
        return jsonify({'status': 'error', 'message': 'please enter AppSecret'}), 400
    if not app_id.startswith('wx'):
        return jsonify({'status': 'error', 'message': 'AppID must start with wx'}), 400

    accounts = load_accounts()

    if any(acc['name'] == name for acc in accounts):
        return jsonify({'status': 'error', 'message': f'account "{name}" exists'}), 400
    if any(acc['app_id'] == app_id for acc in accounts):
        return jsonify({'status': 'error', 'message': 'AppID already in use'}), 400

    try:
        _verify_credentials(app_id, app_secret)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'invalid credentials: {e}'}), 400

    new_account = {
        'name': name,
        'app_id': app_id,
        'app_secret': app_secret,
        'created_at': __import__('datetime').datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    }
    accounts.append(new_account)
    save_accounts(accounts)

    return jsonify({
        'status': 'success',
        'message': f'"{name}" added',
        'account': {'name': name, 'app_id': app_id}
    })


@app.route('/api/accounts/delete', methods=['POST'])
def delete_account():
    data = request.get_json()
    if data is None:
        return jsonify({'status': 'error', 'message': 'invalid JSON'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'status': 'error', 'message': 'specify name'}), 400

    accounts = load_accounts()
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['name'] != name]

    if len(accounts) == original_len:
        return jsonify({'status': 'error', 'message': f'"{name}" not found'}), 400

    save_accounts(accounts)
    return jsonify({'status': 'success', 'message': f'"{name}" deleted'})


@app.route('/api/create-draft', methods=['POST'])
def create_draft():
    data = request.get_json()
    if data is None:
        return jsonify({'status': 'error', 'message': 'invalid JSON'}), 400

    url = data.get('url', '').strip()
    account = data.get('account', '').strip()

    if not url:
        return jsonify({'status': 'error', 'message': 'enter URL'}), 400
    if not account:
        return jsonify({'status': 'error', 'message': 'select account'}), 400

    accounts = load_accounts()
    acc_map = build_accounts_map(accounts)

    if account not in acc_map:
        return jsonify({'status': 'error', 'message': f'unknown account: {account}'}), 400

    log.info(f'processing: {account}, url={url[:50]}...')

    try:
        # 通过subprocess调用，彻底隔离GBK问题
        result = _run_script(
            '--url', url,
            '--account', account,
            timeout=180
        )

        if result.returncode != 0:
            log.error(f'script failed (code {result.returncode}): {result.stderr[-500:]}')
            return jsonify({
                'status': 'error',
                'message': f'script error: {result.stderr[-300:]}'
            }), 500

        # 解析 ---RESULT--- 分隔符后的JSON
        stdout = result.stdout
        if '---RESULT---' in stdout:
            json_str = stdout.split('---RESULT---')[1].strip()
            return jsonify(json.loads(json_str))
        else:
            log.error(f'no result marker in output: {stdout[-500:]}')
            return jsonify({'status': 'error', 'message': 'unexpected output format'}), 500

    except subprocess.TimeoutExpired:
        log.error('script timeout (180s)')
        return jsonify({'status': 'error', 'message': 'operation timeout (180s)'}), 500
    except json.JSONDecodeError as e:
        log.error(f'JSON parse error: {e}')
        return jsonify({'status': 'error', 'message': f'result parse error: {e}'}), 500
    except Exception as e:
        log.error(f'unexpected error: {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    script_exists = os.path.isfile(SCRIPT_PATH)
    return jsonify({
        'status': 'ok',
        'script_path': SCRIPT_PATH,
        'script_exists': script_exists,
        'accounts_count': len(load_accounts())
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'Starting server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
