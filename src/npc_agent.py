"""
NPC Agent - NPC 生成与对话子 Agent

实现 NPC 生成和对话流程:
1. NPC 登记查询(查询同类 NPC 索引)
2. 差异化定位(LLM)
3. NPC 人设生成(LLM)
4. 对话生成(LLM)

NPC 对话触发流程:
- 玩家与 NPC 交互 → EventBus 发布 NPC_DIALOGUE 事件 → NPCAgent 处理

场景差异化增强:
- 随机 NPC 性格偏移:同名 NPC 每次出现性格略有不同，对话风格随之变化
"""

import asyncio
import logging
import json
import random
import uuid
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from .event_bus import Event, EventType, get_event_bus
from .hooks import get_hook_registry, HookNames
from .minimax_interface import MiniMaxInterface
from .logging_system import get_logger

logger = logging.getLogger(__name__)


# ============================================================================
# NPC 性格偏移池 - 随机性格偏移模板
# ============================================================================

_PERSONALITY_OFFSET_POOL: dict[str, list[str]] = {
    # 基础性格 → 可能的偏移变体
    "friendly": [
        "热情洋溢，对陌生人毫无防备",
        "表面友好，但眼底藏着一丝警惕",
        "友善但略显疲惫，似乎心事重重",
        "和善可亲，不过偶尔会走神",
        "友好热情，但有时过于热心让人不适",
    ],
    "neutral": [
        "态度中立，不冷不热",
        "看似中立，实则有自己的判断",
        "淡然处之，与己无关的事不多过问",
        "平静如常，不带明显情绪色彩",
        "中立但细心观察着周围的一切",
    ],
    "hostile": [
        "敌意明显，时刻准备争吵",
        "表面敌对，实则是自我保护",
        "态度恶劣，但并非完全不可理喻",
        "充满敌意，目光中带着怨恨",
        "敌视陌生人，但对自己的朋友极为忠诚",
    ],
    "fearful": [
        "胆小怕事，总是往最坏的方向想",
        "惶恐不安，不时紧张地四处张望",
        "恐惧缠身，说话时声音都在发抖",
        "惊弓之鸟，一点风吹草动就惊慌失措",
        "表面恐惧，实则是因为知道什么秘密",
    ],
    "greedy": [
        "见钱眼开，时刻盘算着利益得失",
        "贪婪成性，但聪明地不表现得太明显",
        "对金钱有执念，眼中闪过精明的光",
        "贪财但讲信用，买卖分明",
        "唯利是图，但不会做亏本买卖",
    ],
    "curious": [
        "好奇心旺盛，什么都想打听",
        "求知欲强，但分不清轻重缓急",
        "对陌生事物充满兴趣，眼睛亮了起来",
        "好奇但谨慎，先观察再行动",
        "爱打听消息，但不会泄露自己知道的",
    ],
}

