import re
import json


def extract_text(json_path):
    """
    从OCR保存的JSON文件中提取所有识别文本
    """
    texts = []
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 直接从rec_texts字段提取文本
        if "rec_texts" in data:
            texts = data["rec_texts"]
            # 过滤空字符串和纯空格文本
            texts = [txt.strip() for txt in texts if txt.strip()]
    except Exception as e:
        print(f"读取JSON文件失败: {e}")

    return texts


def parse_ticket_info(ocr_texts):
    """
    解析OCR识别的文本
    """
    ticket_info = {
        "train_code": "",
        "departure_station": "",
        "arrival_station": "",
        "datetime": "",
        "carriage": "",
        "seat_num": "",
        "berth_type": "",
        "price": "",
        "seat_type": "",
        "name": "",
        "discount_type": "",
        "detection_id": 0
    }

    print(f"OCR独立文本块列表: {ocr_texts}\n")

    # 增加全局解析（跨文本块）
    all_stations_global = []  # [(name, idx)]
    train_code = ""
    train_index = -1

    for idx, txt in enumerate(ocr_texts):
        # 提取“XX站”
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,6})站', txt):
            name = match.group(1)
            interference = {"上铺", "中铺", "下铺", "限乘", "当日", "当次", "车", "号", "开", "元", "报销", "使用"}
            if not any(w in name for w in interference):
                all_stations_global.append((name, idx))

        # 提取车次（首次出现）
        if not train_code:
            tm = re.search(r'(?<![0-9A-Z])([GDCKTZ]\d{1,4})(?![0-9A-Z])', txt)
            if tm:
                train_code = tm.group()
                train_index = idx

    ticket_info["train_code"] = train_code

    if train_index >= 0 and all_stations_global:
        dep_cands = [s for s in all_stations_global if s[1] < train_index]
        arr_cands = [s for s in all_stations_global if s[1] > train_index]
        if dep_cands:
            ticket_info["departure_station"] = dep_cands[-1][0]
        if arr_cands:
            ticket_info["arrival_station"] = arr_cands[0][0]
    elif all_stations_global:
        # 无车次：按顺序赋值
        names = [s[0] for s in all_stations_global]
        if len(names) >= 1:
            ticket_info["departure_station"] = names[0]
        if len(names) >= 2:
            ticket_info["arrival_station"] = names[1]

    # 遍历每个独立文本块，逐个匹配对应字段
    for txt in ocr_texts:
        if not ticket_info["train_code"] or not (ticket_info["departure_station"] and ticket_info["arrival_station"]):
            # 1. 查找所有“XX站”车站及其位置
            stations_in_txt = []
            for match in re.finditer(r'([\u4e00-\u9fa5]{2,6})站', txt):
                name = match.group(1)
                interference = {"上铺", "中铺", "下铺", "限乘", "当日", "当次", "车", "号", "开", "元", "报销", "使用"}
                if not any(w in name for w in interference):
                    stations_in_txt.append((name, match.start(), match.end()))

            # 2. 查找车次及其位置
            train_match = None
            if not ticket_info["train_code"]:
                train_match = re.search(r'(?<![0-9])([GDCKTZ]\d{1,4})(?![0-9])', txt)
                if train_match:
                    ticket_info["train_code"] = train_match.group(1)
                    train_start = train_match.start()
                else:
                    train_start = -1
            else:
                # 车次已知，但仍可尝试定位（用于已有车次但未处理车站的情况）
                tm = re.search(r'(?<![0-9])([GDCKTZ]\d{1,4})(?![0-9])', txt)
                train_start = tm.start() if tm else -1

            # 3. 如果有车站
            if stations_in_txt:
                # 按位置排序
                stations_in_txt.sort(key=lambda x: x[1])

                if train_start >= 0:
                    # 车次存在：找车次之后的第一个车站 → 到达站
                    arrival_candidates = [s for s in stations_in_txt if s[1] > train_start]
                    departure_candidates = [s for s in stations_in_txt if s[1] < train_start]

                    if arrival_candidates and not ticket_info["arrival_station"]:
                        ticket_info["arrival_station"] = arrival_candidates[0][0]  # 最近的右侧车站

                    if departure_candidates and not ticket_info["departure_station"]:
                        ticket_info["departure_station"] = departure_candidates[-1][0]  # 最近的左侧车站

                else:
                    # 无车次：按原逻辑，第一个是出发，第二个是到达
                    if not ticket_info["departure_station"]:
                        ticket_info["departure_station"] = stations_in_txt[0][0]
                    elif not ticket_info["arrival_station"] and len(stations_in_txt) > 1:
                        ticket_info["arrival_station"] = stations_in_txt[1][0]

        # 3. 发车时间匹配（支持中文/英文冒号，带或不带“开”字）
        if not ticket_info["datetime"]:
            # 定义多种时间格式正则（按优先级排序）
            time_patterns = [
                r'(\d{4}年\d{1,2}月)(\d{1,2})[^\d:\s]{1,3}?(\d{1,2})[:：](\d{2})开?',
                # 格式1: "2020年08月29日20：54开" 或 "2020年08月29日20:54开"
                r'(\d{4}年\d{1,2}月\d{1,2}日)[\s:：]*(\d{1,2})[:：](\d{2})开?',
                # 格式2: "2020年08月29日 20:54"（有空格）
                r'(\d{4}年\d{1,2}月\d{1,2}日)\s+(\d{1,2})[:：](\d{2})',
                # 格式3: 紧凑型 "2020年08月29日2054"
                r'(\d{4}年\d{1,2}月\d{1,2}日)(\d{2})(\d{2})',
            ]

            for i, pattern in enumerate(time_patterns):
                match = re.search(pattern, txt)
                if match:
                    if i == 0:
                        # 泛化分隔符模式：如 2025年01月18H13:46
                        year_month = match.group(1)
                        day = match.group(2).zfill(2)
                        hour = match.group(3).zfill(2)
                        minute = match.group(4).zfill(2)
                        ticket_info["datetime"] = f"{year_month}{day}日 {hour}:{minute}"
                    else:
                        date_part = match.group(1)
                        hour = match.group(2).zfill(2)
                        minute = match.group(3).zfill(2)
                        if i == 3:  # 紧凑型：YYYY年MM月DDHHMM
                            hour = match.group(2)
                            minute = match.group(3)
                        ticket_info["datetime"] = f"{date_part} {hour}:{minute}"
                    break

            # 如果没匹配到，尝试粘连时间（如 2024年02月26014:08 → 应为 2024年02月26日 14:08）
            if not ticket_info["datetime"]:
                sticky_match = re.search(r'(\d{4}年\d{1,2}月)(\d{4,6}):(\d{2})', txt)
                if sticky_match:
                    year_month = sticky_match.group(1)
                    time_digits = sticky_match.group(2)
                    minute = sticky_match.group(3).zfill(2)

                    if len(time_digits) == 4:
                        day = time_digits[:2]
                        hour = time_digits[2:]
                    elif len(time_digits) == 5:
                        day = time_digits[:2]
                        hour = time_digits[-2:]
                        # 检查：hour 是否合理（00~23）
                        if hour.isdigit() and 0 <= int(hour) <= 23:
                            pass
                        else:
                            hour = time_digits[2:4]
                    elif len(time_digits) == 6:
                        day = time_digits[:2]
                        hour = time_digits[2:4]
                    else:
                        day = time_digits[:2] if len(time_digits) >= 2 else '01'
                        hour = time_digits[2:4] if len(time_digits) >= 4 else '00'
                    # 补零并验证
                    day = day.zfill(2)
                    hour = hour.zfill(2)

                    d = int(day)
                    h = int(hour)
                    if 1 <= d <= 31 and 0 <= h <= 23:
                        ticket_info["datetime"] = f"{year_month}{day}日 {hour}:{minute}"

            # 如果已提取到时间，跳过后续字段处理
            if ticket_info["datetime"]:
                continue

        # 4. 车厢号+座位号+铺位类型匹配（重点优化：同一文本块拆分多个字段）
        if not (ticket_info["carriage"] and ticket_info["seat_num"] and ticket_info["berth_type"]):
            # 匹配格式：数字车+数字+字母号+铺位类型（如09车14F号上铺、3车02号中铺）
            combo_match = re.search(r'(\d+)车(\d+[A-F]?)号(上铺|中铺|下铺)?', txt)
            if combo_match:
                # 拆分车厢号、座位号、铺位类型
                if not ticket_info["carriage"]:
                    ticket_info["carriage"] = combo_match.group(1)
                if not ticket_info["seat_num"]:
                    ticket_info["seat_num"] = combo_match.group(2)
                if not ticket_info["berth_type"] and combo_match.group(3):
                    ticket_info["berth_type"] = combo_match.group(3)
                continue

        # 处理 03403A → 03车03A号
        if not (ticket_info["carriage"] and ticket_info["seat_num"]):
            # 主规则：03车03A号
            combo_match = re.search(r'(\d+)车(\d+[A-F]?)号', txt)
            if combo_match:
                ticket_info["carriage"] = combo_match.group(1)
                ticket_info["seat_num"] = combo_match.group(2)
                continue

            # OCR错误规则：如 "03403A" → 假设格式为 XX?XXA（6字符，最后是字母）
            if len(txt) == 6 and txt[-1] in 'ABCDEF' and txt[:2].isdigit():
                # 尝试跳过第3位（常见OCR把"车"识别为数字）
                if txt[3:-1].isdigit():  # 如 '03A' 的前部分 '03'
                    ticket_info["carriage"] = txt[:2]
                    ticket_info["seat_num"] = txt[3:]
                    continue

            # 规则2: 泛化OCR错误格式，如 "03+12C号", "05#08A号", "12&01B号"
            ocr_match = re.search(r'(\d{1,2})[^\u4e00-\u9fa5\dA-Za-z]{1,3}?(\d{1,2}[A-F]?)号', txt)
            if ocr_match:
                ticket_info["carriage"] = ocr_match.group(1)
                ticket_info["seat_num"] = ocr_match.group(2)
                continue

            # 规则3: 单独匹配车厢（如 "03车"）
            if not ticket_info["carriage"]:
                carriage_match = re.search(r'(\d+)车', txt)
                if carriage_match:
                    ticket_info["carriage"] = carriage_match.group(1)

            # 规则4: 单独匹配座位（如 "12C号"）
            if not ticket_info["seat_num"]:
                seat_match = re.search(r'(\d+[A-F]?)号', txt)
                if seat_match:
                    ticket_info["seat_num"] = seat_match.group(1)

        # 5. 单独匹配车厢号（兼容只有车厢号的文本块）
        if not ticket_info["carriage"]:
            carriage_match = re.search(r'(\d+)车', txt)
            if carriage_match:
                ticket_info["carriage"] = carriage_match.group(1)
                continue

        # 6. 单独匹配座位号（兼容只有座位号的文本块）
        if not ticket_info["seat_num"]:
            # 修改座位号匹配，支持数字+字母的组合
            seat_match = re.search(r'(\d+[A-F]?)号', txt)
            if seat_match:
                ticket_info["seat_num"] = seat_match.group(1)
                continue

        # 7. 单独匹配铺位类型（兼容只有铺位类型的文本块）
        if not ticket_info["berth_type"]:
            berth_types = ["上铺", "中铺", "下铺"]
            for berth in berth_types:
                if berth in txt:
                    ticket_info["berth_type"] = berth
                    break
            if ticket_info["berth_type"]:
                continue

        # 8. 票价匹配（处理价格被分割的情况，如['￥443.', '5元']）
        if not ticket_info["price"]:
            # 检查是否包含价格相关关键词
            price_related = any(keyword in txt for keyword in ['￥', '元'])
            if price_related:
                # 如果当前文本块包含价格相关关键词，尝试与前后文本块组合
                idx = ocr_texts.index(txt)
                # 尝试组合当前文本块和后续文本块
                combined_price = txt
                for i in range(idx + 1, min(idx + 3, len(ocr_texts))):
                    combined_price += ocr_texts[i]
                    # 检查组合后的文本是否符合价格格式
                    price_match = re.search(r'￥?(\d+\.?\d*)元?', combined_price)
                    if price_match:
                        ticket_info["price"] = price_match.group(1)
                        break

                if ticket_info["price"]:
                    continue

                # 单独匹配当前文本块
                price_match = re.search(r'￥?(\d+\.?\d*)元?', txt)
                if price_match:
                    # 只有当匹配到的数字是完整价格时才使用
                    if '.' in price_match.group(1) or len(price_match.group(1)) > 2:
                        ticket_info["price"] = price_match.group(1)
                    continue

            # 符合小数标准的字段
            decimal_match = re.search(r'(\d+\.\d+)', txt)
            if decimal_match:
                val_str = decimal_match.group(1)
                try:
                    num = float(val_str)
                    if 5 <= num <= 3000:
                        ticket_info["price"] = val_str
                except ValueError:
                    pass

        # 9. 座位类型匹配（如新车空调硬卧）
        if not ticket_info["seat_type"]:
            seat_types = ['新空调硬座', '新空调硬卧', '新空调软座', '新空调软卧',"一等座", "二等座", "商务座", "特等座", "硬座", "软座", "硬卧", "软卧"]
            for seat_type in seat_types:
                if seat_type in txt:
                    ticket_info["seat_type"] = seat_type
                    break
            if ticket_info["seat_type"]:
                continue

        # 10. 优惠类型匹配（学生票/儿童票等）
        if not ticket_info["discount_type"]:
            # 扩展优惠类型关键词，包括"学惠"
            discount_types = ["学生票", "儿童票", "优惠票", "残疾军人票", "学惠", "学", "惠"]
            for discount in discount_types:
                if discount in txt:
                    ticket_info["discount_type"] = "学生票" if discount == "学惠" or discount == '学' or discount == '惠' else discount
                    break
            if ticket_info["discount_type"]:
                continue

        # 11. 姓名匹配 - 放在优惠类型之后，避免"学惠"被误识别为姓名
        if not ticket_info["name"]:
            # 主规则：匹配「6位地区码 + 8-10位（数字+*） + 4位校验码」后面的中文
            name_match = re.search(r'(\d{6})([\d\*]{8,10})([\dXx]{4})([\u4e00-\u9fa5]+)', txt)
            if name_match:
                ticket_info["name"] = name_match.group(4).strip()
                continue
            # 备用规则1：只要有15-17位（数字+*）+ 结尾（数字/X/x），后面的中文都算姓名
            backup_match1 = re.search(r'[\d\*]{15,17}[\dXx]([\u4e00-\u9fa5]+)', txt)
            if backup_match1:
                ticket_info["name"] = backup_match1.group(1).strip()
                continue
            # 备用规则2：匹配数字+空格+中文姓名的模式（如"5678 张三"）
            backup_match2 = re.search(r'\d+\s+([\u4e00-\u9fa5]{2,6})', txt)
            if backup_match2:
                ticket_info["name"] = backup_match2.group(1).strip()
                continue
            # 备用规则3：匹配纯中文姓名（2-4个中文字符）
            # 排除常见的非姓名词汇
            non_name_words = ["学惠", "报销", "凭证", "遗失", "不补", "退票", "改签", "车站", "检票", "仅供报销使用", "等", "座"]
            if re.fullmatch(r'[\u4e00-\u9fa5]{2,6}', txt) and not any(p in txt for p in non_name_words) and "站" not in txt:
                ticket_info["name"] = txt
                continue

    return ticket_info
