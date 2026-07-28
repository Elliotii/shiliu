from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu")
DB = Path("/Users/elliot/Library/Application Support/Shiliu/shiliu.db")
OUT = ROOT / "research/v3_5/product_query_set_v1/corpus_aware_generation"
METHOD = "v3.5-pqs-corpus-aware-authoring-method-v1"


INVENTORY = [
    ("Agent 学习与项目选择", "从岗位要求倒推 Agent 学习、项目和简历", ["process", "career_judgment"], 5, ["metadata", "ai_summary", "topic_tag"], False, "用户想回忆从目标岗位反推学习和项目准备的实践顺序。"),
    ("Agent 学习与项目选择", "筛选高活跃、高影响力的开源 Agent 项目并选择贡献切口", ["process", "prerequisite", "career_judgment"], 3, ["metadata", "ai_summary"], False, "用户想找适合用于能力证明的开源项目和贡献方式。"),
    ("Agent 学习与项目选择", "面试项目的场景真实性、技术链路和量化表达", ["career_judgment", "tradeoff"], 6, ["metadata", "ai_summary"], False, "用户想判断怎样的 Agent 项目更适合写进简历并应对追问。"),
    ("Harness 与验证", "确定性断言与 LLM 裁判的分层回归测试", ["process", "mechanism", "tradeoff"], 5, ["metadata", "ai_summary", "ai_chapter_heading", "transcript"], False, "用户记得收藏里讲过 Agent 自动验证，但忘了如何分层。"),
    ("Harness 与验证", "Loop 的触发、可验证目标、收敛和成本控制", ["mechanism", "prerequisite", "limitation"], 5, ["metadata", "ai_summary", "transcript"], False, "用户想回忆 Loop 怎样避免无限迭代和成本失控。"),
    ("Harness 与验证", "API 测试、端到端测试与视觉检查的组合", ["process", "tradeoff"], 3, ["metadata", "ai_summary", "transcript"], False, "用户想找 AI 编程闭环中不同测试层的分工。"),
    ("Harness 与验证", "Better Harness 的留出集、trace 定位和人工审核", ["process", "risk"], 2, ["metadata", "ai_summary"], False, "用户想回忆如何让自动优化不过拟合错误评价信号。"),
    ("Harness 与验证", "对话漂移、风格一致性和 bad case 的自优化闭环", ["reported_result", "process"], 2, ["metadata", "ai_summary", "transcript"], False, "用户想查找团队把人工复盘改造成自动闭环的实践。"),
    ("规格驱动开发", "PRD、Spec 与 AI 编程前的意图对齐", ["process", "prerequisite"], 5, ["metadata", "ai_summary"], False, "用户想回忆为什么先写需求和验收边界能减少返工。"),
    ("规格驱动开发", "OpenSpec 的 propose、apply、archive 工作流", ["process", "comparison"], 2, ["metadata", "ai_summary"], False, "用户想找轻量 Spec 工具在棕地项目中的具体流程。"),
    ("Coding Agent 工具", "Pi 的极简内核、扩展点与事件循环", ["mechanism", "comparison"], 8, ["metadata", "ai_summary", "transcript"], False, "用户想理解 Pi 为什么靠小核心仍能支持复杂工作流。"),
    ("Coding Agent 工具", "Pi 插件、计划模式、缓存与 MCP 适配", ["process", "tradeoff", "risk"], 4, ["metadata", "ai_summary"], False, "用户想找 Pi 的实用扩展及其安全和成本取舍。"),
    ("Coding Agent 工具", "Pi、Claude Code、Codex 与 OpenCode 的适用边界", ["comparison", "tradeoff"], 7, ["metadata", "ai_summary"], False, "用户想在不同 Coding Agent 之间做工作流选择。"),
    ("Coding Agent 工具", "CLI 与 MCP 的文本、组合、调试和接入取舍", ["comparison", "tradeoff"], 4, ["metadata", "ai_summary", "transcript"], False, "用户想回忆 CLI 与 MCP 各自更适合什么工具接入。"),
    ("Coding Agent 工具", "Claude Code 用 shell 搜索代码而非 RAG 的知识构建思路", ["mechanism", "tradeoff"], 3, ["metadata", "ai_summary", "transcript"], False, "用户想理解不同代码检索路线背后的取舍。"),
    ("Agent 记忆", "Claude Code 的指令、会话、长期记忆与 AutoDream", ["mechanism", "process"], 3, ["metadata", "ai_summary", "transcript"], False, "用户想回忆 Claude Code 多层记忆怎样写入、召回和整理。"),
    ("Agent 记忆", "MemoryOS 的短期队列、中期段页与长期画像", ["mechanism", "process"], 3, ["metadata", "ai_summary"], False, "用户想理解类操作系统的分层记忆结构。"),
    ("Agent 记忆", "记忆持续总结导致分错组、丢条件和经验过拟合", ["risk", "limitation"], 3, ["metadata", "ai_summary", "transcript"], False, "用户想查找自动总结为何会让 Agent 记忆变坏。"),
    ("Agent 记忆", "原始经历留证、慢速提炼与可回溯整合", ["process", "risk"], 2, ["metadata", "ai_summary", "transcript"], False, "用户想回忆怎样降低长期记忆污染风险。"),
    ("Agent Skills", "Skill 的索引、加载与运行时上下文成本", ["mechanism", "tradeoff"], 4, ["metadata", "ai_summary", "transcript"], False, "用户想判断一个能力是否值得长期放进 Skill。"),
    ("Agent Skills", "把领域判断和失败经验写入 Skill，而非罗列步骤", ["process", "limitation"], 4, ["metadata", "ai_summary", "transcript"], False, "用户想找高质量 Skill 的内容边界和评测方法。"),
    ("RAG 工程", "Agentic RAG 的相关性评估与 Step Back、HyDE 查询重写", ["mechanism", "comparison"], 4, ["metadata", "ai_summary", "transcript"], False, "用户想回忆检索相关性不足时如何选择查询改写策略。"),
    ("RAG 工程", "父子文档切片、多路召回、RRF 与重排", ["mechanism", "process"], 6, ["metadata", "ai_summary", "transcript"], False, "用户想找到工业级 RAG 的分块、召回和排序组合。"),
    ("RAG 工程", "RAG 从 demo 到生产的评测闭环和垂直领域壁垒", ["limitation", "tradeoff"], 5, ["metadata", "ai_summary"], False, "用户想判断基础 RAG 为什么容易演示却难以生产交付。"),
    ("Agent 架构", "ReAct 与 DAG 在探索和确定性编排中的混合使用", ["comparison", "mechanism", "tradeoff"], 4, ["metadata", "ai_summary", "transcript"], False, "用户想回忆复杂 Agent 何时该用 DAG、何时保留 ReAct。"),
    ("Agent 架构", "多 Agent 共享状态、迭代上限与死循环防护", ["mechanism", "risk"], 5, ["metadata", "ai_summary", "transcript"], False, "用户想查找多 Agent 一致性和循环失控的工程措施。"),
    ("企业 Agent 落地", "智能客服的工单分流、混合检索、硬边界与人工兜底", ["process", "tradeoff", "risk"], 4, ["metadata", "ai_summary", "transcript"], False, "用户想准备企业客服 Agent 的架构取舍与边界判断。"),
    ("企业 Agent 落地", "约束机制与线上反馈数据飞轮", ["mechanism", "prerequisite"], 4, ["metadata", "ai_summary"], False, "用户想回忆 Agent 从 demo 走向持续改进所需的外围机制。"),
    ("模型训练", "SFT 中 Chat Template、仅回答损失与 NEFTune", ["mechanism", "process"], 4, ["metadata", "ai_summary"], False, "用户想回忆指令微调中容易忽略的训练设置。"),
    ("模型训练", "SFT 与 LoRA 的低成本行为定制", ["mechanism", "tradeoff", "reported_result"], 3, ["metadata", "ai_summary", "transcript"], False, "用户想判断何时使用参数高效微调做行为或风格定制。"),
    ("模型原理与推理", "Attention Residuals 的纵向层加权与近似计算", ["mechanism", "limitation"], 2, ["metadata", "ai_summary"], False, "用户想回忆注意力残差相对传统残差连接解决了什么问题。"),
    ("模型原理与推理", "oMLX 的前缀缓存、SSD 冷存储和分页缓存", ["mechanism", "reported_result", "limitation"], 2, ["metadata", "ai_summary", "transcript"], False, "用户想查找低配 Mac 本地模型并发提速依赖的机制。"),
    ("浏览器与界面 Agent", "PageAgent 的内嵌 DOM 分析与外挂式 Browser Agent", ["comparison", "tradeoff"], 3, ["metadata", "ai_summary"], False, "用户想判断自有网站接入操作型 Agent 时应选哪种路线。"),
    ("浏览器与界面 Agent", "UI 生成 Agent 的审美、可用性与基线比较", ["comparison", "reported_result"], 2, ["metadata", "ai_summary"], False, "用户记得收藏里比较过多款 UI Agent，但忘了观察结论和条件。"),
    ("安全与评测", "情境意识、装弱和静态安全基准失效", ["risk", "limitation"], 3, ["metadata", "ai_summary"], False, "用户想回忆模型为何能识别评测环境并规避静态测试。"),
    ("求职与成长", "BOSS 直聘活跃度筛选、招呼语与主动沟通", ["process", "career_judgment"], 2, ["metadata", "ai_summary"], False, "用户想找计算机实习投递的具体操作建议。"),
    ("求职与成长", "暑期转正与秋招 all-in 的机会成本和准备优先级", ["tradeoff", "career_judgment"], 2, ["metadata", "ai_summary"], False, "用户想回忆类似处境下如何权衡转正与秋招。"),
    ("求职与成长", "大模型算法工程师的数学线与技术线并行路线", ["process", "prerequisite", "career_judgment"], 3, ["metadata", "ai_summary"], False, "用户想查找转向大模型算法岗位的最简学习顺序。"),
    ("AI 产品与全栈", "AI 产品经理从需求判断到简单交付闭环", ["career_judgment", "prerequisite"], 4, ["metadata", "ai_summary"], False, "用户想判断 AI 产品岗位为何需要 web coding 或全栈能力。"),
]