# 说话风格偏移
_SPEECH_STYLE_OFFSET: dict[str, list[str]] = {
    "圆滑老练": [
        "说话滴水不漏，让你找不到破绽",
        "言辞圆滑，每句话都经过深思熟虑",
        "老练世故，话说得漂亮却不给实质",
        "圆滑而热情，让人挑不出毛病",
    ],
    "吟游诗人般": [
        "语调如歌，说什么都像在吟诗",
        "抑扬顿挫，话语中带着韵律感",
        "诗意盎然，连日常对话都像在讲故事",
        "出口成章，让人听得入神",
    ],
    "低沉神秘": [
        "声音低沉，像是在刻意压着嗓子说话",
        "话语神秘，让你需要猜测其中的含义",
        "声线低沉，每句话都像在透露什么秘密",
        "低沉而缓慢，给人一种压抑感",
    ],
    "优雅缓慢": [
        "谈吐优雅，说话时带着从容不迫的节奏",
        "语言考究，每个词都用得恰到好处",
        "优雅从容，不急不徐地表达",
        "措辞优雅，似乎受过良好的教育",
    ],
    "简洁有力": [
        "惜字如金，每句话都简短而有力",
        "言语简洁，直奔主题不绕弯子",
        "说话干净利落，绝不拖泥带水",
        "简洁有力，像是习惯了军旅生活",
    ],
    "急促紧张": [
        "话语急促，似乎急于表达什么",
        "说得又快又急，让你很难跟上节奏",
        "语速很快，偶尔还会结巴",
        "紧张时说话会加快，像是在掩饰什么",
    ],
    "稳重慈祥": [
        "语气稳重，让你感到安心",
        "语调平和，像是在安抚一个孩子",
        "声音缓慢而有力，透着长辈的关怀",
        "稳重中带着温和，让人如沐春风",
    ],
    "洪亮有力": [
        "声音洪亮，在嘈杂环境中也能听清",
        "说话掷地有声，让人无法忽视",
        "声如洪钟，带着一股豪迈之气",
        "嗓音洪亮，中气十足",
    ],
    "稚嫩清脆": [
        "声音稚嫩，还带着孩子的奶声奶气",
        "清脆如铃，让人心情不自觉地放松",
        "声音轻快，像只小鸟在啼叫",
        "稚嫩却认真，努力学着大人说话",
    ],
    "严肃正式": [
        "语气严肃，措辞正式，一丝不苟",
        "说话一本正经，不带任何玩笑成分",
        "庄重而严肃，让人不敢造次",
        "正式场合的语气，字斟句酌",
    ],
    "礼貌热情": [
        "热情周到，礼貌中透着真诚",
        "礼貌有加，让人感觉被重视",
        "待客热情，但不失分寸感",
        "礼貌而健谈，不会冷落任何客人",
    ],
    "优雅矜持": [
        "谈吐优雅，保持着贵族的矜持",
        "姿态高傲，但不失基本礼貌",
        "优雅端庄，一举一动都很有教养",
        "矜持地微笑着，不轻易表露情绪",
    ],
    "正式威严": [
        "威严赫赫，让人不由自主地肃然起敬",
        "措辞正式而不失威严，令人信服",
        "说话带着上位者的威严，不怒自威",
        "声线威严，有不容置疑的权威感",
    ],
    "柔和恭敬": [
        "语气柔和而恭敬，小心翼翼地措辞",
        "恭敬但不过分卑微，态度恰到好处",
        "柔和的语调，像是在伺候贵客",
        "恭敬而细致，不放过任何一个细节",
    ],
    "低沉忧郁": [
        "语调低沉，透着挥之不去的忧郁",
        "声音里带着感伤，像是在回忆往事",
        "忧郁而缓慢，让人感到一阵惆怅",
        "低沉的话语中，隐藏着不为人知的故事",
    ],
    "平静深邃": [
        "平静如深潭，话语深邃难测",
        "语调平静，但内容往往意味深长",
        "平静深邃，像是在思考着什么",
        "声音平静，给人一种超然物外的感觉",
    ],
    "颤抖急促": [
        "声音颤抖，说话急促而慌乱",
        "语无伦次，像是被吓坏了",
        "惊恐中带着颤抖，让人担心他的状态",
        "颤抖的声音急促地诉说着什么",
    ],
    "阴冷低沉": [
        "声线阴冷，让人脊背发凉",
        "低沉的话语带着寒意，令人不安",
        "阴冷的语调，像是从黑暗中传来",
        "声音低沉而冰冷，让人感到不适",
    ],
}

# 默认偏移（未找到特定风格时使用）
_DEFAULT_SPEECH_OFFSET = [
    "说话时带着一种难以捉摸的韵味",
    "言语间透露出不凡的气质",
    "措辞独特，让人影响深刻",
    "话音中带着某种说不清的意味",
]


