"""检查体彩在售比赛的API"""
import requests, json, re

headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
    'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/',
}

# 获取dataTransfer.js看API配置
try:
    resp = requests.get('https://static.sporttery.cn/res_1_0/jcwm/default/jc/jsq/dataTransfer.js', headers=headers, timeout=10)
    js = resp.text
    # 找所有URL
    urls = re.findall(r'["\']([^"\']*(?:gateway|webapi|qry|api)[^"\']*)["\']', js)
    for u in set(urls):
        print(f'API: {u[:150]}')
    # 找所有key的配置
    keys = re.findall(r'(\w+)\s*:\s*["\']([^"\']+)["\']', js)
    for k, v in keys:
        if any(w in k.lower() for w in ['url', 'api', 'host', 'path', 'gateway']):
            print(f'{k}: {v[:120]}')
except Exception as e:
    print(f'Error: {e}')

# 也检查lotJs.js
print()
try:
    resp = requests.get('https://static.sporttery.cn/res_1_0/jcwm/default/jc/jsq/lotJs.js', headers=headers, timeout=10)
    js = resp.text
    urls = re.findall(r'["\']([^"\']*(?:gateway|webapi|qry|api)[^"\']*)["\']', js)
    for u in set(urls):
        print(f'lotJs URL: {u[:150]}')
except Exception as e:
    print(f'Error: {e}')
