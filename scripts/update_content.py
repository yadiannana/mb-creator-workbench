#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每天自动更新“宝妈创作工作台”内容数据源。

功能：
1. 抓取抖音 / 全网热点（uapis.cn 免费热榜 API）。
2. 尝试抓取指定微信专辑文章（作为辅助素材）。
3. 调用 AI 改写成贴合“宝妈勇闯自媒体”赛道的内容。
4. 输出 JSON 到公开 GitHub Gist。

环境变量（在 GitHub Actions Secrets 中设置）：
  GIST_ID          要更新的 Gist ID
  GIST_TOKEN       有 gist 权限的 GitHub Personal Access Token
  OPENAI_API_KEY   AI 服务商 API Key
  OPENAI_BASE_URL  可选，OpenAI 兼容地址（默认 https://api.openai.com/v1）
  OPENAI_MODEL     可选，默认 gpt-4o-mini
  WECHAT_ALBUM_URL 可选，微信专辑/文章地址，用于给 AI 提供素材

输出文件：content.json（放到 Gist 中），App 会通过“设置”读取该地址。
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

import requests

GIST_ID = os.environ.get("GIST_ID", "").strip()
GIST_TOKEN = os.environ.get("GIST_TOKEN", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
WECHAT_ALBUM_URL = os.environ.get("WECHAT_ALBUM_URL", "").strip()
STYLE_SAMPLES = os.environ.get("STYLE_SAMPLES", "").strip()

# 默认语感样例（从参考博主截图里提炼的爆款结构；可在 Secrets 里用 STYLE_SAMPLES 覆盖）
DEFAULT_STYLE = """例1（周星驰/电影热点）:
封面：读懂星爷的通透：接纳普通，是成年人最高级的清醒
文案：星爷一席话又说到我心坎上了。接纳普通，不是躺平，是清楚自己是谁之后还敢继续往前走。咱们宝妈做自媒体更是如此，不必跟谁比，也不必怕被熟人看见，先把今天的视频发了再说。
话题：#宝妈情感 #女性成长 #宝妈自媒体

例2（杨紫/歌曲热点）:
封面：杨紫这首歌，送给每一个还在坚持的宝妈
文案："请把我的歌，带回你的家，请把你的微笑留下。"杨紫一开口，我就知道这是给普通人的温柔。我们做自媒体，不也是为了把日子过出笑容吗？坚持播，微笑总会被看见。
话题：#杨紫 #宝妈情感 #普通人做自媒体

例3（行动派/人民日报式）:
封面：真正厉害的人，都是跳过情绪直接行动
文案：担心做不好就担心的干，会紧张就紧张的干，没动力就没动力的干，一边焦虑一边干。宝妈做自媒体哪有准备好的那一天？开干吧各位！
话题：#女性成长 #宝妈成长 #励志语录

例4（收益晒单）:
封面：加入伙伴计划第二天，有收益啦！
文案：金额不大，却是努力最好的见证。我们普通人做自媒体，就是要勤快、心中有热爱、脚下有行动。努力终会开花结果。
话题：#宝妈自媒体 #收益 #坚持

例5（热点歌曲）:
封面：听新歌《吹吹山顶的风》，过肆意人生
文案：无法掌控的事情太多，自媒体也是如此。把心放宽一点，把事看淡一点，大步奔赴前路，自有清风相伴。
话题：#女性成长 #宝妈成长 #真实生活分享计划

例6（体育明星/孙颖莎）:
封面：恭喜孙颖莎夺冠！被她这段话狠狠鼓舞了
文案：孙颖莎说，没有白走的路。你看她站上领奖台的背后，是无数个无人问津的练习日。宝妈做自媒体也一样，你现在发的每一条视频，都是在为未来的某一天铺路。
话题：#宝妈成长 #励志 #坚持

金句参考（可当封面的短句要像这样）:
- "世上只有妈妈好，但妈妈也只有她自己最好。"
- "我们当妈的，先弄丢了自己，才学会找回自己。"
- "真正厉害的人，都是跳过情绪直接行动。"
- "允许自己慢慢来，是成年人最高级的清醒。"

================ 标准「图文文案」结构示范（必须照此格式写）================
一篇完整文案 = 图片上的文字 + 图片下方延续性正文。请严格按下面 5 段生成：

① 钩子句（第一句，12-15 字，必须有钩子）：
   痛点 / 反差 / 悬念 / 数字，让人刷到就想点开。例："当妈后我才懂，杨紫这话多通透"（14字）

② 金句（正文，原文原话，注明出处）：
   用明星发言 / 热点歌曲歌词 / 人民日报式人生感悟的原句。例：杨紫在采访里说："把生活过成自己喜欢的样子，本身就是一种成功。"

③ 感悟（图片上的几句话，2-4 句，每句一行，闺蜜语气，戳中宝妈情绪，能截图转发）：
   原来我们拼命追赶别人的时候，最该哄的是自己。
   做自媒体也是，先把日子过顺了，镜头里的松弛感才骗不了人。

④ 延续性标题（图片下方，承上启下）：
   宝妈做自媒体，别急着证明给谁看

⑤ 延续性正文（图片下方，2-4 句，落到宝妈做自媒体的共鸣/成长/变现）：
   你发的每一条，都是在替千万个普通妈妈说话。先完成再完美，今天这条发出去，就比昨天离变现近一步。

话题：#宝妈情感 #女性成长 #宝妈自媒体"""

# 北京时间 = UTC+8
BJ = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_hot(platform: str, limit: int = 20) -> List[Dict[str, str]]:
    """从 uapis.cn 抓取指定平台热榜。"""
    try:
        url = f"https://uapis.cn/api/v1/misc/hotboard?type={platform}&limit={limit}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("list", []) or []
        return [
            {"title": str(it.get("title", "")), "url": str(it.get("url", "")), "hot_value": str(it.get("hot_value", ""))}
            for it in items[:limit]
            if it.get("title")
        ]
    except Exception as e:
        log(f"[热榜] {platform} 抓取失败: {e}")
        return []


def fetch_hot_summary() -> List[Dict[str, str]]:
    """组合抖音 + 微博 + B站 + 头条 + 快手热点，取最多 30 条。"""
    platforms = [
        ("douyin", 8),
        ("weibo", 6),
        ("bilibili", 5),
        ("toutiao", 5),
        ("kuaishou", 5),
    ]
    combined = []
    for p, n in platforms:
        items = fetch_hot(p, n)
        for it in items:
            it["platform"] = p
        combined.extend(items)
    return combined


def fetch_wechat_album(url: str) -> str:
    """尝试抓取微信专辑/文章内容。微信风控较严，失败返回空字符串。"""
    if not url:
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G9980) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 NetType/WIFI MicroMessenger/8.0.49(0x18003131)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        text = resp.text
        # 简单提取正文：找文章主体文字段落
        # 1. 去除 script/style
        text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 8]
        # 取前 2500 字作为素材
        return "\n".join(lines)[:2500]
    except Exception as e:
        log(f"[微信] 抓取失败（这是常见现象，不影响整体运行）: {e}")
        return ""