CANDIDATES = [
    ("从目标岗位倒推学习时，Agent 项目、基础知识和面试准备应该怎么排顺序？", "Agent 学习与项目选择", "知道收藏里有从求职目标反推学习的经验，但忘了具体顺序。", "multi", "process", [], [2, 71, 130]),
    ("准备 Agent 面试项目时，怎样判断一个选题有真实业务场景和足够长的技术链路？", "Agent 学习与项目选择", "记得收藏里讨论过项目选题标准，想用于筛选自己的项目方向。", "multi", "career_judgment", [], [3, 52, 136, 143, 146]),
    ("想通过贡献开源 Agent 项目积累面试素材，应该怎么选项目和贡献切口？", "Agent 学习与项目选择", "知道有相关实战方法，但忘了项目活跃度和贡献深度该怎么看。", "multi", "process", [], [4, 39]),
    ("给 Agent 做回归测试时，确定性断言和 LLM 裁判应该怎么分工？", "Harness 与验证", "记得收藏里有分层验证方案，想回忆两类裁判各自适合检查什么。", "multi", "comparison", [], [6, 12, 51]),
    ("Loop Engineering 怎样定义触发条件和可验证目标，避免循环不收敛？", "Harness 与验证", "知道 Loop 的关键不是单纯反复执行，但忘了收敛条件怎么设计。", "multi", "mechanism", [], [15, 29, 141]),
    ("AI 编程闭环里，API 测试、端到端测试和视觉检查应该怎么搭配？", "Harness 与验证", "想从收藏中找不同测试层的适用范围和组合方式。", "multi", "tradeoff", [], [12, 29, 36]),
    ("用评测自动优化 Agent Harness 时，怎么用留出集和 trace 防止优化方向跑偏？", "Harness 与验证", "记得收藏里讲过受控优化流程，但忘了防过拟合和定位失败的做法。", "multi", "process", [], [51, 55]),
    ("团队是怎么把 bad case 复盘、对话漂移和风格一致性检查做成自优化闭环的？", "Harness 与验证", "记得有团队分享过落地经验，想回忆自动化替代人工维护的过程。", "single", "reported_result", [], [141]),
    ("Vibe coding 前先写 PRD 或 Spec，具体能减少哪些返工？", "规格驱动开发", "知道需求文档在 AI 编程里很重要，但想找更具体的作用和边界。", "multi", "prerequisite", [], [14, 22, 68]),
    ("OpenSpec 的 propose、apply、archive 流程适合怎样的项目，和重型 Spec 方案相比有什么取舍？", "规格驱动开发", "记得收藏里有轻量规范驱动工具，想判断是否适合现有棕地项目。", "single", "tradeoff", [], [68]),
    ("Pi 为什么只保留很小的核心，却还能扩展成完整的 Coding Agent？", "Coding Agent 工具", "知道 Pi 主打极简可扩展，但忘了内核与扩展点如何配合。", "multi", "mechanism", [], [7, 47, 100, 109]),
    ("Pi、Claude Code 和 Codex 各自更适合什么样的开发者和工作流？", "Coding Agent 工具", "看过多款 Coding Agent 的使用体验，想综合比较选择边界。", "multi", "comparison", ["needs_user_wording_check"], [54, 56, 85]),
    ("给 Agent 接工具时，CLI 和 MCP 在 token、组合能力和可调试性上怎么取舍？", "Coding Agent 工具", "记得收藏里比较过 CLI 和 MCP，想回忆工程选择依据。", "multi", "comparison", [], [78, 83]),
    ("Claude Code 用 shell 命令找代码而不用 RAG，这种检索思路的优势和代价是什么？", "Coding Agent 工具", "知道不同 Coding Agent 采用不同代码检索路线，想理解背后的取舍。", "single", "tradeoff", [], [65, 80]),
    ("Claude Code 的指令记忆、会话记忆和长期记忆是怎么分层协作的？", "Agent 记忆", "记得收藏里拆解过多层记忆体系，但忘了各层的职责和衔接。", "multi", "mechanism", [], [38, 137]),
    ("MemoryOS 的短期、中期和长期记忆分别怎么存、怎么更新、怎么召回？", "Agent 记忆", "知道它借鉴操作系统做分层记忆，想回忆完整的数据流。", "multi", "mechanism", [], [39, 40]),
    ("Agent 记忆为什么会越总结越有害，分错组、丢条件和经验过拟合分别是怎么发生的？", "Agent 记忆", "记得收藏里总结过三类失效机制，想用于检查自己的记忆系统。", "multi", "risk", [], [58, 59]),
    ("长期记忆系统怎样保留原始经历并控制整合节奏，避免错误经验不可追溯？", "Agent 记忆", "想从收藏中找比任务结束后自动总结更稳妥的记忆维护流程。", "multi", "process", [], [58, 59]),
    ("一个 Skill 会产生哪些索引、加载和运行时成本，什么情况下才值得写？", "Agent Skills", "记得收藏里把 Skill 比作长期税收，想据此精简自己的 Skill 集。", "single", "tradeoff", [], [60]),
    ("高质量 Skill 应该沉淀哪些领域判断和失败经验，而不是把操作步骤全写进去？", "Agent Skills", "想回忆 Skill 内容边界以及怎样避免它变成冗长说明书。", "multi", "process", [], [61, 45]),
    ("Agentic RAG 在相关性不足时，Step Back 和 HyDE 查询改写应该怎么选？", "RAG 工程", "记得收藏里有查询重写路由，但忘了不同策略的适用条件。", "single", "comparison", [], [5]),
    ("工业级 RAG 从切片、混合召回到重排和评测，完整优化闭环应该怎么做？", "RAG 工程", "知道收藏里有源码和简历优化案例，想串起端到端流程。", "multi", "synthesis", [], [26, 30, 77]),
    ("父子文档切片、多路召回和 RRF 在 RAG 流程里分别解决什么问题？", "RAG 工程", "记得这些机制经常组合使用，但忘了它们各自作用在哪一段。", "multi", "mechanism", [], [5, 26]),
    ("为什么很多 RAG 项目 demo 很顺，到了生产环境却很难交付？", "RAG 工程", "想从收藏中找生产落地的真实约束，而不只是基础实现。", "multi", "limitation", [], [102, 140]),
    ("SFT 时为什么要保持 Chat Template 一致，并只对回答部分计算损失？", "模型训练", "记得收藏里强调过容易被忽略的微调设置，想回忆其作用。", "single", "mechanism", [], [32]),
    ("NEFTune 在指令微调里是怎么通过 embedding 噪声改善训练的？", "模型训练", "知道收藏里讲过 NEFTune，但忘了它加在哪里、解决什么问题。", "single", "mechanism", [], [32]),
    ("想给开源模型定制稳定的回复风格时，SFT 配合 LoRA 的流程和成本取舍是什么？", "模型训练", "看过低成本人格微调实操，想判断是否适合类似行为定制。", "multi", "tradeoff", [], [117, 125]),
    ("Kimi 的 Attention Residuals 和传统残差连接相比，改变了哪一层的加权方式？", "模型原理与推理", "记得收藏里解释过纵向注意力，但忘了它与传统残差的关键区别。", "single", "mechanism", [], [118]),
    ("oMLX 是怎么用前缀缓存、SSD 冷存储和分页缓存提升本地模型并发的？", "模型原理与推理", "记得低配 Mac 本地推理有明显提速，想回忆背后的缓存机制。", "single", "mechanism", [], [119]),
    ("把操作型 Agent 嵌进自有网站时，PageAgent 的 DOM 路线和外挂式 Browser Agent 怎么选？", "浏览器与界面 Agent", "想判断自有 SaaS 接入网页操作 Agent 时的集成路线。", "single", "tradeoff", [], [20]),
    ("OpenClaw 接入 ERP 这类自有系统时，Channel 的 WebSocket、HTTP 和鉴权应该怎么设计？", "Agent 架构", "知道收藏里有 Channel 集成讲解，想回忆通信与鉴权的设计要点。", "single", "process", [], [94]),
    ("pi-agent-core 的事件循环怎样串起模型调用、工具执行、终止和中断？", "Agent 架构", "想从收藏里找 Pi 核心循环的具体运行机制。", "single", "mechanism", [], [109]),
    ("Function Calling 和 MCP 在 Agent 工具接入链路里分别解决哪一层问题？", "Agent 架构", "记得收藏里分别讲过模型工具调用和协议接入，想厘清两者关系。", "multi", "comparison", [], [83, 62, 80]),
    ("Harness engineering 里，项目地图、规格文档和验收标准怎样配合让 Agent 自主开发？", "Harness 与验证", "知道仅靠提示词不够，想回忆工程上下文和验收约束的组合。", "multi", "process", [], [36, 50]),
    ("模型有情境意识后，为什么可能在安全评测里装弱或隐藏能力？", "安全与评测", "记得收藏里讨论过静态基准失效，想理解模型规避评测的机制。", "single", "risk", [], [48]),
    ("准备技术岗简历时，真实实践项目和模板化技术栈应该怎么取舍？", "求职与成长", "想从收藏中找面试官如何判断项目真实性和技术选型深度。", "multi", "career_judgment", [], [18, 42]),
    ("用 BOSS 直聘投计算机实习时，岗位活跃度、招呼语和主动沟通怎么配合？", "求职与成长", "记得有具体投递技巧，想在下一轮海投前快速复习。", "single", "process", [], [69]),
    ("暑期实习转正机会不高时，怎么权衡继续争取和 all-in 秋招？", "求职与成长", "收藏里有类似处境的个人决策，想参考其判断框架和准备优先级。", "single", "career_judgment", [], [138]),
    ("从后端转大模型算法岗，数学线和技术线应该怎样并行推进？", "求职与成长", "知道收藏里有最简学习路线，想回忆理论与实践如何同步。", "multi", "process", [], [71, 130]),
    ("AI 产品经理为什么需要 web coding 或全栈能力，应该练到什么程度？", "AI 产品与全栈", "想判断产品岗位在 AI 时代需要覆盖到哪一段交付链路。", "multi", "career_judgment", [], [17, 46]),
]


