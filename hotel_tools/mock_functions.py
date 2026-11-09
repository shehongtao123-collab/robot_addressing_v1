"""Local, side-effect-free pseudo tools derived from dataset gold answers.

``TOOL_DEFINITIONS`` can be passed as the OpenAI-compatible ``tools`` request
parameter.  ``dispatch_methed`` simulates execution without contacting any
hotel system, device, search service, or human department.

The dataset intentionally uses the key ``methed``.  Keep that spelling when
converting a tool call back to the dataset's expected result format.
"""

from __future__ import annotations

import json
from datetime import date, datetime
import re
from typing import Any


def _tool(name: str, description: str, properties: dict, required: list[str]):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required,
                       "additionalProperties": False}}}


STRING = lambda description: {"type": "string", "description": description}
INTEGER = lambda description: {"type": "integer", "description": description}
NUMBER = lambda description: {"type": "number", "description": description}
BOOLEAN = lambda description: {"type": "boolean", "description": description}
STRINGS = lambda description: {"type": "array", "items": {"type": "string"}, "description": description}
ENUM = lambda description, values: {"type": "string", "enum": values, "description": description}
ENUMS = lambda description, values: {"type": "array", "items": {"type": "string", "enum": values}, "description": description}


TOOL_DEFINITIONS = [
    _tool("adjust_room_device", "调整客房设备的状态或设定值。", {
        "room_number": STRING("房间号字符串，例如 0806；不得返回数字"),
        "device": ENUM("设备英文枚举", ["tv", "curtain"]),
        "action": ENUM("操作英文枚举", ["turn_off", "set_position"]),
        "value": {**NUMBER("目标数值；turn_off 时为 0，set_position 时为 0 到 100"), "minimum": 0, "maximum": 100},
        "unit": ENUM("数值单位；关闭状态使用 state，位置百分比使用 percent", ["state", "percent"])},
        ["room_number", "device", "action", "value", "unit"]),
    _tool("arrange_wakeup_call", "为指定房间安排叫醒服务。", {
        "room_number": STRING("房间号字符串，例如 0806；不得返回数字"),
        "wakeup_time": {"type": "string", "pattern": r"^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?|\d{2}:\d{2})$",
                        "description": "单次叫醒使用 ISO 8601 日期时间（YYYY-MM-DDTHH:MM:SS，可带时区），每日重复使用 HH:MM；禁止使用明天等相对时间"},
        "repeat": ENUM("重复规则", ["once", "daily"]), "language": ENUM("服务语言", ["zh", "en"])},
        ["room_number", "wakeup_time", "repeat", "language"]),
    _tool("book_hotel_facility", "预订酒店设施或课程。", {
        "facility": STRING("设施或课程名称，可使用中文"),
        "date": {"type": "string", "format": "date", "pattern": r"^\d{4}-\d{2}-\d{2}$", "description": "ISO 8601 日期，YYYY-MM-DD"},
        "start_time": {"type": "string", "pattern": r"^(?:[01]\d|2[0-3]):[0-5]\d$", "description": "24 小时时间，HH:MM"},
        "duration_minutes": INTEGER("时长，分钟"),
        "guest_count": INTEGER("参加人数")},
        ["facility", "date", "start_time", "duration_minutes", "guest_count"]),
    _tool("call_elevator", "呼叫指定楼层的电梯。", {
        "floor": INTEGER("楼层"), "direction": ENUM("方向", ["up", "down"])},
        ["floor", "direction"]),
    _tool("create_housekeeping_order", "创建客房服务工单。", {
        "room_number": STRING("房间号字符串"), "service_type": ENUM("服务类型英文枚举", ["amenities", "linen"]),
        "urgency": ENUM("紧急程度", ["low", "normal", "high"]), "notes": STRING("服务说明")},
        ["room_number", "service_type", "urgency", "notes"]),
    _tool("deliver_items", "向指定房间配送物品。", {
        "room_number": STRING("房间号字符串"), "items": STRINGS("物品名称列表，可使用中文"),
        "quantity": INTEGER("每种物品的数量")}, ["room_number", "items", "quantity"]),
    _tool("navigation_and_capture", "导航至目标地点并取回指定物品。", {
        "goal_pose": STRING("目标地点"), "objs": STRINGS("需要取回的物品")},
        ["goal_pose", "objs"]),
    _tool("query_room_status", "查询指定客房的状态字段。", {
        "room_number": STRING("房间号字符串"), "fields": ENUMS("要查询的状态字段英文枚举", ["cleaning_status", "occupancy_ready", "maintenance_status"])},
        ["room_number", "fields"]),
    _tool("report_maintenance", "提交客房设备维修报告。", {
        "room_number": STRING("房间号字符串"), "issue": STRING("故障描述，可使用中文"),
        "severity": ENUM("严重程度", ["low", "medium", "high"]), "allow_entry": BOOLEAN("是否允许工作人员进入")},
        ["room_number", "issue", "severity", "allow_entry"]),
    _tool("search_hotel_knowledge", "查询酒店内部知识库。", {
        "query": STRING("查询内容，可使用中文"),
        "top_k": {**INTEGER("最多返回的相关知识片段数量，只校验整数类型，不与标准答案逐值比较"), "minimum": 1}}, ["query", "top_k"]),
    _tool("transfer_to_human", "将请求转接给酒店人工部门。", {
        "department": ENUM("目标部门", ["security", "front_desk", "maintenance"]), "reason": STRING("转接原因"),
        "priority": ENUM("优先级", ["normal", "high", "emergency"])}, ["department", "reason", "priority"]),
    _tool("web_search", "查询需要互联网或时效性信息的内容。", {
        "query": STRING("搜索关键词，可使用中文"),
        "freshness_days": {**INTEGER("向前检索多少天内的信息，只校验整数类型，不与标准答案逐值比较"), "minimum": 0}},
        ["query", "freshness_days"]),
]