def extract_article_links(url: str) -> List[str]:
    """从微信专辑页中提取文章链接（再次尝试）。"""
    if not url:
        return []
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.49"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        text = resp.text
        links = re.findall(r"https?://mp\.weixin\.qq\.com/s/[a-zA-Z0-9_-]+", text)
        return list(dict.fromkeys(links))[:10]
    except Exception as e:
        log(f"[微信] 提取文章链接失败: {e}")
        return []


def build_math_problems() -> List[str]:
    """生成 10 道口算题，作为 AI 参考/兜底。"""
    import random
    probs = []
    for _ in range(10):
        op = random.choice(["+", "-", "×"])
        if op == "+":
            a, b = random.randint(1, 99), random.randint(1, 99)
            probs.append(f"{a}+{b}")
        elif op == "-":
            a, b = random.randint(20, 99), random.randint(1, 19)
            probs.append(f"{a}-{b}")
        else:
            a, b = random.randint(2, 9), random.randint(2, 9)
            probs.append(f"{a}×{b}")
    return probs


def build_prompt(hot_items: List[Dict[str, str]], wechat_text: str) -> str:
    today = datetime.now(tz=BJ).strftime("%Y-%m-%d")
    hot_lines = []
    for it in hot_items[:25]:
        hot_lines.append(f"- [{it.get('platform', '')}] {it['title']}（热度 {it.get('hot_value', '')}）")
    hot_block = "\n".join(hot_lines) or "（今日热榜暂未能获取）"
    wc_block = (wechat_text[:2000] or "（未提供微信专辑素材）")
    style_block = (STYLE_SAMPLES.strip() or DEFAULT_STYLE)

    return f"""你是一位专为「宝妈情感共鸣 + 自媒体变现」赛道服务的内容策划与文案高手。

账号定位：面向宝妈群体，目标是通过自媒体赚到钱。内容调性——真诚、治愈、通透、有共鸣，像和闺蜜聊天，不卖弄、不说教，少用感叹号和鸡汤词。

内容公式（核心方法）：
从下面素材里挑出能打动宝妈的点，尤其是：
1) 明星发言/采访金句（如杨紫、周星驰等近期刷屏的语录）；
2) 热点歌曲歌词；
3) 人民日报式「人生感悟」类金句。
第一步：把原句提炼成「一句很通透的话」，作为文案正文（金句）。
第二步：自然关联到「宝妈做自媒体的真实情绪 / 成长 / 怎么靠内容变现」，让观众觉得“这说的不就是我吗”。

钩子写法（重要！请学习同类爆款主播）：
- 第一句 12-15 字，必须带钩子——用痛点、反差、悬念或具体数字，让人刷到就想点开。
- 常用钩子套路：身份反差（"当妈后我才懂…"）、扎心提问（"你也是这样吗？"）、反常识（"别再逼自己完美了"）、具体数字（"带娃第 365 天"）。
- 前 3 秒必须点名热点关键词（明星名/歌曲名/事件名），让搜索流量进来。
- 语气像闺蜜聊天，短句、口语、有温度，少用"家人们"这类主播腔。

## 今日热点（部分，请结合事实热度挑选素材）
{hot_block}

## 参考素材（微信文章/专辑摘要）
{wc_block}

## 风格样例（请模仿这种语感与「图文文案」结构来写）
{style_block}

## 输出要求
请只输出一个 JSON 对象，不要任何 Markdown 或解释。JSON 结构如下（inspirations 与 insights 的每个条目都必须是完整的「图文文案」）：
{{
  "date": "{today}",
  "inspirations": [
    {{
      "tag": "标签（如 杨紫/周星驰/热点歌曲/人民日报/情感/成长）",
      "title": "封面钩子句，12-15字，与 hook 一致",
      "hook": "第一句 12-15 字，带钩子（痛点/反差/悬念/数字）",
      "golden": "正文金句：明星发言/歌曲歌词/人民日报金句的原文原话，注明出处",
      "reflection": "图片上的几句话感悟，2-4 句，每句一行，闺蜜语气，戳中宝妈情绪，可截图转发",
      "belowTitle": "图片下方延续性标题（承上启下）",
      "belowBody": "图片下方延续性正文，2-4 句，落到宝妈做自媒体的共鸣/成长/变现"
    }}
  ],
  "insights": [
    {{
      "tag": "标签",
      "title": "封面钩子句，12-15字，与 hook 一致",
      "hook": "第一句 12-15 字，带钩子",
      "golden": "人生感悟金句原文（偏人民日报式/通透语录，注明出处）",
      "reflection": "图片上的几句话感悟，2-4 句，每句一行",
      "belowTitle": "图片下方延续性标题",
      "belowBody": "图片下方延续性正文，2-4 句，关联宝妈勇闯自媒体"
    }}
  ],
  "hotspots": [
    {{
      "hot": "引用的热点标题",
      "angle": "二创角度：宝妈赛道怎么切入（结合金句+感悟）",
      "copy": "可直接做封面的金句（带情绪钩子，12-20字，基于明星/歌曲/人民日报金句二创）",
      "imitate": "深度模仿：口播起手+收尾+挂什么话题+怎么剪"
    }}
  ],
  "math": ["10 道口算题字符串，如 12+34, 56-18, 7×8"]
}}

要求：
1. inspirations 10 条、insights 10 条、hotspots 10 条、math 10 条。
2. 每条 inspirations / insights 都必须严格包含 hook、golden、reflection、belowTitle、belowBody 五个字段，且 hook 必须 12-15 字并带钩子；golden 必须是原文原话（不要自己编造名言，尽量用真实明星/歌曲/人民日报语录）；reflection 是图片上的文字（2-4 句分行）；belowTitle+belowBody 是图片下方延续性正文。
3. 每天必须结合上面的「今日热点」事实热度来选题，不要空谈鸡汤；素材可来自明星发言、热点歌曲、人民日报感悟。
4. hotspots 的 copy 必须是能直接做封面的金句（带情绪钩子），imitate 给出口播结构建议。
5. 所有内容都要落到「宝妈做自媒体」——情绪共鸣、成长、或怎么赚钱。
6. math 是小学口算水平，10 题，混合加减乘，不要重复。
7. 只输出 JSON，不要任何其他文字。"""