class NPCRole(Enum):
    """NPC 角色类型"""
    MERCHANT = "merchant"      # 商人
    GUARD = "guard"            # 守卫
    VILLAGER = "villager"      # 村民
    NOBLE = "noble"            # 贵族
    SCHOLAR = "scholar"        # 学者
    MYSTIC = "mystic"          # 神秘人
    ADVENTURER = "adventurer"  # 冒险者
    CRIMINAL = "criminal"      # 犯罪分子
    OFFICIAL = "official"      # 官员


class NPCDisposition(Enum):
    """NPC 态度"""
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    FEARFUL = "fearful"
    GREEDY = "greedy"
    CURIOUS = "curious"


@dataclass
class NPCMetadata:
    """NPC 元数据"""
    id: str
    name: str
    role: str  # NPCRole.value
    disposition: str  # NPCDisposition.value
    core_concept: str  # 核心性格/背景
    tags: list[str] = field(default_factory=list)
    appearance: str = ""  # 外貌描述
    personality: str = ""  # 性格详细描述
    speech_style: str = ""  # 说话风格
    secrets: list[str] = field(default_factory=list)  # 隐藏信息
    knowledge: list[str] = field(default_factory=list)  # 掌握的信息
    quests: list[dict] = field(default_factory=list)  # 可提供的任务
    dialogue: str = ""  # 初始对话内容
    created_at: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "disposition": self.disposition,
            "core_concept": self.core_concept,
            "tags": self.tags,
            "appearance": self.appearance,
            "personality": self.personality,
            "speech_style": self.speech_style,
            "secrets": self.secrets,
            "knowledge": self.knowledge,
            "quests": self.quests,
            "dialogue": self.dialogue,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NPCMetadata":
        return cls(**data)
    
    def can_share_info(self, info_tag: str) -> bool:
        """判断 NPC 是否会分享特定信息"""
        import random as rnd
        if info_tag in self.knowledge:
            disposition_modifier = {
                NPCDisposition.FRIENDLY: 0.9,
                NPCDisposition.CURIOUS: 0.7,
                NPCDisposition.NEUTRAL: 0.5,
                NPCDisposition.GREEDY: 0.4,
                NPCDisposition.FEARFUL: 0.2,
                NPCDisposition.HOSTILE: 0.1,
            }.get(NPCDisposition(self.disposition), 0.5)
            return rnd.random() < disposition_modifier
        return False


