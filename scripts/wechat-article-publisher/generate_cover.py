#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pillow>=10.0.0",
# ]
# ///
"""
生成公众号文章封面图片 - 统一入口

支持三种图像生成服务：
1. 星洞AI (Xingdong) - 默认，使用 gpt-image-2 模型
2. 豆包 (Doubao) - 火山引擎
3. 千问 (Qwen) - 通义万相

使用方法：
    # 使用星洞AI生成（默认）
    python3 generate_cover.py --prompt "科技风格插画"
    
    # 使用豆包生成
    python3 generate_cover.py --prompt "科技风格插画" --provider doubao
    
    # 使用千问生成
    python3 generate_cover.py --prompt "科技风格插画" --provider qwen
    
    # 指定尺寸（千问支持）
    python3 generate_cover.py --prompt "科技风格插画" --provider qwen --size "1024*1024"
"""

import os
import sys
import argparse
import json


def generate_cover_xingdong(prompt: str, model: str = "gpt-image-2") -> dict:
    """
    使用星洞AI生成封面图片（异步轮询模式）
    
    Args:
        prompt: 图片提示词
        model: 模型名称（gpt-image-2 / gptimag2）
        
    Returns:
        dict: 包含图片URL的响应数据
    """
    import requests
    import time
    
    api_key = os.getenv("XINGDONG_API_KEY")
    if not api_key:
        raise ValueError("缺少星洞AI API凭证，请设置环境变量 XINGDONG_API_KEY 或在 .env 文件中配置 XINGDONG_API_KEY")
    
    base_url = "https://api.lk888.ai/api"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    print(f"正在使用星洞AI生成封面图片 (模型: {model})...", file=sys.stderr)
    
    # Step 1: 提交任务
    submit_url = f"{base_url}/v1/media/generate"
    submit_data = {
        "model": model,
        "params": {
            "prompt": prompt,
            "size": "1664x928"  # 16:9 横屏
        }
    }
    
    response = requests.post(submit_url, headers=headers, json=submit_data, timeout=120)
    response.raise_for_status()
    result = response.json()
    
    # 解析 task_id（兼容多种返回格式）
    task_id = result.get("task_id")
    if not task_id:
        data = result.get("data", {})
        task_id = data.get("task_id") or (data.get("task_ids") and data["task_ids"][0]) if isinstance(data, dict) else None
    if not task_id:
        raise Exception(f"提交任务失败: {json.dumps(result, ensure_ascii=False)[:500]}")
    
    print(f"任务已提交, task_id={task_id}, 正在轮询...", file=sys.stderr)
    
    # Step 2: 轮询状态
    poll_url = f"{base_url}/v1/skills/task-status?task_id={task_id}"
    max_wait = 180  # 最多等3分钟
    start_time = time.time()
    
    while True:
        elapsed = int(time.time() - start_time)
        if elapsed > max_wait:
            raise Exception(f"任务超时 ({max_wait}s), task_id={task_id}")
        
        time.sleep(5)  # 5秒间隔
        try:
            poll_resp = requests.get(poll_url, headers=headers, timeout=60)
            poll_resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  [轮询] 网络异常: {e}, 重试中...", file=sys.stderr)
            time.sleep(5)
            continue
        status = poll_resp.json()
        
        state = status.get("state", "unknown")
        progress = status.get("progress", 0)
        is_final = status.get("is_final", False)
        
        print(f"  [状态] state={state}, progress={progress}%, is_final={is_final}", file=sys.stderr)
        
        if is_final or state == "completed" or state == "success":
            result_url = status.get("result_url")
            if not result_url:
                # 尝试从 output/result 中获取 URL
                output = status.get("output", status.get("result", {}))
                result_url = output.get("url", output.get("image_url", output.get("images", [{}])[0].get("url") if isinstance(output.get("images"), list) else None))
            if not result_url:
                raise Exception(f"任务完成但未找到图片URL: {json.dumps(status, ensure_ascii=False)[:500]}")
            
            return {
                "success": True,
                "provider": "xingdong",
                "model": model,
                "image_url": result_url,
                "task_id": task_id
            }
        
        if state in ("failed", "error"):
            error_msg = status.get("error_message", status.get("message", "未知错误"))
            raise Exception(f"星洞AI生图失败: {error_msg}, task_id={task_id}")


