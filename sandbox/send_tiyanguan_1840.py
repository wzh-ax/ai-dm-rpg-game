# -*- coding: utf-8 -*-
import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

app_id = 'cli_a95352f61a781cc7'
app_secret = 'zjgomOXKn7rzpCDGK1IHqeJ4AS3ZmI13'

token_url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
token_resp = requests.post(token_url, json={'app_id': app_id, 'app_secret': app_secret})
print('Token status:', token_resp.status_code)
token = token_resp.json().get('tenant_access_token')
if not token:
    print('获取 token 失败')
    sys.exit(1)

report = """## 🎮 体验官报告 - 2026-04-12 18:58

**综合评分：1.5/10** ❌

---

### 测试概况
- 测试时间：2026-04-12 18:40 GMT+8
- 角色：体验官（人类战士，HP 22/22）
- 总操作：21 个
- 无响应率：**76%**（16/21 无响应）
- 单元测试：73 通过 ✅

---

### P0 - 阻塞问题（4项）

**P0-1：系统命令全部无响应**
- 状态 / 背包 / 任务 / 帮助 → 全部 (无响应)
- 上轮（13:37）已报告，**本次仍未修复**

**P0-2：NPC 交互全部无响应**
- "和镇长说话" / "和酒馆老板说话" → 全部无响应
- 上轮报告崩溃 (`'str' object has no attribute 'value'`)，本次不崩溃但**仍无输出**

**P0-3：场景切换后全部无响应**
- "去酒馆" / "去森林" → 无响应，切换后所有后续操作也无响应

**P0-4：战斗系统无响应**
- 攻击 / 防御 / 使用道具 → 全部无响应
- 战斗根本未触发

---

### P1 - 影响体验（2项）

**P1-1：有效响应是"回声"而非叙事**
- 有响应时输出：`[回合 2] 你说道："开始游戏"` + `场景中的细节在你眼前展开...`
- 不是 DM 叙事，是原文回显+占位符

**P1-2：场景定位错误**
- 在月叶镇输入"看看周围"，收到的是森林场景描述
- 内容为模板："一个森林类型的地点:玩家正在寻找一个森林"

---

### 亮点 ✅
- 代码可导入，不崩溃
- 角色创建正常
- 架构文档完善

---

### 结论
**游戏当前不可玩**。绝大多数玩家操作静默无响应，无响应率从上轮的 47% **恶化到 76%**。建议立即诊断 `handle_player_message` 的事件路由路径。

报告文件：`workspace-ai-dm-rpg/tasks/tiyanguan_report_20260412.md`"""

msg_url = 'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

payload = {
    'receive_id': 'oc_e1ceff2fe81e3c715c2f01af0e194b72',
    'msg_type': 'text',
    'content': json.dumps({'text': report})
}
resp = requests.post(msg_url, headers=headers, json=payload)
print('Send status:', resp.status_code)
print(resp.json().get('msg', resp.text))