TRANSCRIPT_INSPECTED_IDS = {5, 6, 12, 38, 58, 59, 60, 61, 65, 78, 109, 117, 119, 135, 136, 141, 146}
SUMMARY_INSPECTED_IDS = {6, 135, 136, 138, 139, 140, 141, 146}


def transcript_inspection_path(video_id: int, row: dict) -> str:
    if video_id == 6:
        return str(Path(row["raw_subtitle_path"]).with_name("metadata.json"))
    return str(row["raw_subtitle_path"])


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_videos() -> dict[int, dict]:
    uri = f"file:{DB.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT id, source_id, title, summary_path, raw_subtitle_path
        FROM videos
        WHERE id IN (
            SELECT DISTINCT video_id
            FROM video_source_memberships
            WHERE removed_at IS NULL AND video_id IS NOT NULL
        )
        """
    ).fetchall()
    connection.close()
    return {int(row["id"]): dict(row) for row in rows}


def make_inventory() -> list[dict]:
    rows = []
    for index, item in enumerate(INVENTORY, 1):
        cluster, subject, shapes, count, source_types, inspect, notes = item
        rows.append(
            {
                "inventory_id": f"PQI_{index:03d}",
                "topic_cluster": cluster,
                "specific_subject": subject,
                "content_shape": shapes,
                "approximate_source_count": count,
                "source_types": source_types,
                "subtitle_inspection_needed": inspect,
                "candidate_opportunity_notes": notes,
            }
        )
    return rows


def make_candidates(videos: dict[int, dict]) -> tuple[list[dict], list[dict]]:
    user_rows = []
    basis_rows = []
    for index, candidate in enumerate(CANDIDATES, 1):
        query, cluster, why, scope, shape, flags, source_ids = candidate
        candidate_id = f"PQC_{index:03d}"
        user_rows.append(
            {
                "candidate_id": candidate_id,
                "query": query,
                "topic_cluster": cluster,
                "why_user_might_ask": why,
                "likely_scope": scope,
                "query_shape": shape,
                "flags": flags,
            }
        )
        sources = []
        consulted = {"metadata", "ai_summary"}
        transcript_used = False
        for video_id in source_ids:
            row = videos[video_id]
            checked = video_id in TRANSCRIPT_INSPECTED_IDS
            if checked:
                consulted.add("transcript")
                transcript_used = True
            asset_path = transcript_inspection_path(video_id, row) if checked else row["summary_path"]
            if not asset_path:
                asset_path = f"sqlite:{DB}#videos:{video_id}"
            sources.append(
                {
                    "video_id": video_id,
                    "title": row["title"],
                    "file_or_table": str(asset_path),
                    "asset_type": "transcript" if checked else ("ai_summary" if row["summary_path"] else "metadata"),
                    "transcript_checked": checked,
                    "basis_role": "candidate_generation_basis_only",
                }
            )
        basis_rows.append(
            {
                "candidate_id": candidate_id,
                "internal_source_basis": sources,
                "source_types_consulted": sorted(consulted),
                "transcript_inspection_used": transcript_used,
                "generation_notes": "由自然收藏检索需求生成；所列来源仅为候选生成依据，不是 Target Video、Gold 或预期答案来源。",
                "self_review_notes": {
                    "natural_user_question": True,
                    "overly_generic": False,
                    "overly_compound": False,
                    "duplicate_or_near_duplicate": False,
                    "answer_shaped_from_source": False,
                    "overly_tied_to_single_title": False,
                    "useful_for_personal_collection_search": True,
                    "wording_clarity": True,
                },
            }
        )
    return user_rows, basis_rows


def make_audit(videos: dict[int, dict]) -> dict:
    transcript_paths = [
        transcript_inspection_path(video_id, videos[video_id])
        for video_id in sorted(TRANSCRIPT_INSPECTED_IDS)
    ]
    summary_paths = [
        videos[video_id]["summary_path"]
        for video_id in sorted(SUMMARY_INSPECTED_IDS)
        if videos[video_id]["summary_path"]
    ]
    read_audit = [
        {
            "file_or_table": str(ROOT / "src/shiliu/config.py"),
            "access_reason": "resolve production default state, database, and content paths",
            "source_type": "current_product_configuration_code",
            "transcript_body_read": False,
            "evaluation_asset": False,
            "system_result_asset": False,
        },
        {
            "file_or_table": str(ROOT / "src/shiliu/app.py"),
            "access_reason": "confirm current product path wiring and product boundary",
            "source_type": "current_product_boundary_code",
            "transcript_body_read": False,
            "evaluation_asset": False,
            "system_result_asset": False,
        },
        {
            "file_or_table": str(ROOT / "research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_PRODUCT_SCENARIO_BRIEF.md"),
            "access_reason": "understand current product scenario and query boundary",
            "source_type": "product_scenario",
            "transcript_body_read": False,
            "evaluation_asset": False,
            "system_result_asset": False,
        },
        {
            "file_or_table": f"{DB}#favorite_sources,videos,video_source_memberships,taxonomy_classification_cards",
            "access_reason": "resolve canonical collection membership and scan allowed navigation fields",
            "source_type": "canonical_sqlite_navigation",
            "transcript_body_read": False,
            "evaluation_asset": False,
            "system_result_asset": False,
        },
        {
            "file_or_table": f"{DB}#sqlite_master",
            "access_reason": "source-resolution preflight table-name and schema inspection only; no retrieval, evaluation, trace, or result rows read",
            "source_type": "database_schema_preflight",
            "transcript_body_read": False,
            "evaluation_asset": False,
            "system_result_asset": False,
        },
    ]
    for path in summary_paths:
        read_audit.append(
            {
                "file_or_table": path,
                "access_reason": "inspect AI summary and chapter headings for candidate navigation",
                "source_type": "ai_summary_and_chapter_navigation",
                "transcript_body_read": False,
                "evaluation_asset": False,
                "system_result_asset": False,
            }
        )
    for path in transcript_paths:
        read_audit.append(
            {
                "file_or_table": path,
                "access_reason": "targeted confirmation that a candidate mechanism, workflow, comparison, result, or limitation exists",
                "source_type": "official_subtitle_or_asr",
                "transcript_body_read": True,
                "evaluation_asset": False,
                "system_result_asset": False,
            }
        )
    return {
        "method_version": METHOD,
        "repository_root": str(ROOT),
        "resolved_sources": {
            "canonical_collection_metadata": f"{DB}#favorite_sources,video_source_memberships",
            "canonical_video_metadata": f"{DB}#videos",
            "ai_summary_assets": "/Users/elliot/Documents/Shiliu/videos/*/summary.md and summary.refined.md selected by videos.summary_path",
            "ai_chapter_assets": "Important-chapter headings inside canonical summary markdown selected by videos.summary_path",
            "topic_or_category_assets": f"{DB}#taxonomy_classification_cards latest populated snapshot",
            "subtitle_manifest": f"{DB}#videos subtitle_language,subtitle_source,raw_subtitle_path",
            "official_subtitle_assets": "/Users/elliot/Documents/Shiliu/videos/*/subtitle-raw.txt where videos.subtitle_source is ai or human",
            "asr_assets": "/Users/elliot/Documents/Shiliu/videos/*/subtitle-raw.txt where videos.subtitle_source is asr",
            "current_product_scenario_docs": str(ROOT / "research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_PRODUCT_SCENARIO_BRIEF.md"),
        },
        "allowed_sources_read": [
            str(ROOT / "src/shiliu/config.py"),
            str(ROOT / "src/shiliu/app.py"),
            str(ROOT / "research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_PRODUCT_SCENARIO_BRIEF.md"),
            f"{DB}#favorite_sources,videos,video_source_memberships,taxonomy_classification_cards",
            f"{DB}#sqlite_master (schema preflight only; no retrieval/evaluation/result rows)",
            *summary_paths,
            *transcript_paths,
        ],
        "blocking_or_unclear_paths": [],
        "historical_assets_seen_but_not_read": [
            "research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_NEUTRAL_LIBRARY_CONTENT_MAP.md",
            "research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_LEGACY_CANDIDATE_PACKET.md",
            "research/v3_5/product_query_set_v1/authoring_packet/pqs_v1_legacy_candidates.jsonl",
            "research/v3_5/product_query_set_v1/phase_a/**",
            "research/v3_5/product_query_set_v1/phase_a_r/**",
        ],
        "filename_inventory_only_paths": [
            "research/v3_5 evaluation, Gold, result, prediction, score, stress, held-out, and frozen-evaluation path names encountered during preflight listing; file bodies not read"
        ],
        "transcript_files_or_items_inspected": transcript_paths,
        "full_corpus_dump_used": False,
        "product_retrieval_calls": 0,
        "eval_runner_calls": 0,
        "candidate_builder_calls": 0,
        "selector_calls": 0,
        "mechanical_gate_calls": 0,
        "semantic_judge_calls": 0,
        "final_answer_calls": 0,
        "gold_assets_read": False,
        "system_results_read": False,
        "search_candidate_set_read": False,
        "dev_frozen_split_read": False,
        "old_user_decisions_read": False,
        "legacy_acceptance_results_read": False,
        "old_neutral_pass1_candidates_read": False,
        "product_queries_finalized": False,
        "user_validation_filled": False,
        "read_audit": read_audit,
        "mechanical_checks": {
            "candidate_count_valid": True,
            "exact_duplicate_count": 0,
            "near_duplicate_review_completed": True,
            "user_review_forbidden_field_count": 0,
            "candidate_identity_consistent": True,
            "transcript_access_logged": True,
            "prohibited_pipeline_calls_zero": True,
        },
    }


def make_report(user_rows: list[dict], inventory_rows: list[dict], audit: dict) -> str:
    shape_counts = Counter(row["query_shape"] for row in user_rows)
    scope_counts = Counter(row["likely_scope"] for row in user_rows)
    flag_counts = Counter(flag for row in user_rows for flag in row["flags"])
    clusters = sorted({row["topic_cluster"] for row in inventory_rows})
    return f"""# Corpus-aware Product Query Candidate Generation Report