def generate_cover_doubao(prompt: str, model: str = "doubao-seedream-4-5-251128") -> dict:
    """
    使用豆包生成封面图片
    
    Args:
        prompt: 图片提示词
        model: 豆包模型（doubao-seedream-4-0-250828, doubao-seedream-4-5-251128, doubao-seedream-5-0-260128）
        
    Returns:
        dict: 包含图片URL的响应数据
    """
    import requests
    
    # 获取API Key - 优先从配置文件读取
    api_key = os.getenv("DOUBAO_API_KEY")
    if not api_key:
        try:
            from config import get_doubao_api_key
            api_key = get_doubao_api_key()
        except:
            pass
    
    if not api_key:
        raise ValueError("缺少豆包图像API凭证，请设置环境变量 DOUBAO_API_KEY 或在 .env 文件中配置")
    
    # 构建请求
    url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    request_data = {
        "model": model,
        "prompt": prompt,
        "sequential_image_generation": "disabled",
        "response_format": "url",
        "size": "2K",
        "stream": False,
        "watermark": True
    }
    
    print(f"正在使用豆包生成封面图片 (模型: {model})...", file=sys.stderr)
    
    response = requests.post(url, headers=headers, json=request_data, timeout=120)
    
    if response.status_code >= 400:
        raise Exception(f"HTTP请求失败: 状态码 {response.status_code}, 响应: {response.text}")
    
    data = response.json()
    
    if data.get("error"):
        error_info = data["error"]
        raise Exception(f"豆包API错误: {error_info.get('message', '未知错误')}")
    
    # 解析响应
    images = data.get("data", [])
    if not images or not images[0].get("url"):
        raise Exception("生成图片失败: 响应中未找到图片URL")
    
    return {
        "success": True,
        "provider": "doubao",
        "model": model,
        "image_url": images[0]["url"],
        "revised_prompt": images[0].get("revised_prompt", prompt)
    }


def generate_cover_qwen(prompt: str, size: str = "1664*928", model: str = "qwen-image-2.0") -> dict:
    """
    使用千问生成封面图片
    
    Args:
        prompt: 图片提示词
        size: 图片尺寸
        model: 模型名称
        
    Returns:
        dict: 包含图片URL的响应数据
    """
    import requests
    
    # 获取API Key
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("缺少千问API凭证，请设置 DASHSCOPE_API_KEY 环境变量")
    
    # 构建请求
    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ]
        },
        "parameters": {
            "negative_prompt": "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。",
            "prompt_extend": True,
            "watermark": False,
            "size": size
        }
    }
    
    print(f"正在使用千问生成封面图片 (模型: {model}, 尺寸: {size})...", file=sys.stderr)
    
    response = requests.post(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        json=payload,
        timeout=120
    )
    
    response.raise_for_status()
    result = response.json()
    
    if result.get("code"):
        raise Exception(f"千问API错误: {result.get('message', '未知错误')}")
    
    choices = result.get("output", {}).get("choices", [])
    if not choices:
        raise Exception("生成图片失败: 响应中未找到图片数据")
    
    content = choices[0].get("message", {}).get("content", [])
    if not content or not content[0].get("image"):
        raise Exception("生成图片失败: 响应中未找到图片URL")
    
    image_url = content[0]["image"]
    
    return {
        "success": True,
        "provider": "qwen",
        "image_url": image_url,
        "model": model,
        "size": size
    }


