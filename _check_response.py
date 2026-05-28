#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import urllib.request
import sys

resp = urllib.request.urlopen('http://127.0.0.1:5000')
body = resp.read()
ct = resp.headers.get('Content-Type', 'N/A')

print('HTTP Status:', resp.status)
print('Content-Type:', ct)
print('Content-Length:', len(body))
print()
print('=== First 500 bytes (repr) ===')
print(repr(body[:500]))
print()
print('=== First 500 bytes (decode try) ===')
try:
    text = body.decode('utf-8')
    print('UTF-8 decode: OK')
    print('Has meta charset:', 'charset="UTF-8"' in text or 'charset="utf-8"' in text)
    # Check for mojibake - Chinese characters encoded as wrong encoding
    mojibake_patterns = ['é', 'ç', 'â', 'å', '°', '±', '²', '³']
    found = [p for p in mojibake_patterns if p in text[:2000]]
    if found:
        print('WARNING: possible mojibake detected:', found)
    # Show first 10 lines
    lines = text.split('\n')[:10]
    for i, line in enumerate(lines, 1):
        print(f'{i}: {line[:100]}')
except Exception as e:
    print('UTF-8 decode FAILED:', e)
    print('Trying GBK...')
    try:
        text = body.decode('gbk')
        print('GBK decode: OK')
        print('First 300 chars:', text[:300])
    except:
        print('GBK also failed')
