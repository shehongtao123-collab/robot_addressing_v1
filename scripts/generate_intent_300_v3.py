"""Generate a 300-line short-utterance dataset intended for sub-3s TTS."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_intent_300_v2 import CASES, CONTEXTS, PEOPLE, human, robot


OUTPUT = ROOT / "datasets" / "intent_300_v3.jsonl"
CONVERSATION_ID = "intent_300_v3_001"
MAX_CONTEXT_UNITS = 18
MAX_REQUEST_UNITS = 22


# One short request per v2 scenario. Tool parameters continue to be grounded by
# the immediately preceding compact history where the request omits a detail.
SHORT_REQUESTS = [
    "小露，快通知安保。",
    "小露，快联系急救。",
    "小露，快通知维修。",
    "小露，儿童加床收费吗？",
    "小露，宠物能入住吗？",
    "小露，金卡能晚退房吗？",
    "小露，无障碍房有什么？",
    "小露，近期有什么展会？",
    "小露，机场高速封路吗？",
    "小露，本月有什么演出？",
    "小露，未来三天空气好吗？",
    "小露，0715送四瓶苏打水。",
    "小露，1603送儿童用品。",
    "小露，0921送两本便签。",
    "小露，1806送三条浴巾。",
    "小露，去礼宾台取快递文件。",
    "小露，去健身房取蓝色水杯。",
    "小露，去商务中心取打印材料。",
    "小露，0715补用品，优先。",
    "小露，1806正常更换布草。",
    "小露，0921明天补毛巾。",
    "小露，1603空调异响，可进房。",
    "小露，0715台灯坏了，别进房。",
    "小露，1806排风坏了，可进房。",
    "小露，1603房能入住吗？",
    "小露，0715维修好了吗？",
    "小露，查0921清洁维修状态。",
    "小露，按刚才安排订泳课。",
    "小露，按刚才安排订会议室。",
    "小露，按刚才安排订网球场。",
    "小露，地下二层叫上行电梯。",
    "小露，22楼叫下行电梯。",
    "小露，一楼叫上行电梯。",
    "小露，1603窗帘开三成。",
    "小露，关掉0715的电视。",
    "小露，1806窗帘开八成。",
    "小露，按刚才设置叫醒。",
    "小露，按刚才设置叫醒。",
    "小露，按刚才设置叫醒。",
    "小露，按刚才设置叫醒。",
    "小露，早餐改到几点？",
    "小露，车钥匙放哪了？",
    "小露，在哪集合？",
    "小露，孙浩喝什么咖啡？",
    "小露，会议提前多久？",
    "小露，晚餐有什么要求？",
    "小露，几点退房？",
    "小露，给孩子准备了什么？",
    "小露，先去哪再去哪？",
    "小露，紧急联系人是谁？",
]


CONTEXT_REPLACEMENTS = {
    "音乐厅门口那张海报上的演出你感兴趣吗": "那场音乐会你想看吗",
    "0715房的台灯报修以后有人处理了吗": "0715的台灯修了吗",
    "最好确认一下有没有扶手和淋浴座椅": "先确认扶手和淋浴椅",
    "我们需要同时看看清洁和维修的状态": "清洁维修状态都要看",
    "前台说1603房很快就能交给我们": "1603房快交付了",
    "还得确认房态真的变成可入住才行": "还要确认能否入住",
    "楼下那只小狗好像也是住客带来的": "那只小狗是住客带的",
    "司机说机场高速入口排了很长的车": "机场高速入口堵车了",
}


NAMED_CONTEXT_REPLACEMENTS = {
    "陈宇，你刚才是不是也听见门把手响了？": "陈宇，你听见门响了吗？",
    "赵敏，她脸色怎么突然这么白？": "赵敏，她脸色怎么了？",
    "孙浩，你把窗户打开一点，我看看她还有没有呼吸。": "孙浩，把窗户打开。",
    "陈宇，先带大家往电梯厅那边走。": "陈宇，先带大家离开。",
    "赵敏，你订房时看到加床价格了吗？": "赵敏，你看到加床价了吗？",
    "陈宇，你先别下结论，我们查清楚再说。": "陈宇，先别下结论。",
    "陈宇，你要普通矿泉水还是苏打水？": "陈宇，你要苏打水吗？",
    "赵敏，一套儿童用品够不够？": "赵敏，一套够吗？",
    "陈宇，你别忘了核对收件人姓名。": "陈宇，记得核对姓名。",
    "孙浩，你留在这里整理电脑，我想办法去取。": "孙浩，你留下整理电脑。",
    "赵敏，把贵重物品收好，维修人员可能要进来。": "赵敏，先收好贵重物品。",
    "孙浩，你确认这里是二十二楼吧？": "孙浩，这里是二十二楼吧？",
    "赵敏，提醒内容用中文就行吧？": "赵敏，用中文提醒吧？",
    "赵敏，早餐改到八点半吧。": "赵敏，早餐改到八点半。",
    "孙浩，你也记一下时间。": "孙浩，你记一下时间。",
    "陈宇，我把车钥匙放在前台信封里。": "陈宇，车钥匙在前台。",
    "孙浩，停车票在你那里吗？": "孙浩，停车票在你那吗？",
    "赵敏，你别走到西门去了。": "赵敏，别走到西门。",
    "孙浩，你喝无糖咖啡还是普通咖啡？": "孙浩，你喝无糖咖啡吗？",
    "孙浩，你负责带投影转接头。": "孙浩，记得带转接头。",
}


CONTEXT_OVERRIDES = {
    27: ["十二日晚去上泳课。", "两个人参加。", "晚上七点开始。", "上四十五分钟。"],
    28: ["十三日要开会。", "六个人参加。", "下午两点开始。", "用九十分钟。"],
    29: ["十四日去打网球。", "四个人参加。", "早上八点开始。", "打一小时。"],
    36: ["我们住0715房。", "每天赶七点半班车。", "用中文提醒。", "七点叫醒。"],
    37: ["我们住1603房。", "十二日要赶早班机。", "五点四十五叫醒。", "英文提醒一次。"],
    38: ["我们住0921房。", "每天晚上要吃药。", "九点半提醒。", "用中文提醒。"],
    39: ["我们住1806房。", "十五日赶早班车。", "早上六点叫醒。", "中文提醒一次。"],
}


def spoken_units(text: str) -> int:
    """Conservative text-size proxy; real audio still requires duration QA."""
    normalized = re.sub(r"[，。！？、；：,.!?;\s]", "", text)
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z]+|\d+", normalized))


def short_context(text: str) -> str:
    if text in NAMED_CONTEXT_REPLACEMENTS:
        return NAMED_CONTEXT_REPLACEMENTS[text]
    first_clause = re.split(r"[，。？！；]", text, maxsplit=1)[0].strip()
    shortened = CONTEXT_REPLACEMENTS.get(first_clause, first_clause)
    punctuation = "？" if "？" in text else "。"
    return shortened + punctuation


def build_human(uid: str, section: str, speaker, text: str, addressing: bool, tag: str):
    row = human(uid, section, speaker, text, addressing, tag)
    row["conversation_id"] = CONVERSATION_ID
    row["reason"] = ("短句中明确呼叫小露并提出请求。" if addressing
                     else "短句属于人类之间的自然交谈，没有呼叫机器人。")
    return row


def build_robot(uid: str, section: str, response):
    row = robot(uid, section, response)
    row["conversation_id"] = CONVERSATION_ID
    return row


def choose_speaker(case_index: int, offset: int, text: str, previous):
    preferred = (case_index + offset) % len(PEOPLE)
    for shift in range(len(PEOPLE)):
        speaker = PEOPLE[(preferred + shift) % len(PEOPLE)]
        if speaker != previous and speaker[1] not in text:
            return speaker
    return PEOPLE[preferred]


def generate() -> list[dict]:
    assert len(CASES) == len(CONTEXTS) == len(SHORT_REQUESTS) == 50
    rows = []
    for case_index, ((section, _request, response, tag), context, request) in enumerate(
            zip(CASES, CONTEXTS, SHORT_REQUESTS)):
        context = CONTEXT_OVERRIDES.get(case_index, context)
        previous = None
        for offset, original in enumerate(context):
            text = short_context(original)
            assert spoken_units(text) <= MAX_CONTEXT_UNITS, (case_index, text, spoken_units(text))
            speaker = choose_speaker(case_index, offset, text, previous)
            rows.append(build_human(f"u{len(rows)+1:03d}", section, speaker, text, False, "闲聊干扰"))
            previous = speaker
        assert spoken_units(request) <= MAX_REQUEST_UNITS, (case_index, request, spoken_units(request))
        request_speaker = choose_speaker(case_index, len(context), request, previous)
        rows.append(build_human(f"u{len(rows)+1:03d}", section, request_speaker, request, True, tag))
        rows.append(build_robot(f"u{len(rows)+1:03d}", section, response))
    assert len(rows) == 300
    OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                              for row in rows), encoding="utf-8")
    return rows


if __name__ == "__main__":
    generated = generate()
    humans = [row for row in generated if row["role"] == "human"]
    addressing = [row for row in humans if row["intent"] == "addressing"]
    print(f"Wrote {len(generated)} rows to {OUTPUT}")
    print(f"Human={len(humans)}, addressing={len(addressing)}, "
          f"max_human_units={max(spoken_units(row['text']) for row in humans)}, "
          f"max_addressing_units={max(spoken_units(row['text']) for row in addressing)}")
