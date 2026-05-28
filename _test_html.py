import urllib.request

r = urllib.request.urlopen('http://127.0.0.1:5001/')
html = r.read().decode('utf-8')

print(f'Total length: {len(html)}')
print(f'Has </head>: {"</head>" in html}')
print(f'Has <body>: {"<body" in html}')

idx_vue = html.find('vue.global.prod.js')
idx_axios = html.find('axios.min.js')
idx_body = html.find('<body')
idx_script = html.find('<script>')  # inline script start

print(f'\nVue script tag at char: {idx_vue}')
print(f'Axios script tag at char: {idx_axios}')
print(f'<body> at char: {idx_body}')
print(f'Inline <script> at char: {idx_script}')

# Check if there's a </head> between scripts and body
if idx_axios > 0:
    after_axios = html[idx_axios:idx_axios+500]
    print(f'\nAfter axios script (300 chars):')
    print(after_axios[:300])

# Check the end of file - is it complete?
last200 = html[-200:]
print(f'\nLast 200 chars of HTML:')
print(last200)