def call_ai(prompt: str) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        log("[AI] 未配置 OPENAI_API_KEY，跳过 AI 改写，使用兜底数据。")
        return {}
    try:
        url = f"{OPENAI_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.85,
        "max_tokens": 3000,
        }
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # 提取 JSON 部分
        raw = content.strip()
        if raw.startswith("```"):
            m = re.search(r"```(?:json)?\n([\s\S]+?)\n```", raw)
            if m:
                raw = m.group(1)
            else:
                raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        log(f"[AI] 调用或解析失败: {e}")
        return {}


def fallback_data(hot_items: List[Dict[str, str]]) -> Dict[str, Any]:
    """当 AI 或网络失败时，用热榜原始标题 + 固定人生感悟生成一份可用兜底（新结构）。"""
    today = datetime.now(tz=BJ).strftime("%Y-%m-%d")
    hot_titles = [h["title"] for h in hot_items[:10]] or ["今日热点待获取"]

    def mk(tag, title, hook, golden, reflection, below_title, below_body):
        return {"tag": tag, "title": title, "hook": hook, "golden": golden,
                "reflection": reflection, "belowTitle": below_title, "belowBody": below_body}

    # 用热榜标题拼 5 条，保证“结合事实热度”；钩子固定 12-13 字，标题放进正文
    inspirations = []
    hot_hooks = [
        "刷到这条热搜我破防了",
        "原来普通妈妈都这样啊",
        "当妈后我才真正读懂它",
        "这条热搜治好了我焦虑",
        "普通人的难不必被证明",
    ]
    for i, t in enumerate(hot_titles[:5]):
        h = hot_hooks[i % len(hot_hooks)]
        inspirations.append(mk(
            "热点", h, h,
            f"刷到「{t}」那一刻，忽然懂了：普通人的难，从来不需要被证明。",
            "原来我们硬撑的时候，最该被哄的是自己。\n做自媒体也是，先把日子过顺了，镜头才骗不了人。",
            "宝妈做自媒体，别急着证明给谁看",
            "你发的每一条，都是在替千万个普通妈妈说话。先完成再完美，今天这条发出去，就比昨天离变现近一步。",
        ))
    # 再补 5 条常青选题
    inspirations += [
        mk("杨紫", "杨紫这句话，治好了我的焦虑", "杨紫这句话，治好了我的焦虑",
           "杨紫说：把生活过成自己喜欢的样子，本身就是一种成功。",
           "我们当妈的，总先顾别人，最后才轮到自己。\n今天起，把一点时间还给自己。",
           "做自媒体，先哄好自己再哄流量",
           "你状态对了，视频自然有光。宝妈做号，悦己才能长久。"),
        mk("周星驰", "星爷的通透，30岁才看懂", "星爷的通透，30岁才看懂",
           "周星驰说：做人如果没有梦想，跟咸鱼有什么分别。",
           "带娃很累，但别把自己活成咸鱼。\n搞个账号，就是给自己留一扇窗。",
           "宝妈也要有做梦的权利",
           "自媒体不是赚快钱，是给未来的自己留条路。开干吧各位。"),
        mk("人民日报", "人民日报这段话，建议宝妈抄下来", "人民日报这段话，建议宝妈抄下来",
           "人民日报写道：你只管努力，剩下的交给时间。",
           "别盯着数据焦虑，别跟别人比。\n你发的每一条，都在长肌肉。",
           "慢一点，也是在往前走",
           "今天没爆没关系，账号在生长。方向对了，就别停。"),
        mk("成长", "30岁重学技能，我从社恐变博主", "30岁重学技能，我从社恐变博主",
           "成长不是变强，是敢在不会的时候还往前走。",
           "学英语、学剪辑，磕磕绊绊也发出来。\n真实，比完美更动人。",
           "宝妈成长，从敢开始",
           "展示学习过程本身就有流量。你敢开始，就有人敢陪你。"),
        mk("变现", "宝妈号第一笔100块怎么来的", "宝妈号第一笔100块怎么来的",
           "赚钱不是羞耻，是努力最好的见证。",
           "金额不大，却让我踏实：普通妈妈也能行。\n勤快+热爱+行动=开花结果。",
           "宝妈变现，从敢谈钱开始",
           "别羞于提收益，你的真实，就是别人的底气。"),
    ]

    insights = [
        mk("坚持", "慢一点也没关系", "慢一点也没关系",
           "人民日报：你只管努力，剩下的交给时间。",
           "自媒体不是百米冲刺，是马拉松。\n今天没爆，账号也在长肌肉。",
           "方向对了，就别停",
           "每周进步一点点，时间会奖励长期主义。"),
        mk("接纳", "不完美也可以开始", "不完美也可以开始",
           "接纳普通，不是躺平，是清楚自己是谁还敢往前走。",
           "第一条视频很糙？真实比精致更动人。\n先完成，再完美。",
           "先完成，再完美",
           "发出去的第一条，胜过脑子里的一百条。"),
        mk("专注", "少看别人，多看自己", "少看别人，多看自己",
           "真正的清醒，是跳过情绪直接行动。",
           "焦虑大多来自比较。\n盯住自己的数据曲线，别盯别人的热闹。",
           "把目光收回到自己",
           "每周进步一点就赢，别人的爆款与你无关。"),
        mk("热爱", "热爱是熬过瓶颈的光", "热爱是熬过瓶颈的光",
           "把生活过成自己喜欢的样子，本身就是成功。",
           "把带娃的琐碎变成内容灵感。\n热爱会替你续航。",
           "用热爱给账号充电",
           "你喜欢的，自然会吸引同频的人。"),
        mk("成长", "妈妈也可以是学习者", "妈妈也可以是学习者",
           "没有白走的路，每一步都算数。",
           "我在学英语、学剪辑。\n展示学习过程，本身就有流量。",
           "宝妈也可以是学生",
           "你敢学，就有人敢陪你一起成长。"),
        mk("勇气", "怕被熟人看到怎么办", "怕被熟人看到怎么办",
           "真诚，是最高级的运营。",
           "把羞耻感拍出来，反而圈粉。\n你不是一个人。",
           "真诚比完美更圈粉",
           "敢露怯，才敢被爱。做自己最省力。"),
        mk("平衡", "带娃和搞事业不对立", "带娃和搞事业不对立",
           "允许自己慢慢来，是成年人最高级的清醒。",
           "用时间块管理，给宝妈一个“我也可以”。\n带娃和搞事业，能共存。",
           "平衡不是平均，是节奏",
           "找到你的节奏，一天也能做很多事。"),
        mk("价值", "你经历的就是别人的答案", "你经历的就是别人的答案",
           "你经历的就是别人的答案。",
           "普通妈妈的日常，对另一个妈妈可能是救命稻草。\n你的碎碎念有用。",
           "别小看你的日常",
           "分享出来，你就成了别人的光。"),
        mk("长期", "做难而正确的事", "做难而正确的事",
           "时间会奖励长期主义者。",
           "不追热点投机，沉淀人设。\n难而正确的事，越走越宽。",
           "长期主义，是宝妈的底气",
           "今天埋的种子，明年会开花。"),
        mk("感恩", "谢谢愿意听我说话的你", "谢谢愿意听我说话的你",
           "被看见，是普通人最温柔的幸运。",
           "定期和粉丝“对话”，把账号做成有温度的小圈子。\n你不是在做号，是在交朋友。",
           "把粉丝当闺蜜",
           "真诚的关系，才是最稳的流量。"),
    ]

    hotspots = [
        {
            "hot": h["title"],
            "angle": f"从宝妈视角解读 {h['title']} 与普通人生活的关联（结合金句+感悟）",
            "copy": f"{h['title']} 刷屏了，当妈后我更看懂这背后的情绪。",
            "imitate": f"用“热点+带娃真实瞬间”对比剪辑，结尾点题：每个妈妈都在发光。口播起手点名热点，收尾抛互动“你也是这样吗”。"
        }
        for h in hot_items[:10]
    ]
    if len(hotspots) < 10:
        placeholders = [
            {"hot": "全网都在跳的手势舞", "angle": "带娃版手势舞更吸睛", "copy": "和宝宝一起跳这个太治愈了。", "imitate": "宝宝出镜拍同款，加字幕宝妈勇闯自媒体 dayN。"},
            {"hot": "普通人逆袭视频刷屏", "angle": "宝妈逆袭叙事", "copy": "普通妈妈也能翻盘，关键是敢开始。", "imitate": "三段式：低谷→行动→小成果，配励志 BGM。"},
            {"hot": "省钱攻略类走红", "angle": "带娃省钱 10 招", "copy": "当妈后真的会精打细算，这篇太实用。", "imitate": "实拍+清单字幕，强调亲测有效。"},
            {"hot": "治愈系风景视频爆了", "angle": "带娃累了看看窗外", "copy": "当妈也需要喘口气，这片刻属于我。", "imitate": "窗边实拍+轻音乐+短文案，做情绪价值。"},
        ]
        hotspots += placeholders[:(10 - len(hotspots))]
    return {
        "date": today,
        "inspirations": inspirations[:10],
        "insights": insights[:10],
        "hotspots": hotspots[:10],
        "math": build_math_problems(),
    }