TOOL_SCHEMAS = {item["function"]["name"]: item["function"]["parameters"] for item in TOOL_DEFINITIONS}


def normalize_dataset_parameters(name: str, parameters: dict[str, Any]):
    """Normalize legacy dataset values to the current tool schema types."""
    normalized = dict(parameters)
    if "room_number" in normalized:
        normalized["room_number"] = str(normalized["room_number"])
    if name == "adjust_room_device":
        normalized["device"] = {"电视": "tv", "窗帘": "curtain"}.get(normalized.get("device"), normalized.get("device"))
        old_value = normalized.get("value")
        if isinstance(old_value, str) and old_value.endswith("%") and old_value[:-1].isdigit():
            normalized["value"], normalized["unit"] = int(old_value[:-1]), "percent"
        elif old_value == "off":
            normalized["value"], normalized["unit"] = 0, "state"
    return normalized


def _pseudo(name: str, parameters: dict[str, Any]):
    return {"ok": True, "simulated": True, "methed": name, "parameters": parameters,
            "message": f"本地伪工具 {name} 已接收参数；未执行任何真实操作。"}


def adjust_room_device(room_number: str, device: str, action: str, value: int | float, unit: str):
    return _pseudo("adjust_room_device", locals())


def arrange_wakeup_call(room_number: str, wakeup_time: str, repeat: str, language: str):
    return _pseudo("arrange_wakeup_call", locals())


def book_hotel_facility(facility: str, date: str, start_time: str, duration_minutes: int, guest_count: int):
    return _pseudo("book_hotel_facility", locals())


def call_elevator(floor: int, direction: str):
    return _pseudo("call_elevator", locals())


def create_housekeeping_order(room_number: str, service_type: str, urgency: str, notes: str):
    return _pseudo("create_housekeeping_order", locals())


def deliver_items(room_number: str, items: list[str], quantity: int):
    return _pseudo("deliver_items", locals())


def navigation_and_capture(goal_pose: str, objs: list[str]):
    return _pseudo("navigation_and_capture", locals())


def query_room_status(room_number: str, fields: list[str]):
    return _pseudo("query_room_status", locals())


def report_maintenance(room_number: str, issue: str, severity: str, allow_entry: bool):
    return _pseudo("report_maintenance", locals())