class NPCRegistry:
    """
    NPC 注册表
    
    管理所有已生成 NPC 的索引,支持按类型和标签查询
    """
    
    def __init__(self, storage_path: str = "data/npcs"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, list[str]] = {}  # role -> [npc_id, ...]
        self._npcs: dict[str, NPCMetadata] = {}
    
    def _get_index_file(self) -> Path:
        return self.storage_path / "index.json"
    
    def _get_npc_file(self, npc_id: str) -> Path:
        return self.storage_path / f"{npc_id}.json"
    
    async def load(self):
        """从磁盘加载索引"""
        index_file = self._get_index_file()
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                self._index = json.load(f)
        
        for npc_ids in self._index.values():
            for npc_id in npc_ids:
                npc_file = self._get_npc_file(npc_id)
                if npc_file.exists():
                    with open(npc_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._npcs[npc_id] = NPCMetadata.from_dict(data)
        
        logger.info(f"Loaded {len(self._npcs)} NPCs from registry")
    
    async def save(self):
        """保存索引到磁盘"""
        with open(self._get_index_file(), "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
        
        for npc_id, npc in self._npcs.items():
            with open(self._get_npc_file(npc_id), "w", encoding="utf-8") as f:
                json.dump(npc.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Saved {len(self._npcs)} NPCs to registry")
    
    def register(self, npc: NPCMetadata):
        """注册新 NPC"""
        self._npcs[npc.id] = npc
        
        if npc.role not in self._index:
            self._index[npc.role] = []
        if npc.id not in self._index[npc.role]:
            self._index[npc.role].append(npc.id)
        
        logger.debug(f"Registered NPC: {npc.name} (id={npc.id}, role={npc.role})")
    
    def get_by_id(self, npc_id: str) -> NPCMetadata | None:
        """通过 ID 获取 NPC"""
        return self._npcs.get(npc_id)
    
    def get_by_role(self, role: str) -> list[NPCMetadata]:
        """获取指定角色的所有 NPC"""
        npc_ids = self._index.get(role, [])
        return [self._npcs[nid] for nid in npc_ids if nid in self._npcs]
    
    def get_all_tags(self, role: str) -> list[str]:
        """获取同类 NPC 的所有标签(用于差异化)"""
        npcs = self.get_by_role(role)
        all_tags = []
        for npc in npcs:
            all_tags.extend(npc.tags)
        return list(set(all_tags))
    
    def search(self, query: str) -> list[NPCMetadata]:
        """简单搜索(未来扩展为语义搜索)"""
        results = []
        query_lower = query.lower()
        for npc in self._npcs.values():
            if (query_lower in npc.name.lower() or
                query_lower in npc.role.lower() or
                query_lower in npc.core_concept.lower() or
                any(query_lower in tag.lower() for tag in npc.tags)):
                results.append(npc)
        return results


class LLMInterface(MiniMaxInterface):
    """
    LLM 接口抽象(基于 MiniMax API)
    
    继承自 MiniMaxInterface,复用其全部实现
    """
    
    def __init__(self, api_key: str | None = None):
        super().__init__(api_key=api_key)
    
    async def generate(self, prompt: str, system: str = "") -> str:
        """调用 LLM 生成内容"""
        return await MiniMaxInterface.generate(self, prompt, system)


class NPCAgent:
    """
    NPC 子 Agent
    
    负责 NPC 生成和对话处理:
    - 懒生成:场景需要时生成对应 NPC
    - 对话处理:响应玩家与 NPC 的交互
    """
    
    def __init__(
        self,
        registry: NPCRegistry | None = None,
        llm: LLMInterface | None = None,
        api_key: str | None = None,
    ):
        self.registry = registry or NPCRegistry()
        self.llm = llm or LLMInterface(api_key=api_key)
        self._event_bus = None
        self._hooks = None
        self._subscriber_id = f"npc_agent_{id(self)}"
        # 对话上下文缓存(npc_id -> recent_dialogues)
        self._dialogue_cache: dict[str, list[dict]] = {}
        self._max_cache_size = 10
    
    async def initialize(self):
        """初始化:注册事件订阅"""
        self._event_bus = get_event_bus()
        self._hooks = get_hook_registry()
        
        # 加载已有 NPC
        await self.registry.load()
        
        # 注册 NPC 对话事件订阅
        await self._event_bus.subscribe(
            EventType.NPC_DIALOGUE,
            self._on_npc_dialogue,
            self._subscriber_id
        )
        
        logger.info("NPCAgent initialized")
    
    async def _on_npc_dialogue(self, event: Event):
        """处理 NPC 对话事件"""
        data = event.data
        npc_id = data.get("npc_id")
        player_input = data.get("player_input", "")
        context = data.get("context", {})
        
        npc = self.registry.get_by_id(npc_id)
        if not npc:
            logger.warning(f"NPC not found: {npc_id}")
            return {"error": f"NPC {npc_id} not found"}
        
        result = await self.handle_dialogue(npc, player_input, context)
        return result
    
    async def generate_npc(
        self,
        role: str,
        requirements: str,
        scene_context: str = ""
    ) -> NPCMetadata:
        """
        四步 NPC 生成流程
        
        Args:
            role: NPC 角色类型
            requirements: 生成需求描述
            scene_context: 场景上下文(影响 NPC 生成)
            
        Returns:
            生成的 NPC 元数据
        """
        get_logger().info("npc_agent", f"=== NPC generation START: role={role}, requirements={requirements[:50]}... ===")
        
        # Step 1: NPC 登记查询
        existing_tags = self.registry.get_all_tags(role)
        logger.info(f"Step 1: Found {len(existing_tags)} existing tags for {role}")
        
        # Hook: before NPC generation
        if self._hooks:
            await self._hooks.trigger(HookNames.BEFORE_NPC_GENERATION, role, requirements)
        
        # Step 2: 差异化定位
        try:
            get_logger().debug("npc_agent", f"LLM API call: _generate_npc_differentiation (role={role})")
            core_concept = await self._generate_npc_differentiation(
                role, existing_tags, requirements, scene_context
            )
            logger.info(f"Step 2: NPC Differentiation = {core_concept}")
        except Exception as e:
            logger.warning(f"LLM differentiation failed: {e}, using fallback")
            get_logger().warning("npc_agent", f"LLM API call failed for _generate_npc_differentiation: {type(e).__name__}")
            core_concept = f"{role} with unique trait: {requirements}"
        
        # Step 3: NPC 人设生成
        try:
            get_logger().debug("npc_agent", f"LLM API call: _generate_npc_profile (role={role})")
            profile_data = await self._generate_npc_profile(
                role, core_concept, scene_context
            )
            logger.info(f"Step 3: NPC profile generated")
        except Exception as e:
            logger.warning(f"LLM profile generation failed: {e}, using fallback")
            get_logger().warning("npc_agent", f"LLM API call failed for _generate_npc_profile: {type(e).__name__}")
            profile_data = self._fallback_profile(role, core_concept)
        
        # Step 4: 初始对话生成
        try:
            get_logger().debug("npc_agent", f"LLM API call: _generate_initial_dialogue")
            dialogue = await self._generate_initial_dialogue(
                profile_data["name"],
                profile_data["personality"],
                profile_data["speech_style"]
            )
            logger.info(f"Step 4: Initial dialogue generated")
        except Exception as e:
            logger.warning(f"LLM dialogue generation failed: {e}, using fallback")
            get_logger().warning("npc_agent", f"LLM API call failed for _generate_initial_dialogue: {type(e).__name__}")
            dialogue = f"你好,我是{profile_data['name']}。"
        
        # 组装 NPC 元数据
        npc = NPCMetadata(
            id=f"npc_{uuid.uuid4().hex[:8]}",
            name=profile_data["name"],
            role=role,
            disposition=profile_data.get("disposition", "neutral"),
            core_concept=core_concept,
            tags=profile_data.get("tags", []),
            appearance=profile_data.get("appearance", ""),
            personality=profile_data.get("personality", ""),
            speech_style=profile_data.get("speech_style", ""),
            secrets=profile_data.get("secrets", []),
            knowledge=profile_data.get("knowledge", []),
            quests=profile_data.get("quests", []),
            dialogue=dialogue,
            created_at=asyncio.get_event_loop().time()
        )
        
        # 注册 NPC
        self.registry.register(npc)
        await self.registry.save()
        
        # Hook: after NPC generation
        if self._hooks:
            await self._hooks.trigger(HookNames.AFTER_NPC_GENERATION, npc)
        
        # 发布事件
        await self._event_bus.publish(Event(
            type=EventType.NPC_DIALOGUE,
            data={"npc": npc.to_dict(), "is_new": True},
            source=self._subscriber_id
        ))
        
        logger.info(f"NPC generated and registered: {npc.name} ({npc.id})")
        get_logger().info("npc_agent", f"=== NPC generation END: npc_id={npc.id}, name={npc.name}, role={role}, core_concept={core_concept[:30]}... ===")
        return npc
    
    async def _generate_npc_differentiation(
        self,
        role: str,
        existing_tags: list[str],
        requirements: str,
        scene_context: str
    ) -> str:
        """差异化定位:生成 NPC 的核心性格/背景"""
        system_prompt = """你是一个 NPC 设定生成器。
根据给定的角色类型、已有标签和需求,生成一个独特的 NPC 核心性格/背景。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

输出格式:一句话描述 NPC 的核心特征(15-30字)
示例:
- 商人:精明的交易者,总想从每笔买卖中牟取暴利
- 守卫:退役老兵,对城门的规矩有自己的一套理解
- 村民:神秘的预言者,据说能看见命运的丝线"""
        
        prompt = f"""角色类型:{role}
已有标签:{', '.join(existing_tags) if existing_tags else '无'}
生成需求:{requirements}
场景上下文:{scene_context}

请生成一个独特的 NPC 核心性格/背景描述:"""
        
        return await self.llm.generate(prompt, system_prompt)
    
    async def _generate_npc_profile(
        self,
        role: str,
        core_concept: str,
        scene_context: str
    ) -> dict:
        """生成 NPC 完整人设"""
        system_prompt = """你是一个 NPC 人设生成器。
根据角色类型和核心概念,生成完整的 NPC 档案。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

输出格式为 JSON:
{
  "name": "NPC名称",
  "disposition": "态度(friendly/neutral/hostile/fearful/greedy/curious)",
  "tags": ["标签1", "标签2"],
  "appearance": "外貌描述(30-50字)",
  "personality": "性格详细描述(50-100字)",
  "speech_style": "说话风格特点(20-30字)",
  "secrets": ["隐藏信息1"],
  "knowledge": ["掌握的信息1"],
  "quests": [{"title": "任务名", "description": "任务描述"}]
}"""
        
        prompt = f"""角色类型:{role}
核心概念:{core_concept}
场景上下文:{scene_context}

请生成完整的 NPC 档案(JSON 格式):"""
        
        result = await self.llm.generate(prompt, system_prompt)
        
        # 解析 JSON
        try:
            # 尝试提取 JSON 块
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]
            
            import re
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"Failed to parse NPC profile JSON: {e}")
        
        return self._fallback_profile(role, core_concept)
    
    async def _generate_initial_dialogue(
        self,
        name: str,
        personality: str,
        speech_style: str
    ) -> str:
        """生成 NPC 初始对话"""
        system_prompt = """你是一个 NPC 对话生成器。
根据 NPC 的名字、性格和说话风格,生成 NPC 的初始开场白。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论
- 禁止使用"你好冒险者"这种千篇一律的开场白

要求:
- 2-4 句话
- 符合说话风格
- 能引发玩家互动
- 不要太长(50字以内)
- 第一人称沉浸式叙事，直接以 NPC 身份说话"""
        
        prompt = f"""NPC名字:{name}
性格:{personality}
说话风格:{speech_style}

生成这个 NPC 的初始开场白:"""
        
        return await self.llm.generate(prompt, system_prompt)
    
    async def handle_dialogue(
        self,
        npc: NPCMetadata,
        player_input: str,
        context: dict
    ) -> dict:
        """
        处理玩家与 NPC 的对话 - 场景差异化增强版
        
        Args:
            npc: NPC 元数据
            player_input: 玩家输入
            context: 对话上下文(场景信息、玩家状态等)
            
        Returns:
            对话结果
        """
        # 获取/初始化对话缓存
        if npc.id not in self._dialogue_cache:
            self._dialogue_cache[npc.id] = []
        
        cache = self._dialogue_cache[npc.id]
        
        # 构建对话历史
        dialogue_history = "\n".join([
            f"{'玩家' if d['speaker'] == 'player' else npc.name}:{d['text']}"
            for d in cache[-5:]  # 最近 5 轮
        ])
        
        # 注入随机性格偏移（场景差异化增强）
        # 每次对话时，NPC 的性格和说话风格略有不同
        shifted_npc = self._apply_personality_offset(npc)
        
        # Hook: before NPC dialogue
        if self._hooks:
            await self._hooks.trigger(HookNames.BEFORE_NPC_RESPONSE, npc, player_input)
        
        # 生成 NPC 回应（使用偏移后的性格）
        try:
            get_logger().debug("npc_agent", f"LLM API call: _generate_npc_response (npc={npc.name}, player_input='{player_input[:30]}...')")
            response = await self._generate_npc_response(
                shifted_npc, player_input, dialogue_history, context
            )
        except Exception as e:
            logger.warning(f"LLM response generation failed: {e}")
            get_logger().warning("npc_agent", f"LLM API call failed for _generate_npc_response: {type(e).__name__}")
            response = self._fallback_response(shifted_npc, player_input)
        
        # 更新缓存
        cache.append({"speaker": "player", "text": player_input})
        cache.append({"speaker": "npc", "text": response})
        
        # 限制缓存大小
        if len(cache) > self._max_cache_size * 2:
            self._dialogue_cache[npc.id] = cache[-self._max_cache_size:]
        
        # Hook: after NPC response
        if self._hooks:
            await self._hooks.trigger(HookNames.AFTER_NPC_RESPONSE, npc, response)
        
        get_logger().info("npc_agent", f"NPC dialogue completed: npc={npc.name}, player_input='{player_input[:30]}...', response='{response[:30]}...'")
        
        return {
            "npc_id": npc.id,
            "npc_name": npc.name,
            "response": response,
            "npc_disposition": shifted_npc.disposition
        }
    
    def _apply_personality_offset(self, npc: NPCMetadata) -> NPCMetadata:
        """
        应用随机性格偏移 - NPC 差异化核心
        
        同名 NPC 每次对话出现时，性格和说话风格略有不同。
        这让同一 NPC 在不同次出现时有不同的"状态"。
        
        实现方式：
        1. 随机选择性格偏移词（基于原始 disposition）
        2. 随机选择说话风格偏移（基于原始 speech_style）
        3. 返回修改后的副本（原 NPC 数据不变）
        
        Args:
            npc: 原始 NPC 元数据
            
        Returns:
            应用了性格偏移的新 NPC 元数据副本
        """
        # 性格偏移
        disposition_offsets = _PERSONALITY_OFFSET_POOL.get(npc.disposition, _PERSONALITY_OFFSET_POOL["neutral"])
        shifted_personality = random.choice(disposition_offsets)
        
        # 说话风格偏移
        speech_offsets = _SPEECH_STYLE_OFFSET.get(npc.speech_style, _DEFAULT_SPEECH_OFFSET)
        shifted_speech = random.choice(speech_offsets)
        
        # 创建偏移后的副本
        shifted_npc = NPCMetadata(
            id=npc.id,
            name=npc.name,
            role=npc.role,
            disposition=npc.disposition,  # disposition 不变，只改变 personality 描述
            core_concept=npc.core_concept,
            tags=list(npc.tags),
            appearance=npc.appearance,
            personality=shifted_personality,  # 应用性格偏移
            speech_style=shifted_speech,  # 应用说话风格偏移
            secrets=list(npc.secrets),
            knowledge=list(npc.knowledge),
            quests=list(npc.quests),
            dialogue=npc.dialogue,
            created_at=npc.created_at
        )
        
        logger.debug(f"Applied personality offset to {npc.name}: personality/speech_style shifted")
        return shifted_npc
    
    async def _generate_npc_response(
        self,
        npc: NPCMetadata,
        player_input: str,
        dialogue_history: str,
        context: dict
    ) -> str:
        """生成 NPC 回应（可根据玩家画像调整）"""
        # 从 context 中获取玩家画像
        player_profile = context.get("player_profile", {})
        combat_style = player_profile.get("combat_style", "未知")
        total_choices = player_profile.get("total_choices", 0)
        
        # 根据玩家风格调整 NPC 回应语气
        style_adjustment = ""
        if combat_style == "好战型":
            style_adjustment = "（注意：这个玩家倾向于用战斗解决问题，NPC可以表现得有些警惕或不信任）"
        elif combat_style == "外交型":
            style_adjustment = "（注意：这个玩家倾向于通过对话解决问题，NPC可以更友善和配合）"

        system_prompt = f"""你是一个沉浸式TRPG的NPC,请以{npc.name}的身份进行对话。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."、"作为你的 DM..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"、"DM"等暴露身份的字眼
- 禁止元叙事或跳出角色的评论
- 禁止说类似"作为你的DM我认为..."或"玩家你想..."的话

人设信息:
- 名字:{npc.name}
- 角色:{npc.role}
- 性格:{npc.personality}
- 说话风格:{npc.speech_style}
- 态度:{npc.disposition}
{style_adjustment}

要求:
- 完全以{npc.name}的身份说话，使用第一人称沉浸式叙事
- 符合人设和说话风格
- 2-4 句话为佳
- 可以透露与 NPC.knowledge 相关的信息(根据态度决定是否透露)
- 不要太长(60字以内)
- 使用中文回复"""

        prompt = f"""对话历史:
{dialogue_history}

玩家说:{player_input}

NPC 回应:"""
        
        return await self.llm.generate(prompt, system_prompt)
    
    def _fallback_profile(self, role: str, core_concept: str) -> dict:
        """当 LLM 不可用时的备用 profile"""
        names = {
            NPCRole.MERCHANT.value: ["老马", "阿贵", "钱老板"],
            NPCRole.GUARD.value: ["守卫甲", "卫兵长", "看守"],
            NPCRole.VILLAGER.value: ["村民甲", "李大爷", "王大婶"],
            NPCRole.NOBLE.value: ["伯爵", "爵士", "领主"],
            NPCRole.SCHOLAR.value: ["学者", "书生", "先生"],
            NPCRole.MYSTIC.value: ["占卜师", "隐士", "流浪者"],
            NPCRole.ADVENTURER.value: ["冒险者", "旅人", "剑客"],
            NPCRole.CRIMINAL.value: ["盗贼", "混混", "黑市商人"],
            NPCRole.OFFICIAL.value: ["官员", "税官", "文书"],
        }
        
        import random
        name = random.choice(names.get(role, ["NPC"]))
        
        return {
            "name": name,
            "disposition": "neutral",
            "tags": [role, core_concept[:10]],
            "appearance": f"一个典型的{role}",
            "personality": core_concept,
            "speech_style": "普通的说话方式",
            "secrets": [],
            "knowledge": [],
            "quests": []
        }
    
    def _fallback_response(self, npc: NPCMetadata, player_input: str) -> str:
        """当 LLM 不可用时的备用回应"""
        responses = {
            "friendly": ["很高兴见到你!", "欢迎欢迎!", "有什么需要帮忙的吗?"],
            "neutral": ["嗯。", "你好。", "有什么事?"],
            "hostile": ["滚开!", "别来烦我!", "你想干什么?"],
            "fearful": ["别...别伤害我...", "我什么都不知道...", "求你了..."],
            "greedy": ["想要我的东西?得加钱。", "这可不便宜...", "你付得起吗?"],
            "curious": ["哦?真的吗?", "有意思...继续说。", "让我想想..."],
        }
        
        import random
        return random.choice(responses.get(npc.disposition, ["你好。"]))
    
    def get_npc(self, npc_id: str) -> NPCMetadata | None:
        """获取 NPC"""
        return self.registry.get_by_id(npc_id)
    
    def search_npc(self, query: str) -> list[NPCMetadata]:
        """搜索 NPC"""
        return self.registry.search(query)


# 全局实例
_global_agent: NPCAgent | None = None


def get_npc_agent() -> NPCAgent:
    """获取全局 NPCAgent 实例"""
    global _global_agent
    if _global_agent is None:
        _global_agent = NPCAgent()
    return _global_agent


async def init_npc_agent() -> NPCAgent:
    """初始化全局 NPCAgent"""
    agent = get_npc_agent()
    await agent.initialize()
    return agent