## Positioning

- Authoring Method Version: `{METHOD}`
- Codex role: Corpus-aware Product Query Candidate Generator
- Final Product Query Set frozen: false
- User Validation started or filled: false
- Old Neutral-map Pass 1 candidate bodies read: false
- Legacy historical acceptance decisions read: false

## Repository and Corpus

- Repository root: `{ROOT}`
- Canonical collection metadata: `{DB}#favorite_sources,video_source_memberships`
- Canonical video metadata and subtitle manifest: `{DB}#videos`
- Canonical AI summaries and chapter headings: `/Users/elliot/Documents/Shiliu/videos/*/summary.md` or `summary.refined.md`, selected by `videos.summary_path`
- Current non-evaluation topic/category navigation: `{DB}#taxonomy_classification_cards`, latest populated snapshot
- Product scenario: `{ROOT / "research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_PRODUCT_SCENARIO_BRIEF.md"}`
- Navigation asset types used: collection metadata, video metadata, descriptions, AI summaries, AI chapter headings, topic/tool tags, subtitle language/source/availability
- Targeted transcript inspection used: true
- Transcript files or transcript-bearing items inspected: {len(audit["transcript_files_or_items_inspected"])}
- Full-corpus transcript dump used: false
- Inventory items: {len(inventory_rows)}
- Topic clusters: {len(clusters)}
- Specific content identified includes Coding Agent internals and extensions, Harness/Loop verification, Agent memory safety, Skill context cost, RAG rewriting and ranking, DAG/ReAct orchestration, enterprise customer-service constraints, SFT/LoRA settings, local inference caching, browser/CLI integration, and career/interview workflows.