def search_hotel_knowledge(query: str, top_k: int):
    return _pseudo("search_hotel_knowledge", locals())


def transfer_to_human(department: str, reason: str, priority: str):
    return _pseudo("transfer_to_human", locals())


def web_search(query: str, freshness_days: int):
    return _pseudo("web_search", locals())


HANDLERS = {function.__name__: function for function in (
    adjust_room_device, arrange_wakeup_call, book_hotel_facility, call_elevator,
    create_housekeeping_order, deliver_items, navigation_and_capture,
    query_room_status, report_maintenance, search_hotel_knowledge,
    transfer_to_human, web_search,
)}


def _validate(name: str, parameters: dict[str, Any]):
    if name not in TOOL_SCHEMAS:
        raise ValueError(f"unknown methed: {name}")
    schema = TOOL_SCHEMAS[name]
    expected, actual = set(schema["required"]), set(parameters)
    if actual != expected:
        raise ValueError(f"{name} parameters mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    python_types = {"string": str, "integer": int, "boolean": bool, "array": list,
                    "number": (int, float)}
    for key, value in parameters.items():
        wanted = schema["properties"][key]["type"]
        valid_type = (type(value) in python_types[wanted] if isinstance(python_types[wanted], tuple)
                      else type(value) is python_types[wanted])
        if not valid_type:
            raise TypeError(f"{name}.{key} must be {wanted}, got {type(value).__name__}")
        if wanted == "array" and not all(isinstance(item, str) for item in value):
            raise TypeError(f"{name}.{key} must contain only strings")
        if "enum" in schema["properties"][key] and value not in schema["properties"][key]["enum"]:
            raise ValueError(f"{name}.{key} must be one of {schema['properties'][key]['enum']}")
        item_enum = schema["properties"][key].get("items", {}).get("enum")
        if item_enum and any(item not in item_enum for item in value):
            raise ValueError(f"{name}.{key} items must be one of {item_enum}")
        minimum, maximum = schema["properties"][key].get("minimum"), schema["properties"][key].get("maximum")
        if minimum is not None and value < minimum:
            raise ValueError(f"{name}.{key} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise ValueError(f"{name}.{key} must be <= {maximum}")
        pattern = schema["properties"][key].get("pattern")
        if pattern and not re.fullmatch(pattern, value):
            raise ValueError(f"{name}.{key} has invalid format")
        if schema["properties"][key].get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name}.{key} must be a valid ISO 8601 date") from exc
    if name == "arrange_wakeup_call":
        wakeup_time = parameters["wakeup_time"]
        try:
            if parameters["repeat"] == "daily":
                datetime.strptime(wakeup_time, "%H:%M")
            else:
                datetime.fromisoformat(wakeup_time.replace("Z", "+00:00"))
                if "T" not in wakeup_time:
                    raise ValueError
        except ValueError as exc:
            expected = "HH:MM" if parameters["repeat"] == "daily" else "ISO 8601 date-time"
            raise ValueError(f"arrange_wakeup_call.wakeup_time must be {expected} for repeat={parameters['repeat']}") from exc
    if name == "adjust_room_device":
        expected_unit = "state" if parameters["action"] == "turn_off" else "percent"
        if parameters["unit"] != expected_unit:
            raise ValueError(f"adjust_room_device.unit must be {expected_unit} for action {parameters['action']}")


def dispatch_methed(name: str, parameters: dict[str, Any]):
    """Validate and simulate a successful local tool execution."""
    _validate(name, parameters)
    return HANDLERS[name](**parameters)


def dataset_result(name: str, parameters: dict[str, Any]):
    """Convert a native function call to the exact shape used by the datasets."""
    _validate(name, parameters)
    return {"methed": name, "parameters": parameters}


def tool_call_content(name: str, arguments: str):
    """Validate a native tool call and serialize it like a dataset answer."""
    try:
        parameters = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} arguments are not valid JSON: {exc}") from exc
    if not isinstance(parameters, dict):
        raise ValueError(f"{name} arguments must be a JSON object")
    return json.dumps(dataset_result(name, parameters), ensure_ascii=False, separators=(",", ":"))