def merge_ai_with_fallback(ai_data: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """AI 返回不完整时，用兜底数据补齐。"""
    result = dict(fallback)
    if ai_data.get("date"):
        result["date"] = ai_data["date"]
    for key in ["inspirations", "insights", "hotspots"]:
        if isinstance(ai_data.get(key), list) and ai_data[key]:
            # 取 AI 返回，不足再补兜底
            items = ai_data[key]
            while len(items) < 10:
                items.append(fallback[key][len(items) % len(fallback[key])])
            result[key] = items[:10]
    if isinstance(ai_data.get("math"), list) and ai_data["math"]:
        result["math"] = ai_data["math"][:10]
    return result


def update_gist(content: Dict[str, Any]) -> None:
    if not GIST_ID or not GIST_TOKEN:
        log("[Gist] 未配置 GIST_ID / GIST_TOKEN，跳过上传。")
        return
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "files": {
            "content.json": {
                "content": json.dumps(content, ensure_ascii=False, indent=2)
            }
        }
    }
    resp = requests.patch(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    log(f"[Gist] 已更新: {resp.json().get('html_url')}")


def main() -> None:
    log(f"=== 宝妈创作工作台 · 每日更新脚本 === {datetime.now(tz=BJ).isoformat()} ===")
    if not GIST_ID or not GIST_TOKEN:
        log("提示：GIST_ID 或 GIST_TOKEN 未设置，内容只会生成到本地文件 content.json。")

    hot_items = fetch_hot_summary()
    log(f"[热点] 获取 {len(hot_items)} 条")

    wechat_text = ""
    if WECHAT_ALBUM_URL:
        # 尝试先抓取专辑页并提取文章链接
        article_links = extract_article_links(WECHAT_ALBUM_URL)
        if article_links:
            texts = []
            for link in article_links[:5]:
                t = fetch_wechat_album(link)
                if t:
                    texts.append(t)
            wechat_text = "\n".join(texts)[:3000]
        else:
            wechat_text = fetch_wechat_album(WECHAT_ALBUM_URL)
        log(f"[微信] 素材长度 {len(wechat_text)} 字符")
    else:
        log("[微信] 未配置 WECHAT_ALBUM_URL，跳过")

    fallback = fallback_data(hot_items)
    ai_data = {}
    if OPENAI_API_KEY:
        prompt = build_prompt(hot_items, wechat_text)
        ai_data = call_ai(prompt)
        if ai_data:
            log("[AI] 成功生成内容")
        else:
            log("[AI] 生成失败，使用兜底数据")
    else:
        log("[AI] 未配置 OPENAI_API_KEY，使用兜底数据")

    final = merge_ai_with_fallback(ai_data, fallback)

    # 本地写一份，方便调试
    with open("content.json", "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    log("[本地] 已写入 content.json")

    update_gist(final)
    log("=== 完成 ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
