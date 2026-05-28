import urllib.request

for path in ['/static/vue.global.prod.js', '/static/axios.min.js']:
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:5001{path}')
        data = r.read()
        is_html = b'<!DOCTYPE' in data or b'<html' in data
        has_vue = b'Vue' in data or b'axios' in data
        print(f'{path}: {len(data)} bytes, isHTML={is_html}, hasContent={has_vue}')
        if is_html:
            print(f'  ERROR! Got HTML: {data[:300].decode(errors="replace")}')
    except Exception as e:
        print(f'{path}: ERROR - {e}')
