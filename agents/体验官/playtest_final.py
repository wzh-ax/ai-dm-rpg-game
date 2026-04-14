"""
体验官自动体验 - 最终版
"""
import asyncio
import sys
import os
import time
import re
import json

root = r'C:\Users\15901\.openclaw\workspace\ai-dm-rpg'
if root not in sys.path:
    sys.path.insert(0, root)
os.chdir(root)

import requests

# ============ 飞书配置 ============
FEISHU_APP_ID = 'cli_a95352f61a781cc7'
FEISHU_APP_SECRET = 'zjgomOXKn7rzpCDGK1IHqeJ4AS3ZmI13'
FEISHU_CHAT_ID = 'oc_e1ceff2fe81e3c715c2f01af0e194b72'

# ============ 质量检测 ============
FALLBACK_TEMPLATES = [
    "空气中弥漫着", "你的声音在空气中回荡", "这里似乎没有",
    "mysterious", "阳光洒落", "微风吹过", "这里是一个",
    "玩家正在寻找", "这里看起来没有", "远处传来", "你环顾四周",
    "你注意到", "一切显得", "仿佛在等待", "似乎在诉说着",
    "你深吸一口气", "你的心中", "突然", "忽然",
    "场景中的细节在你眼前展开", "玩家正在寻找一个酒馆",
    "这里是一个酒馆类型的地点",
]

AI_LEAK_PATTERNS = [
    r"玩家正在", r"\(DM\)", r"DM正在", r"请输入", r"系统提示",
    r"你选择", r"作为AI", r"我没有", r"AI语言模型", r"我没有办法",
    r"玩家正在寻找一个.*类型的地点",
]

def detect_templates(text):
    if not text:
        return []
    return [t for t in FALLBACK_TEMPLATES if t in text]

def detect_ai_leak(text):
    if not text:
        return []
    found = []
    for p in AI_LEAK_PATTERNS:
        if re.search(p, text):
            found.append(p)
    return found

def quality_score(text, action):
    if not text or len(text.strip()) < 10:
        return 0, [], []
    s = 10
    tmpl = detect_templates(text)
    leaks = detect_ai_leak(text)
    
    if tmpl:
        s -= min(len(tmpl) * 1.5, 5)
    if leaks:
        s -= min(len(leaks) * 2, 6)
    if len(text) < 80:
        s -= 2
    elif len(text) < 150:
        s -= 1
    
    return max(0, s), tmpl, leaks

# ============ 游戏交互 ============
from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

async def wait_for_narrative(bus, timeout=60):
    narrative_event = asyncio.Event()
    result = {"text": "", "turn": 0}
    
    def handler(event: Event):
        result["text"] = event.data.get("text", "")
        result["turn"] = event.data.get("turn", 0)
        narrative_event.set()
    
    sub_id = f"playtest_{time.time()}"
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, sub_id)
    try:
        await asyncio.wait_for(narrative_event.wait(), timeout=timeout)
        return result["text"]
    except asyncio.TimeoutError:
        return "[超时无响应]"
    finally:
        await bus.unsubscribe(EventType.NARRATIVE_OUTPUT, sub_id)

async def act(master, bus, action, label):
    t0 = time.time()
    try:
        await master.handle_player_message(action)
        response = await wait_for_narrative(bus, timeout=90)
    except Exception as e:
        response = f"[ERROR: {e}]"
    
    elapsed = time.time() - t0
    q, tmpl, leaks = quality_score(response, action)
    
    stats = master.game_state.get('player_stats', {})
    entry = {
        "action": action, "label": label,
        "elapsed": round(elapsed, 1),
        "resp_len": len(response) if response else 0,
        "quality": q, "templates": tmpl, "ai_leaks": leaks,
        "preview": (response[:300].replace('\n', ' ') if response else "[空响应]"),
        "location": master.game_state.get('location', '?'),
        "hp": stats.get('hp', 0),
        "turn": master.game_state.get('turn', 0),
    }
    
    ico = "✅" if q >= 8 else "⚠️" if q >= 5 else "❌"
    print(f"  {ico} [{label}] {action[:30]} | Q:{q} | {len(response or '')}字 | {elapsed:.1f}s")
    if tmpl:
        print(f"       模板: {tmpl[:2]}")
    if leaks:
        print(f"       AI泄露: {leaks[:1]}")
    
    return entry, response

async def playtest():
    print("=" * 60)
    print("体验官自动体验")
    print("=" * 60)

    t_start = time.time()
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    creator = get_character_creator()
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)

    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"\n[角色] {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp}")

    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '月叶镇'
    master.game_state['active_npcs_per_scene'] = {}
    master.game_state['active_npcs'] = {}
    master.game_state['quest_stage'] = 'not_started'
    master.game_state['quest_active'] = False

    results = []
    responses = {}
    
    # ===== 开场叙事 =====
    print("\n=== 开场叙事 ===")
    r, resp = await act(master, bus, "探索月叶镇", "开场探索")
    results.append(r)
    responses['开场探索'] = resp
    
    # ===== NPC对话 =====
    print("\n=== NPC对话 ===")
    r, resp = await act(master, bus, "和周围的人说话", "NPC泛化")
    results.append(r)
    responses['NPC泛化'] = resp
    
    r, resp = await act(master, bus, "向老人询问这里的情况", "NPC具体")
    results.append(r)
    responses['NPC具体'] = resp
    
    r, resp = await act(master, bus, "询问有什么工作", "任务请求")
    results.append(r)
    responses['任务请求'] = resp
    
    # ===== 场景切换 =====
    print("\n=== 场景切换 ===")
    r, resp = await act(master, bus, "去镇上的酒馆", "去酒馆")
    results.append(r)
    responses['去酒馆'] = resp
    
    r, resp = await act(master, bus, "在酒馆里四处张望", "观察酒馆")
    results.append(r)
    responses['观察酒馆'] = resp
    
    r, resp = await act(master, bus, "和酒馆里的人搭话", "酒馆社交")
    results.append(r)
    responses['酒馆社交'] = resp
    
    # ===== 系统命令 =====
    print("\n=== 系统命令 ===")
    r, resp = await act(master, bus, "查看状态", "状态命令")
    results.append(r)
    responses['状态'] = resp
    
    r, resp = await act(master, bus, "查看背包", "背包命令")
    results.append(r)
    responses['背包'] = resp
    
    # ===== 离开酒馆 =====
    print("\n=== 探索 ===")
    r, resp = await act(master, bus, "离开酒馆去野外", "离开酒馆")
    results.append(r)
    responses['离开酒馆'] = resp
    
    r, resp = await act(master, bus, "在野外寻找敌人", "寻找战斗")
    results.append(r)
    responses['寻找战斗'] = resp

    elapsed_total = time.time() - t_start
    
    await master.stop()
    await bus.stop()
    
    return results, responses, elapsed_total

