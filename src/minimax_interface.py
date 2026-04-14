"""
MiniMax LLM 接口实现

基于 MiniMax API 实现 LLMInterface
API 格式: Anthropic Messages API (MiniMax-M2.7 reasoning model)
"""

import os
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# MiniMax API 配置
MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
MODEL_CHAT = "MiniMax-M2.7"


class MiniMaxInterface:
    """
    MiniMax LLM 接口实现(Anthropic Messages API 格式)
    
    MiniMax-M2.7 是推理模型,返回的 content 结构为:
    [{"type": "thinking", "thinking": "...", "signature": "..."}]
    或普通文本:
    [{"type": "text", "text": "..."}]
    """
    
    def __init__(self, api_key: str | None = None, model: str = MODEL_CHAT):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.model = model
        self._client: httpx.AsyncClient | None = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=MINIMAX_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=120.0,
            )
        return self._client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None
    
    def _parse_response(self, data: dict) -> str:
        """
        解析 MiniMax API 响应
        
        响应格式 (MiniMax-M2.7 reasoning model):
        {
          "content": [
            {"type": "thinking", "thinking": "...", "signature": "..."},
            {"type": "text", "text": "..."}
          ]
        }
        
        对于简单请求,可能只有 thinking block。
        对于需要最终输出的请求,应该有 text block。
        """
        content = data.get("content", [])
        
        if not content:
            return str(data)
        
        # 查找 text 类型的 block
        text_parts = []
        thinking_parts = []
        
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "thinking":
                # 推理过程,可选择是否包含
                thinking_parts.append(block.get("thinking", ""))
        
        if text_parts:
            return "\n".join(text_parts)
        
        # 如果没有 text block 但有 thinking,返回 thinking 末尾部分
        # (thinking 里包含推理过程和最终答案)
        if thinking_parts:
            # 取最后一个 thinking block(包含最终答案)
            return thinking_parts[-1]
        
        return str(data)
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
        """
        调用 LLM 生成内容(Anthropic Messages API)
        """
        client = self._get_client()
        target_model = model or self.model
        
        # 构建消息
        messages = []
        if system:
            messages.append({"role": "user", "content": system + "\n\n" + prompt})
        else:
            messages.append({"role": "user", "content": prompt})
        
        # Anthropic API payload
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        
        if temperature != 1.0:
            payload["temperature"] = temperature
        
        logger.debug(f"MiniMax API request: model={target_model}, max_tokens={max_tokens}")
        
        try:
            response = await client.post("/v1/messages", json=payload)
            response.raise_for_status()
            data = response.json()
            
            result = self._parse_response(data)
            logger.debug(f"MiniMax API response (first 100 chars): {result[:100]}")
            return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"MiniMax API HTTP error: {e.response.status_code} - {e.response.text[:500]}")
            raise
        except Exception as e:
            logger.error(f"MiniMax API error: {e}")
            raise
    
    async def generate_differentiation(
        self,
        scene_type: str,
        existing_tags: list[str],
        new_requirements: str
    ) -> str:
        """差异化定位(Step 2)"""
        system = """你是一个场景策划专家。你的任务是:
根据已有的同类场景标签,为新场景定义一个差异化的核心思想。

【硬约束 - 必须遵守】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论
- 禁止输出JSON或其他格式，仅输出纯文本

【核心要求 - 差异化】
1. 新场景必须与已有场景有明显区别,不要重复已有的氛围或标签
2. 必须为场景指定一个具体的"变体类型"（见下方列表），每个变体之间要有明显差异：
   - 酒馆变体: 昏暗角落/热闹大厅/宁静包间/喧嚣赌场/怀旧老店
   - 森林变体: 幽暗密林/阳光斑驳/迷雾笼罩/古树参天/花海秘境
   - 村庄变体: 宁静祥和/萧条破败/节庆热闹/废墟遗迹/边境要塞
   - 城镇变体: 繁华商业/阴暗巷陌/庄严官府/贫民窟/港口码头
   - 城堡变体: 威严正殿/阴暗地牢/华丽宴会厅/废弃阁楼/秘密通道
   - 洞穴变体: 潮湿滴水的矿洞/磷光闪烁的溶洞/炙热的火山岩浆洞/寒冰冻结的冰洞/充满陷阱的古墓
   - 其他类型请根据特点自拟变体

3. 必须包含至少3种感官通道的具体描写:
   - 视觉: 具体颜色(不是"暗"而是"墨绿")、光线(不是"亮"而是"斑驳光影")、形状
   - 听觉: 具体声音(不是"吵"而是"酒杯碰撞声和骰子滚动声")
   - 嗅觉: 具体气味(不是"香"而是"陈年橡木桶和麦酒发酵的酸香")
   - 触觉: 温度(不是"冷"而是"石壁传来刺骨寒意")、质地、空气湿度

4. 输出格式(纯文本，分3行):
   第一行: [变体类型]，如「酒馆·昏暗角落」
   第二行: 核心概念（1句话，包含至少3种感官的具体描写）
   第三行: 氛围关键词（3-5个，用逗号分隔）

示例输出:
酒馆·宁静包间
皮质沙发散发着陈年皮革的油光，壁炉火焰投下暖橙色的摇曳光影，空气中弥漫着雪莉酒的坚果香与木柴燃烧的淡淡焦香，厚重的隔音墙隔绝了外面嘈杂的人声，手触之处皆是温热的木质纹理。
温暖, 私密, 雪莉酒香, 皮革沙发, 隔音

示例输出（酒馆·热闹大厅）:
原木横梁上挂满了铜制酒杯，火把将整个大厅染成琥珀色，空气中麦酒、烤肉和烟草的味道混杂在一起，炉火噼啪作响，骰子和硬币的碰撞声此起彼伏，厚底靴踩在泥土地面上发出沉闷的声音。
喧嚣, 琥珀色火光, 麦酒烤肉香, 骰子声, 泥土地面

已有标签示例: 废弃矿洞 → [黑暗, 潮湿, 危险, 矿物, 塌方]
如果生成类似标签的新场景,会被拒绝。"""

        existing_tags_str = ', '.join(existing_tags) if existing_tags else '（暂无同类场景）'
        prompt = f"""已有{scene_type}类型场景的标签:
{existing_tags_str}

新场景需求:{new_requirements}

请为这个新场景输出:
1. 一个具体的变体类型（如酒馆→「昏暗角落」或「热闹大厅」）
2. 1句话的核心概念，必须包含至少3种感官的具体描写（颜色/光线/声音/气味/温度/质地）
3. 3-5个氛围关键词

严格按照格式输出，分3行，不要JSON。"""

        return await self.generate(prompt, system, temperature=0.85)

    async def generate_synopsis(
        self,
        core_concept: str,
        scene_type: str
    ) -> dict:
        """场景纲要生成(Step 3)

        Args:
            core_concept: 差异化定位的输出，包含3行内容:
                第1行: 变体类型，如「酒馆·昏暗角落」
                第2行: 核心概念（1句话，包含感官细节）
                第3行: 氛围关键词
        """
        # 解析 core_concept（支持新旧格式兼容）
        lines = core_concept.strip().split('\n')
        variant_type = ""
        core_desc = core_concept  # 默认为完整内容
        atmosphere_keywords = ""

        if len(lines) >= 3:
            # 新格式：变体类型 | 核心描述 | 关键词
            variant_type = lines[0].strip()
            core_desc = lines[1].strip()
            atmosphere_keywords = lines[2].strip()
        elif len(lines) == 1:
            # 旧格式（兼容）：只有核心描述
            core_desc = lines[0].strip()
            variant_type = f"{scene_type}·独特场所"
            atmosphere_keywords = ""

        system = """你是一个场景策划专家。基于核心概念,生成场景纲要。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

要求:
1. atmosphere 要用感官细节描写（视觉/听觉/嗅觉/触觉），不是抽象的"神秘"
2. danger_level 要诚实评估（low=安全, mid=有风险, high=高危, deadly=致命）
3. synopsis 50-100字,包含场景的核心画面，必须融入variant_type指定的变体氛围
4. tags 3-5个,体现场景特色和变体类型
5. unique_features 2-3个,必须是玩家可以直接感知的细节

输出格式(仅输出JSON,不要其他内容):
{
  "atmosphere": "氛围描述(用感官细节,1句话)",
  "danger_level": "low/mid/high/deadly",
  "synopsis": "场景纲要(50-100字,包含核心画面)",
  "tags": ["tag1", "tag2", "tag3"],
  "unique_features": ["特色1(玩家可感知)", "特色2"]
}"""

        prompt = f"""核心概念:{core_desc}
场景类型:{scene_type}
变体类型:{variant_type}
氛围关键词:{atmosphere_keywords}

请生成场景纲要,确保:
1. atmosphere 有具体的感官描写（融入variant_type的变体氛围）
2. danger_level 诚实反映危险程度
3. unique_features 是玩家能直接看到的细节
4. synopsis 要体现变体类型的独特性"""

        result = await self.generate(prompt, system, temperature=0.7)
        return self._parse_json_response(result)
    
    async def generate_detail(
        self,
        synopsis: str,
        scene_type: str,
        atmosphere: str,
        core_concept: str = "",
        existing_tags: list[str] | None = None
    ) -> dict:
        """详细内容生成(Step 4)

        Args:
            synopsis: 场景纲要
            scene_type: 场景类型
            atmosphere: 氛围关键词
            core_concept: 差异化核心概念（第2行的核心描述，用于提供具体方向）
            existing_tags: 已有的同类场景标签，用于避免重复
        """
        # 提取 core_concept 的第2行（核心描述）用于具体方向引导
        core_desc = core_concept
        lines = core_concept.strip().split('\n')
        if len(lines) >= 2:
            core_desc = lines[1].strip()  # 第2行是核心描述
            variant_type = lines[0].strip()  # 第1行是变体类型
        elif len(lines) == 1:
            core_desc = lines[0].strip()
            variant_type = f"{scene_type}·独特场所"

        # 构建已有场景标签上下文（用于差异化）
        existing_context = ""
        if existing_tags:
            unique_existing = list(set(existing_tags))[:10]  # 限制数量
            existing_context = f"\n\n【已有同类场景标签 - 必须避免重复】\n已使用: {', '.join(unique_existing)}\n\n【硬规则】新场景必须与上述已有标签完全不同！禁止使用任何已列出的标签作为主要特征！"

        system = f"""你是一个叙事写作专家。基于场景纲要,生成沉浸式的详细内容。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论
- 禁止以「推开X」「踏入X」「穿过X」「你推门而入」「一阵X中，你」等动作开场，这些是机械模板
- description 必须直接以场景画面/感官描写开头，而不是动作描写
- 禁止使用与已有场景相同的描写角度、光线效果、气味、温度感受{existing_context}

要求:
1. description 150-300字,用第二人称"你"描写,让玩家身临其境
2. 必须以场景画面/感官细节开头（例如："火光在墙壁上投下摇曳的影子，空气里弥漫着..."），不要以动作描写开头
3. 要有具体的环境细节（光线/声音/气味/温度/质地），且必须与variant_type指定的变体类型一致
4. 要有空间感（上下/远近/明暗对比）
5. npcs 2-3个,角色要有个性,不是泛泛的"商人"而是"眼神狡黠的老克劳德"
6. events 2-3个可触发事件,与场景特色相关
7. objects 2-4个可交互物品,让玩家可以"检查/拾取/使用"它们,丰富探索体验
   - 每个物品要有: name(名称), description(默认描述), can_pickup(bool), can_use(bool)
   - on_examine: 检查时的额外叙事
   - on_pickup: 拾取后的叙事(含 pickup_item/pickup_gold)
   - on_use: 使用后的效果叙事和 effects(效果列表)
   - effects格式: [{{"effect_type":"heal/add_gold/buff_attack/...","value":数值,"description":"描述"}}]
8. 【差异化要求】此场景是"{variant_type}"变体，必须体现与其他变体的本质区别

输出格式(仅输出JSON,不要其他内容):
{{
  "description": "详细场景描述(150-300字,第二人称,感官丰富)",
  "npcs": [
    {{"name": "NPC名", "role": "角色", "personality": "性格(具体)", "dialogue_style": "对话风格(1句话)"}}
  ],
  "events": [
    {{"trigger": "触发条件", "type": "事件类型", "description": "事件描述"}}
  ],
  "objects": [
    {{
      "name": "物品名称(如破旧的木桶)",
      "description": "物品的默认描述",
      "can_pickup": true或false,
      "can_use": true或false,
      "on_examine": "检查时的额外叙事",
      "on_pickup": "拾取后的叙事",
      "on_use": "使用后的效果叙事",
      "pickup_item": "拾取获得的物品名",
      "pickup_gold": 拾取获得的金币数,
      "rarity": "common/uncommon/rare",
      "effects": [{{"effect_type":"heal","value":10,"description":"HP恢复10点"}}]
    }}
  ]
}}"""

        prompt = f"""场景纲要:{synopsis}
场景类型:{scene_type}
氛围:{atmosphere}
变体类型:{variant_type}
核心概念:{core_desc}

请生成详细的场景内容,要求:
1. description 让玩家能"看见"这个地点，严格按照core_concept中的感官细节来描写，体现{variant_type}变体的独特性
2. NPC 要有独特个性
3. events 要与场景核心概念相关
4. objects 要有 2-4 个可交互物品,让场景更生动,物品可以是:
   - 环境物品(树洞、布告、雕像等)
   - 容器类(箱子、桶、袋子等)
   - 自然物品(草药、水源、矿石等)
   物品效果要简单: heal(加HP)、add_gold(加金币)、reveal(揭示线索)
5. 【关键】必须确保此场景的description、NPC、events与同一类型的其他变体有明显区别"""

        result = await self.generate(prompt, system, temperature=0.8)  # 提高 temperature 以增加随机性
        return self._parse_json_response(result)
    
    def _parse_json_response(self, text: str) -> dict:
        """从 LLM 响应中解析 JSON"""
        import re
        # 尝试找到 JSON 对象
        try:
            # 尝试提取 JSON 块(可能包含在thinking中)
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                # 如果找到单个对象,尝试解析
                for match in re.finditer(r'\{.*?\}', text, re.DOTALL):
                    try:
                        candidate = match.group()
                        parsed = json.loads(candidate)
                        if all(k in parsed for k in ["atmosphere", "danger_level", "synopsis"]):
                            return parsed
                    except json.JSONDecodeError:
                        continue
            
            # 直接尝试解析整段文字
            parsed = json.loads(text)
            return parsed
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}, text: {text[:300]}")
        raise ValueError(f"Failed to parse JSON from response: {text[:300]}")


# 全局实例(延迟初始化)
_global_interface: "MiniMaxInterface | None" = None


def get_minimax_interface(api_key: str | None = None) -> "MiniMaxInterface":
    """获取全局 MiniMaxInterface 实例"""
    global _global_interface
    if _global_interface is None:
        _global_interface = MiniMaxInterface(api_key=api_key)
    return _global_interface


async def close_minimax_interface():
    """关闭全局 MiniMaxInterface"""
    global _global_interface
    if _global_interface:
        await _global_interface.close()
        _global_interface = None