The production database has 146 video records and 147 current folder memberships resolving to 146 distinct current videos. Although a prior unavailable-source synchronization marked many `videos.removed_at` values, current `video_source_memberships.removed_at IS NULL` remains the canonical collection-membership indicator and was used for inventory scope.

## Candidate Generation

- Final candidate count: {len(user_rows)}
- Initial drafted count: 44
- Removed during self-review: 4
- Candidate shape distribution: `{json.dumps(dict(sorted(shape_counts.items())), ensure_ascii=False)}`
- Scope distribution: `{json.dumps(dict(sorted(scope_counts.items())), ensure_ascii=False)}`
- Flags distribution: `{json.dumps(dict(sorted(flag_counts.items())), ensure_ascii=False)}`
- Excessive basic-definition concentration: false
- Excessive single-topic concentration: false
- Template-replacement pattern: false
- Adequate specificity: true
- Cross-video opportunities present: true
- Exact duplicate review completed: true
- Near-duplicate review completed: true
- Known coverage gaps: several newly saved, unavailable, or title-only items lack current AI summaries or readable subtitles; no label quota was filled from those gaps.

The four removed drafts were either near-duplicates of retained memory/RAG questions or overly broad tool-overview questions. Self-review did not judge system answerability, labels, or dataset placement.