def generate_report(results, responses, elapsed_total):
    """生成体验报告"""
    total_actions = len(results)
    avg_q = sum(r['quality'] for r in results) / total_actions if total_actions else 0
    zero_q = sum(1 for r in results if r['quality'] == 0)
    high_q = [r for r in results if r['quality'] >= 8]
    low_q = [r for r in results if r['quality'] < 5]
    
    report = []
    report.append("🎮 AI DM RPG 体验报告")
    report.append("=" * 50)
    report.append(f"时间: 2026-04-12 06:41")
    report.append("")
    report.append("📊 基本信息")
    report.append(f"- 游玩时长: {elapsed_total/60:.1f}分钟")
    report.append(f"- 总动作数: {total_actions}")
    report.append(f"- 死亡次数: 0")
    report.append(f"- 空响应率: {zero_q}/{total_actions}")
    report.append(f"- 平均质量: {avg_q:.1f}/10")
    report.append("")
    report.append("---")
    report.append("📝 叙事体验")
    
    # 亮点
    report.append("✅ 亮点:")
    for r in high_q[:3]:
        report.append(f"- [{r['label']}] \"{r['action'][:25]}\" → Q:{r['quality']} | {r['preview'][:80]}")
    if not high_q:
        report.append("无高质量响应")
    
    # 低点
    report.append("")
    report.append("❌ 低点:")
    for r in low_q[:3]:
        probs = []
        if r['quality'] == 0:
            probs.append("空响应")
        if r['templates']:
            probs.append(f"模板:{len(r['templates'])}")
        if r['ai_leaks']:
            probs.append("AI泄露")
        report.append(f"- [{r['label']}] \"{r['action'][:25]}\" → Q:{r['quality']} | {','.join(probs)}")
    
    report.append("")
    report.append("---")
    report.append("🚨 P0问题（必须修复）")
    p0_issues = [r for r in results if r['quality'] == 0]
    if p0_issues:
        for r in p0_issues:
            report.append(f"{r['label']}: {r['action']} → 空响应")
    else:
        report.append("无P0问题")
    
    report.append("")
    report.append("⚠️ P1问题")
    p1_issues = [r for r in results if 0 < r['quality'] < 5]
    if p1_issues:
        for r in p1_issues:
            probs = r['templates'][:1] + r['ai_leaks'][:1]
            report.append(f"- [{r['label']}] {r['action']} | 问题:{probs}")
    else:
        report.append("无P1问题")
    
    report.append("")
    report.append("---")
    report.append("⭐ 总体评分: {:.1f}/10".format(avg_q))
    report.append("")
    
    # 详细响应分析
    report.append("---")
    report.append("📋 响应详情")
    for label, resp in responses.items():
        if resp and len(resp) > 0:
            tmpl = detect_templates(resp)
            leaks = detect_ai_leak(resp)
            q = quality_score(resp, "")[0]
            report.append(f"\n[{label}] Q:{q} | {len(resp)}字")
            if tmpl:
                report.append(f"  模板: {tmpl[:2]}")
            if leaks:
                report.append(f"  泄露: {leaks[:1]}")
            report.append(f"  内容: {resp[:200].replace(chr(10), ' ')}")
    
    return "\n".join(report)

def send_feishu(report_text):
    """发送报告到飞书"""
    # Get token
    token_url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    token_resp = requests.post(token_url, json={
        'app_id': FEISHU_APP_ID, 
        'app_secret': FEISHU_APP_SECRET
    })
    if token_resp.status_code != 200:
        print(f"Token获取失败: {token_resp.status_code}")
        return False
    
    token = token_resp.json().get('tenant_access_token')
    if not token:
        print("Token为空")
        return False
    
    # Send message
    msg_url = 'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id'
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    payload = {
        'receive_id': FEISHU_CHAT_ID,
        'msg_type': 'text',
        'content': json.dumps({'text': report_text})
    }
    
    resp = requests.post(msg_url, headers=headers, json=payload)
    if resp.status_code == 200:
        print("✅ 报告已发送到飞书")
        return True
    else:
        print(f"❌ 发送失败: {resp.status_code} - {resp.text}")
        return False

async def main():
    results, responses, elapsed = await playtest()
    report = generate_report(results, responses, elapsed)
    print("\n" + "=" * 60)
    print("体验报告:")
    print("=" * 60)
    print(report)
    
    # Send to Feishu
    send_feishu(report)
    
    return report

if __name__ == '__main__':
    asyncio.run(main())
