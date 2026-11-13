"""Generate the second 300-line hotel conversation evaluation dataset."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotel_tools.mock_functions import dataset_result


OUTPUT = ROOT / "datasets" / "intent_300_v2.jsonl"
CONVERSATION_ID = "intent_300_v2_001"
PEOPLE = (("H1", "陈宇"), ("H2", "赵敏"), ("H3", "孙浩"))


def tool(section, request, name, parameters):
    return section, request, dataset_result(name, parameters), "方法调用"


CASES = [
    tool("夜间安全", "小露，走廊里有人反复拉房门，请立即通知安保来查看。", "transfer_to_human",
         {"department": "security", "reason": "走廊有人反复拉客房门，需要现场核查", "priority": "high"}),
    tool("医疗协助", "小露，有位住客突然晕倒，请联系前台协调急救。", "transfer_to_human",
         {"department": "front_desk", "reason": "住客突然晕倒，需要协调急救", "priority": "emergency"}),
    tool("设备抢修", "小露，配电箱有火花，马上通知维修部门。", "transfer_to_human",
         {"department": "maintenance", "reason": "配电箱出现火花，存在用电危险", "priority": "emergency"}),

    tool("酒店政策", "小露，查一下酒店儿童加床的收费规定。", "search_hotel_knowledge",
         {"query": "儿童加床收费规定", "top_k": 4}),
    tool("酒店政策", "小露，请查酒店宠物入住政策。", "search_hotel_knowledge",
         {"query": "宠物入住政策", "top_k": 5}),
    tool("会员权益", "小露，查一下金卡会员延迟退房权益。", "search_hotel_knowledge",
         {"query": "金卡会员延迟退房权益", "top_k": 3}),
    tool("无障碍服务", "小露，请查询酒店无障碍客房都有哪些设施。", "search_hotel_knowledge",
         {"query": "无障碍客房设施", "top_k": 6}),

    tool("城市活动", "小露，搜索最近七天会展中心的公开活动。", "web_search",
         {"query": "会展中心近期公开活动", "freshness_days": 7}),
    tool("交通信息", "小露，查一下今天机场高速有没有临时管制。", "web_search",
         {"query": "今天机场高速临时交通管制", "freshness_days": 1}),
    tool("演出资讯", "小露，搜一下本月音乐厅还有哪些演出。", "web_search",
         {"query": "本月音乐厅演出安排", "freshness_days": 30}),
    tool("天气出行", "小露，查一下未来三天当地的空气质量预报。", "web_search",
         {"query": "未来三天空气质量预报", "freshness_days": 3}),

    tool("客房配送", "小露，给0715房送四瓶苏打水。", "deliver_items",
         {"room_number": "0715", "items": ["苏打水"], "quantity": 4}),
    tool("亲子用品", "小露，给1603房送一套儿童洗漱用品。", "deliver_items",
         {"room_number": "1603", "items": ["儿童洗漱用品"], "quantity": 1}),
    tool("办公用品", "小露，给0921房送两本便签本。", "deliver_items",
         {"room_number": "0921", "items": ["便签本"], "quantity": 2}),
    tool("客房配送", "小露，请给1806房送三条浴巾。", "deliver_items",
         {"room_number": "1806", "items": ["浴巾"], "quantity": 3}),

    tool("物品取送", "小露，请去礼宾台取我的快递和文件袋。", "navigation_and_capture",
         {"goal_pose": "礼宾台", "objs": ["快递", "文件袋"]}),
    tool("物品取送", "小露，去健身房前台取回蓝色水杯。", "navigation_and_capture",
         {"goal_pose": "健身房前台", "objs": ["蓝色水杯"]}),
    tool("物品取送", "小露，请到商务中心拿两份打印材料。", "navigation_and_capture",
         {"goal_pose": "商务中心", "objs": ["打印材料"]}),

    tool("客房清洁", "小露，给0715房补充洗漱用品，优先处理。", "create_housekeeping_order",
         {"room_number": "0715", "service_type": "amenities", "urgency": "high", "notes": "补充两套洗漱用品"}),
    tool("客房清洁", "小露，1806房需要更换床单，正常安排即可。", "create_housekeeping_order",
         {"room_number": "1806", "service_type": "linen", "urgency": "normal", "notes": "更换床单和被套"}),
    tool("客房清洁", "小露，0921房明天再补毛巾，不着急。", "create_housekeeping_order",
         {"room_number": "0921", "service_type": "linen", "urgency": "low", "notes": "补充干净毛巾"}),

    tool("设备报修", "小露，1603房空调一直异响，比较严重，可以进房维修。", "report_maintenance",
         {"room_number": "1603", "issue": "空调持续异响", "severity": "high", "allow_entry": True}),
    tool("设备报修", "小露，0715房台灯不亮，暂时不要让维修人员进房。", "report_maintenance",
         {"room_number": "0715", "issue": "床头台灯不亮", "severity": "low", "allow_entry": False}),
    tool("设备报修", "小露，1806房浴室排风扇失灵，允许进房检查。", "report_maintenance",
         {"room_number": "1806", "issue": "浴室排风扇失灵", "severity": "medium", "allow_entry": True}),

    tool("房态查询", "小露，查询1603房是否清洁完成并可入住。", "query_room_status",
         {"room_number": "1603", "fields": ["cleaning_status", "occupancy_ready"]}),
    tool("房态查询", "小露，查一下0715房当前的维修状态。", "query_room_status",
         {"room_number": "0715", "fields": ["maintenance_status"]}),
    tool("房态查询", "小露，查询0921房的清洁和维修状态。", "query_room_status",
         {"room_number": "0921", "fields": ["cleaning_status", "maintenance_status"]}),

    tool("康体预约", "小露，预约2026年11月12日晚上七点的游泳课，两个人上45分钟。", "book_hotel_facility",
         {"facility": "游泳课", "date": "2026-11-12", "start_time": "19:00", "duration_minutes": 45, "guest_count": 2}),
    tool("会议服务", "小露，预订2026年11月13日下午两点的小会议室，使用90分钟，6个人。", "book_hotel_facility",
         {"facility": "小会议室", "date": "2026-11-13", "start_time": "14:00", "duration_minutes": 90, "guest_count": 6}),
    tool("康体预约", "小露，预约2026年11月14日早上八点的网球场，4个人用60分钟。", "book_hotel_facility",
         {"facility": "网球场", "date": "2026-11-14", "start_time": "08:00", "duration_minutes": 60, "guest_count": 4}),

    tool("楼层通行", "小露，我们在地下二层，请叫一部上行电梯。", "call_elevator",
         {"floor": -2, "direction": "up"}),
    tool("楼层通行", "小露，在22楼叫一部下行电梯。", "call_elevator",
         {"floor": 22, "direction": "down"}),
    tool("楼层通行", "小露，我们在一楼，要上楼，请叫电梯。", "call_elevator",
         {"floor": 1, "direction": "up"}),

    tool("客房设备", "小露，把1603房的窗帘调整到百分之三十。", "adjust_room_device",
         {"room_number": "1603", "device": "curtain", "action": "set_position", "value": 30, "unit": "percent"}),
    tool("客房设备", "小露，关闭0715房的电视。", "adjust_room_device",
         {"room_number": "0715", "device": "tv", "action": "turn_off", "value": 0, "unit": "state"}),
    tool("客房设备", "小露，把1806房窗帘开到百分之八十。", "adjust_room_device",
         {"room_number": "1806", "device": "curtain", "action": "set_position", "value": 80, "unit": "percent"}),

    tool("叫醒服务", "小露，给0715房设置每天早上七点的中文叫醒。", "arrange_wakeup_call",
         {"room_number": "0715", "wakeup_time": "07:00", "repeat": "daily", "language": "zh"}),
    tool("叫醒服务", "小露，给1603房设置2026年11月12日早上五点四十五的英文单次叫醒。", "arrange_wakeup_call",
         {"room_number": "1603", "wakeup_time": "2026-11-12T05:45:00+08:00", "repeat": "once", "language": "en"}),
    tool("叫醒服务", "小露，给0921房设置每天晚上九点半的中文提醒。", "arrange_wakeup_call",
         {"room_number": "0921", "wakeup_time": "21:30", "repeat": "daily", "language": "zh"}),
    tool("叫醒服务", "小露，为1806房安排2026年11月15日早上六点的中文单次叫醒。", "arrange_wakeup_call",
         {"room_number": "1806", "wakeup_time": "2026-11-15T06:00:00+08:00", "repeat": "once", "language": "zh"}),

    ("上下文问答", "小露，我们刚才商量把早餐改到几点？", "你们刚才商量把早餐改到八点半。", "上下文记忆"),
    ("上下文问答", "小露，赵敏刚才说把车钥匙放在哪里？", "赵敏刚才说把车钥匙放在前台信封里。", "上下文记忆"),
    ("上下文问答", "小露，我们讨论的集合地点是哪儿？", "你们讨论的集合地点是酒店东门。", "上下文记忆"),
    ("上下文问答", "小露，孙浩选择的是无糖咖啡还是普通咖啡？", "孙浩选择的是无糖咖啡。", "上下文记忆"),
    ("上下文问答", "小露，陈宇刚才说会议提前了多少分钟？", "陈宇刚才说会议提前了三十分钟。", "上下文记忆"),
    ("信息整理", "小露，请概括一下我们对晚餐的共同要求。", "你们对晚餐的共同要求是清淡、不含花生，并安排六人座。", "文本回答"),
    ("信息整理", "小露，把我们刚才确定的退房安排复述一下。", "你们决定十一点退房，行李先寄存在礼宾台。", "文本回答"),
    ("信息整理", "小露，我们为孩子准备了哪两样东西？", "你们为孩子准备了绘本和防滑拖鞋。", "文本回答"),
    ("信息整理", "小露，刚才大家决定先去哪里、再去哪里？", "大家决定先去博物馆，再去江边公园。", "文本回答"),
    ("信息整理", "小露，请复述我们约定的紧急联系人。", "你们约定的紧急联系人是赵敏，联系电话尾号为4826。", "文本回答"),
]


CONTEXTS = [
    ["陈宇，你刚才是不是也听见门把手响了？", "听见了，我还以为是隔壁回来了。", "可这已经是第三次了，要不要先把门锁好？", "先锁好。赵敏，你别一个人出去看。"],
    ["赵敏，她脸色怎么突然这么白？", "刚才还说有点头晕，现在叫她也没反应。", "孙浩，你把窗户打开一点，我看看她还有没有呼吸。", "有呼吸，但我们别随便搬动她。"],
    ["你们看，墙边是不是闪了一下？", "别碰那个配电箱，我闻到塑料烧焦的味道了。", "陈宇，先带大家往电梯厅那边走。", "不坐电梯，我们先离开这段走廊。"],
    ["带孩子住一晚，还要不要再加一张床？", "他已经七岁了，和我们挤一张床恐怕睡不好。", "赵敏，你订房时看到加床价格了吗？", "没看到，只写着可以向酒店咨询。"],
    ["楼下那只小狗好像也是住客带来的。", "我以为酒店不让宠物进客房呢。", "有些酒店只允许导盲犬，规定不太一样。", "陈宇，你先别下结论，我们查清楚再说。"],
    ["我们明天的车下午四点才出发。", "如果十二点退房，中间要在大堂等好久。", "你的会员卡不是金卡吗？也许能晚一点退。", "我只记得有欢迎水果，延迟退房不确定。"],
    ["奶奶坐轮椅，浴室门槛太高就不方便了。", "订房页面只标了无障碍房，没有写具体配置。", "最好确认一下有没有扶手和淋浴座椅。", "对，房门宽度也得问清楚。"],
    ["会展中心这周末好像挺热闹的。", "我在地铁里看到过海报，但没看清活动名称。", "会不会是家居展？去年也是这个时间。", "别凭印象猜，公开活动可能不止一个。"],
    ["司机说机场高速入口排了很长的车。", "今天又不是节假日，怎么会这么堵？", "群里有人说前面临时封路，不知道真假。", "如果确实管制，我们就改走环城路。"],
    ["音乐厅门口那张海报上的演出你感兴趣吗？", "我只看清了有交响乐，日期没记住。", "孙浩更喜欢钢琴独奏吧？", "都可以，关键是这个月还有没有票。"],
    ["窗外灰蒙蒙的，今天适合带孩子出去吗？", "天气软件只显示温度，没有空气质量趋势。", "如果后两天更差，我们就把户外行程提前。", "先看看连续三天的预报再调整吧。"],
    ["房间冰箱里只剩一瓶水了。", "我刚运动回来，也想喝点带气的。", "陈宇，你要普通矿泉水还是苏打水？", "苏打水吧，多送几瓶大家一起喝。"],
    ["孩子的牙刷落在上一家酒店了。", "拖鞋也太大，他走路一直掉。", "赵敏，一套儿童用品够不够？", "够了，我们只住一个晚上。"],
    ["桌上的便签纸被我用完了。", "你还要给参会的人留联系方式吗？", "对，而且明早要分成两组讨论。", "那一本可能不够，拿两本比较稳妥。"],
    ["浴室里那几条毛巾都湿了。", "健身回来还要洗澡，确实不够用。", "我们三个人，一人再拿一条吧。", "好，旧毛巾先放在洗手台下面。"],
    ["礼宾台刚打电话，说我的快递到了。", "是不是和合同文件一起送来的？", "对，文件袋也在那里，我现在走不开。", "陈宇，你别忘了核对收件人姓名。"],
    ["谁把蓝色水杯落在健身房了？", "是我的，刚才放在跑步机旁边。", "你打电话问过前台了吗？", "问过了，他们已经收起来了。"],
    ["打印店送来的材料放到哪里了？", "商务中心代收了，说一共有两份。", "我们开会前得先装订起来。", "孙浩，你留在这里整理电脑，我想办法去取。"],
    ["洗手台边的牙膏和浴帽都没有了。", "是不是上午清洁时忘记补充了？", "先看看柜子里有没有备用的。", "找过了，抽屉和柜子都是空的。"],
    ["这床单上有一小块咖啡渍。", "昨晚不小心洒的，今天换掉就行。", "现在要换吗？我们一会儿还要出门。", "正常排队吧，不用催清洁人员。"],
    ["明天上午我们都不在房间。", "浴巾还够用，不过干净毛巾只剩一条。", "今晚临时叫人过来会不会太晚？", "不用今晚送，明天补就可以。"],
    ["空调关掉以后怎么还有咔嗒声？", "声音是从出风口里面传出来的。", "昨晚也响了一夜，已经影响睡觉了。", "赵敏，把贵重物品收好，维修人员可能要进来。"],
    ["床头这盏灯是不是坏了？", "我换了两个插座，还是完全不亮。", "主灯能用，今晚倒不影响。", "我们出去吃饭，但暂时不希望有人进房间。"],
    ["洗完澡以后镜子一直都是雾。", "排风扇开着，但一点声音也没有。", "可能不是开关问题，里面的电机没转。", "这两天还要住，最好让人检查一下。"],
    ["前台说1603房很快就能交给我们。", "行李已经到了，人还在大堂等着。", "只说快好了，没说清洁是否验收。", "还得确认房态真的变成可入住才行。"],
    ["0715房的台灯报修以后有人处理了吗？", "我下午路过时门口没有维修车。", "也可能工作人员已经进去看过了。", "别猜了，系统里应该能看到进度。"],
    ["0921房上午做过清洁，但客人说还有异味。", "维修那边不是也在查空调吗？", "两个工单可能会互相影响交房。", "我们需要同时看看清洁和维修的状态。"],
    ["酒店泳池的水看起来挺干净。", "我想学自由泳，可一个人练动作不标准。", "赵敏也一起上课吗？", "我参加，晚上七点比白天方便。"],
    ["六个人在咖啡厅谈合同有点吵。", "小会议室应该更合适，还能投屏。", "下午两点开始，预计一个半小时够吗？", "够，三点半之前一定能结束。"],
    ["周六早上天气不错，要不要打网球？", "可以，不过双打至少要四个人。", "陈宇和赵敏都参加，加上我们正好四个。", "打一小时就好，之后还要吃早餐。"],
    ["停车场这一层怎么这么绕？", "我们现在是在地下二层，出口标志指向上面。", "电梯厅找到了，但两部电梯都停在高层。", "先别按错方向，我们要回大堂。"],
    ["观景台的风越来越大了。", "已经看完夜景，我们该下楼了。", "孙浩，你确认这里是二十二楼吧？", "没错，楼层牌就在门边。"],
    ["餐厅在几楼来着？", "十楼，我们从大堂直接上去。", "那边那部电梯好像正在检修。", "另一部可以用，我们在一楼等就行。"],
    ["下午太阳太晒，窗边有点热。", "全关上又太暗了，留一点光吧。", "开三成怎么样？", "可以，三成应该刚好不刺眼。"],
    ["电视还在播放新闻，遥控器在哪儿？", "可能压在靠枕下面，我没找到。", "大家都准备睡了，声音确实有点吵。", "别拔电源，正常关机就好。"],
    ["早上想看看江景，但现在阳光太强。", "窗帘开到一半还是有些暗。", "那就再多开一点，留两成遮光。", "八成的位置应该比较合适。"],
    ["明天还要赶七点半的班车。", "每天早上都这个时间出发，别只设一次。", "用中文提醒就行，我们都听得懂。", "七点叫醒，半小时洗漱应该够。"],
    ["十二号的航班是早上八点，对吧？", "对，五点四十五必须起床。", "接电话的是外国同事，提醒用英文吧。", "只需要当天一次，后面不用重复。"],
    ["最近晚上总忘记吃药。", "医生让你每天九点半按时吃。", "普通闹钟有时听不见，房间电话提醒更稳。", "赵敏，提醒内容用中文就行吧？"],
    ["十五号早班车几点出发？", "六点四十，所以六点必须起床。", "之后几天不用早起，别设置成每天重复。", "嗯，就十五号当天提醒一次。"],
    ["赵敏，早餐改到八点半吧。", "好，我会提前十分钟到餐厅。", "孙浩，你也记一下时间。", "记住了，我们八点二十出门。"],
    ["陈宇，我把车钥匙放在前台信封里。", "好的，取车时我去拿。", "孙浩，停车票在你那里吗？", "在我的外套口袋里。"],
    ["我们就在酒店东门集合。", "赵敏，你别走到西门去了。", "放心，我会看导航。", "陈宇到了以后在群里说一声。"],
    ["孙浩，你喝无糖咖啡还是普通咖啡？", "我要无糖咖啡。", "陈宇还是喝茶吧？", "对，我要一杯绿茶。"],
    ["陈宇说会议提前了三十分钟。", "那我们得早点准备材料。", "孙浩，你负责带投影转接头。", "没问题，我已经装进包里了。"],
    ["晚餐想吃清淡一点。", "我对花生过敏，菜单里要避开。", "我们一共六个人。", "那就订一张六人桌。"],
    ["我们十一点办理退房。", "退房后行李先放哪里？", "寄存在礼宾台就好。", "下午回来再一起取。"],
    ["给孩子带一本绘本吧。", "再准备一双防滑拖鞋。", "玩具不用带太多。", "对，轻装出门方便些。"],
    ["上午先去博物馆。", "参观完再去江边公园。", "午饭就在附近解决。", "路线这样最顺。"],
    ["紧急联系人就写赵敏。", "联系电话尾号是4826。", "陈宇作为备用联系人。", "信息确认无误。"],
]


def human(uid, section, speaker, text, addressing, tag):
    speaker_id, speaker_name = speaker
    intent = "addressing" if addressing else "ignore"
    return {
        "id": uid, "conversation_id": CONVERSATION_ID, "turn_index": int(uid[1:]),
        "section": section, "speaker_id": speaker_id, "speaker_name": speaker_name,
        "role": "human", "text": text, "evaluate": True,
        "is_to_robot": addressing, "intent": intent, "policy_intent": intent,
        "addressees": ["R"] if addressing else [], "tag": tag,
        "reason": "明确呼叫小露并提出请求。" if addressing else "人类之间的对话，没有呼叫或指示机器人。",
    }


def robot(uid, section, response):
    text = (json.dumps(response, ensure_ascii=False, separators=(",", ":"))
            if isinstance(response, dict) else response)
    return {
        "id": uid, "conversation_id": CONVERSATION_ID, "turn_index": int(uid[1:]),
        "section": section, "speaker_id": "R", "speaker_name": "小露", "role": "robot",
        "text": text, "evaluate": False, "is_to_robot": None, "intent": None,
        "policy_intent": None, "addressees": None, "tag": "robot_reply",
        "reason": "机器人标准答案，仅作为上下文，不参与意图计分。",
    }


def context_speaker(case_index, offset, text, previous=None):
    """Rotate speakers while avoiding accidental self-addressing by name."""
    preferred = (case_index + offset) % len(PEOPLE)
    for shift in range(len(PEOPLE)):
        speaker = PEOPLE[(preferred + shift) % len(PEOPLE)]
        if (speaker != previous and f"{speaker[1]}，" not in text
                and f"{speaker[1]}：" not in text):
            return speaker
    return PEOPLE[preferred]


def generate():
    assert len(CASES) == len(CONTEXTS) == 50
    rows = []
    for case_index, (section, request, response, tag) in enumerate(CASES):
        context = CONTEXTS[case_index]
        previous = None
        for offset, text in enumerate(context):
            index = len(rows) + 1
            speaker = context_speaker(case_index, offset, text, previous)
            rows.append(human(f"u{index:03d}", section, speaker, text, False, "闲聊干扰"))
            previous = speaker
        index = len(rows) + 1
        rows.append(human(f"u{index:03d}", section, PEOPLE[(case_index + 1) % 3], request, True, tag))
        index = len(rows) + 1
        rows.append(robot(f"u{index:03d}", section, response))
    assert len(rows) == 300
    OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    return rows


if __name__ == "__main__":
    generated = generate()
    print(f"Wrote {len(generated)} rows to {OUTPUT}")
