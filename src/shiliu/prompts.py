from __future__ import annotations

import json

from shiliu.domain import SubtitleLanguage, SubtitleSegment, SummaryResult, TranscriptResult


TRANSCRIPT_PROMPT_VERSION = "transcript-v1"
SUMMARY_PROMPT_VERSION = "summary-v1"
REFINEMENT_REVIEW_PROMPT_VERSION = "summary-refinement-v1"


def build_transcript_prompt(
    *, title: str, language: SubtitleLanguage, segments: list[SubtitleSegment]
) -> str:
    language_rule = (
        "输入是中文字幕，整理结果使用中文。"
        if language == SubtitleLanguage.ZH
        else "输入是英文字幕；原始字幕文件继续保留英文，但本阶段整理结果必须输出中文，英文技术专有名词保留英文。"
    )
    payload = [
        {"start": item.start, "end": item.end, "content": item.content}
        for item in segments
    ]
    return f"""你是视频字幕的保真编辑，不是摘要器。

视频标题：{title}
{language_rule}

必须遵守：
1. 严格保持原始时间顺序，不重排内容。
2. 只把被字幕系统拆散的连续句子合并为自然段，补充标点。
3. 仅轻度移除无意义语气词和明显机械重复；保留有意义的自我修正。
4. 只修正上下文明确的错别字或 ASR 错误；不确定时保留，影响理解的重要位置可标记 [疑似识别错误]。
5. 不概括、不删减主要内容、不扩写，不改变观点。
6. 根据内容生成分类标题，但不得为了分类改变顺序；同一主题之后再次出现可再次使用相同标题。
7. 只有重要主题开头才填写 start_seconds，其他填 null。不要给每段加时间戳。
8. 只输出一个 JSON 对象，不要 Markdown 代码围栏，不要额外解释。

JSON 结构：
{{"sections":[{{"title":"分类标题","start_seconds":138或null,"paragraphs":["自然段"]}}]}}

原始字幕 JSON：
{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}
"""


def build_summary_prompt(
    *, title: str, description: str, links: list[str], transcript: TranscriptResult
) -> str:
    transcript_payload = transcript.model_dump(mode="json")
    return f"""你是 AI 技术视频的结构化笔记编辑。摘要主体使用中文，模型、工具、框架、论文、GitHub 项目等专有名词尽量保留英文。

视频标题：{title}
视频简介：
{description or '(空)'}

从简介中机械提取的 URL（不得访问这些链接，也不得声称读过链接内容）：
{json.dumps(links, ensure_ascii=False)}

必须遵守：
1. 固定输出一句话结论、3～7 个核心观点、详细笔记。
2. 只有内容确实存在时才输出重要章节、entities、可执行事项、局限/争议/时效性；没有内容就使用空数组。
3. 时间戳只用于真正重要的章节，不用于每条观点。
4. 可执行事项必须来自视频明确建议或能从内容直接推导的行动，不得杜撰。
5. related_links 必须逐项包含上面列出的全部 URL，顺序保持一致；不要添加并非简介中的链接。
6. 不生成可信度分数，不做外部事实核查，不把推测写成视频原意。
7. 只输出一个 JSON 对象，不要 Markdown 代码围栏，不要额外解释。

JSON 结构：
{{
  "conclusion":"一句话结论",
  "key_points":["观点1","观点2","观点3"],
  "detailed_notes":["完整的详细笔记段落"],
  "important_chapters":[{{"title":"章节","start_seconds":138,"summary":"说明"}}],
  "entities":[{{"name":"Claude Code","kind":"工具","note":"视频中的作用"}}],
  "action_items":[{{"action":"行动","rationale":"来自视频的依据"}}],
  "limitations":["局限或时效提醒"],
  "related_links":{json.dumps(links, ensure_ascii=False)}
}}

整理原文 JSON：
    {json.dumps(transcript_payload, ensure_ascii=False, separators=(',', ':'))}
    """


def build_refinement_review_prompt(
    *,
    title: str,
    description: str,
    links: list[str],
    refined_transcript: TranscriptResult,
    fast_summary: SummaryResult,
) -> str:
    return f"""你是 AI 技术视频笔记的精修审稿人。

视频标题：{title}
视频简介：
{description or '(空)'}

简介链接（不得访问）：
{json.dumps(links, ensure_ascii=False)}

请对照精修后的完整原文，判断现有快速摘要是否需要修改。

规则：
1. 如果快速摘要已经忠实、完整且结构合格，decision=keep，revised_summary=null。
2. 如果存在遗漏、误解或需要随精修原文调整，decision=revise，并输出完整 revised_summary；不能只输出补丁。
3. change_reasons 用中文简要说明保留或修改依据。
4. revised_summary 仍须包含一句话结论、3～7 个核心观点、详细笔记；可选模块无内容时为空数组。
5. related_links 必须严格等于简介链接，不访问链接内容。
6. 只输出 JSON，不要 Markdown 围栏或额外说明。

JSON 结构：
{{
  "decision":"keep或revise",
  "change_reasons":["原因"],
  "revised_summary":null或完整摘要对象
}}

精修原文：
{json.dumps(refined_transcript.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':'))}

现有快速摘要：
{json.dumps(fast_summary.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':'))}
"""
