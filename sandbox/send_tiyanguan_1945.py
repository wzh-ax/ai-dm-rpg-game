# -*- coding: utf-8 -*-
import sys, json, time, requests
sys.stdout.reconfigure(encoding='utf-8')

app_id = 'cli_a95352f61a781cc7'
app_secret = 'zjgomOXKn7rzpCDGK1IHqeJ4AS3ZmI13'

token_url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
token_resp = requests.post(token_url, json={'app_id': app_id, 'app_secret': app_secret}, timeout=10)
token_data = token_resp.json()
tenant_token = token_data.get('tenant_access_token', '')

chat_id = 'oc_e1ceff2fe81e3c715c2f01af0e194b72'
url = f'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id'

headers = {'Authorization': f'Bearer {tenant_token}', 'Content-Type': 'application/json'}

text = """【体验官报告 19:45】已完成

综合评分：6/10
无响应率：36.8%（7/19 操作无响应）
测试耗时：170.4秒

P0问题（7个）：
1. 和酒馆老板说话 -> 空
2. 前往森林 -> 空
3. 搜索周围 -> 空
4. 攻击哥布林 -> 空
5. 使用治疗药水 -> 空
6. 查看四周 -> 空
7. 询问任务 -> 空

正常功能：
- 系统命令（状态/背包/任务/帮助/商店）全部正常
- Tutorial、探索、场景切换、战斗防御均正常

完整报告：tasks/tiyanguan_report_20260412_1945.md"""

paylaod = {
    'receive_id': chat_id,
    'msg_type': 'text',
    'content': json.dumps({'text': text})
}

resp = requests.post(url, headers=headers, json=paylaod, timeout=10)
print('Status:', resp.status_code)
print('Response:', resp.text)