def compress_downloaded_image(image_path: str, max_size_kb: int = 800) -> dict:
    """
    压缩下载的图片
    
    Args:
        image_path: 图片路径
        max_size_kb: 目标大小（KB）
        
    Returns:
        dict: 压缩结果
    """
    from PIL import Image
    import io
    
    original_size = os.path.getsize(image_path) / 1024
    
    # 如果已经小于目标大小，不压缩
    if original_size <= max_size_kb:
        print(f"图片大小 {original_size:.1f}KB 已满足要求，无需压缩", file=sys.stderr)
        return {
            "compressed": False,
            "original_size_kb": original_size,
            "final_size_kb": original_size
        }
    
    print(f"图片大小 {original_size:.1f}KB 超过 {max_size_kb}KB，开始压缩...", file=sys.stderr)
    
    # 打开图片
    img = Image.open(image_path)
    
    # 转换为 RGB
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # 渐进式压缩
    quality = 95
    min_quality = 75
    
    while quality >= min_quality:
        buffer = io.BytesIO()
        img.save(buffer, 'JPEG', quality=quality, optimize=True)
        size_kb = len(buffer.getvalue()) / 1024
        
        if size_kb <= max_size_kb:
            # 保存压缩后的图片
            with open(image_path, 'wb') as f:
                f.write(buffer.getvalue())
            
            compression_ratio = (1 - size_kb / original_size) * 100
            print(f"✅ 压缩完成: {original_size:.1f}KB → {size_kb:.1f}KB (质量: {quality}, 压缩率: {compression_ratio:.1f}%)", file=sys.stderr)
            
            return {
                "compressed": True,
                "original_size_kb": original_size,
                "final_size_kb": size_kb,
                "quality": quality,
                "compression_ratio": compression_ratio
            }
        
        # 降低质量
        if size_kb > max_size_kb * 1.5:
            quality -= 10
        elif size_kb > max_size_kb * 1.2:
            quality -= 5
        else:
            quality -= 2
    
    # 使用最低质量保存
    img.save(image_path, 'JPEG', quality=min_quality, optimize=True)
    final_size = os.path.getsize(image_path) / 1024
    compression_ratio = (1 - final_size / original_size) * 100
    
    print(f"⚠️  使用最低质量 {min_quality} 保存: {final_size:.1f}KB (压缩率: {compression_ratio:.1f}%)", file=sys.stderr)
    
    return {
        "compressed": True,
        "original_size_kb": original_size,
        "final_size_kb": final_size,
        "quality": min_quality,
        "compression_ratio": compression_ratio
    }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="生成公众号文章封面图片（支持豆包和千问）",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--prompt", "-p",
        required=True,
        help="图片提示词，描述封面内容"
    )
    
    parser.add_argument(
        "--provider",
        choices=["xingdong", "doubao", "qwen"],
        default="xingdong",
        help="图像生成服务提供商: xingdong (星洞AI，默认), doubao (豆包) 或 qwen (千问)"
    )
    
    # 豆包专用参数
    parser.add_argument(
        "--doubao-model",
        choices=["doubao-seedream-4-0-250828", "doubao-seedream-4-5-251128", "doubao-seedream-5-0-260128"],
        default="doubao-seedream-4-5-251128",
        help="豆包模型（仅豆包支持，默认: doubao-seedream-4-5-251128）"
    )
    
    # 千问专用参数
    parser.add_argument(
        "--size",
        choices=["1664*928", "1024*1024", "720*1280", "1280*720"],
        default="1664*928",
        help="图片尺寸（仅千问支持，默认: 1664*928）"
    )
    
    parser.add_argument(
        "--qwen-model",
        choices=["qwen-image-2.0", "qwen-image-2.0-pro"],
        default="qwen-image-2.0",
        help="千问模型（仅千问支持，默认: qwen-image-2.0）"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="下载并保存图片到指定路径（可选）"
    )
    
    parser.add_argument(
        "--compress",
        action="store_true",
        default=True,
        help="自动压缩图片（默认启用）"
    )
    
    parser.add_argument(
        "--max-size",
        type=int,
        default=800,
        help="压缩目标大小（KB），默认: 800"
    )
    
    args = parser.parse_args()
    
    try:
        # 根据 provider 选择生成方式
        if args.provider == "xingdong":
            result = generate_cover_xingdong(args.prompt)
        elif args.provider == "doubao":
            result = generate_cover_doubao(args.prompt, args.doubao_model)
        else:  # qwen
            result = generate_cover_qwen(args.prompt, args.size, args.qwen_model)
        
        # 如果指定了输出路径，下载图片
        if args.output:
            import requests
            print(f"正在下载图片到 {args.output}...", file=sys.stderr)
            response = requests.get(result["image_url"], timeout=60)
            response.raise_for_status()
            
            with open(args.output, 'wb') as f:
                f.write(response.content)
            
            original_size = os.path.getsize(args.output) / 1024
            print(f"✅ 图片已下载: {original_size:.1f}KB", file=sys.stderr)
            
            # 自动压缩
            if args.compress:
                compress_result = compress_downloaded_image(args.output, args.max_size)
                result["compression"] = compress_result
                result["local_path"] = args.output
        
        # 输出结果（JSON格式）
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)
        
    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