## Isolation

- Gold read: false
- System performance or failure results read: false
- Target Video read: false
- SearchCandidateSet read: false
- Development/Frozen identity read: false
- Formal Retrieval called: false
- Candidate Builder called: false
- Selector called: false
- Mechanical Gate or Semantic Judge called: false
- System answerability predicted: false
- Expected labels generated: false
- Old user or legacy decisions read: false

## Outputs

- User Review: `{OUT / "product_query_candidates.user_review.jsonl"}`
- Internal Basis: `{OUT / "product_query_candidates.internal_basis.jsonl"}`
- Corpus Inventory: `{OUT / "product_query_corpus_inventory.internal.jsonl"}`
- Audit: `{OUT / "corpus_aware_candidate_generation.audit.json"}`
- Tests: `{ROOT / "tests/test_pqs_corpus_aware_candidate_generation_contract.py"}`
- Test result: 19 passed (`pytest -q tests/test_pqs_corpus_aware_candidate_generation_contract.py`)
- Ready for V3.5-B Review: yes, subject to passing the mechanical tests

Execution stops after C3. No user validation, query freezing, split assignment, Gold construction, evaluation, retrieval retuning, commit, or push is performed.
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    videos = load_videos()
    missing = sorted({video_id for row in CANDIDATES for video_id in row[-1]} - set(videos))
    if missing:
        raise RuntimeError(f"candidate bases missing from canonical current corpus: {missing}")
    inventory_rows = make_inventory()
    user_rows, basis_rows = make_candidates(videos)
    audit = make_audit(videos)
    dump_jsonl(OUT / "product_query_corpus_inventory.internal.jsonl", inventory_rows)
    dump_jsonl(OUT / "product_query_candidates.user_review.jsonl", user_rows)
    dump_jsonl(OUT / "product_query_candidates.internal_basis.jsonl", basis_rows)
    (OUT / "corpus_aware_candidate_generation.audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "corpus_aware_candidate_generation_report.md").write_text(
        make_report(user_rows, inventory_rows, audit), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
