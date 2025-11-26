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

    #print(f"OCR独立文本块列表: {ocr_texts}\n")

    # 定义各字段的匹配规则（正则/关键词）
    # 遍历每个独立文本块，逐个匹配对应字段
    for txt in ocr_texts:
        # 1. 车次号匹配 (G/D/C/K/T/Z开头+数字)
        if not ticket_info["train_code"]:
            train_match = re.search(r'[GDCKTZ]\d{1,4}', txt)
            if train_match:
                ticket_info["train_code"] = train_match.group()
                continue

        # 2. 出发站/到达站匹配（中文车站名，排除英文和干扰词）
        if not (ticket_info["departure_station"] and ticket_info["arrival_station"]):
            # 车站名规则：纯中文、不含干扰词、不是英文
            station_match = re.fullmatch(r'[\u4e00-\u9fa5]{2,6}(站)?', txt)
            if station_match:
                station_name = station_match.group().replace("站", "")
                interference = ["上铺", "中铺", "下铺", "限乘", "当日", "当次", "车", "号", "开", "元"]
                if not any(word in station_name for word in interference) and not re.search(r'[a-zA-Z]', txt):
                    # 优先填充出发站，再填充到达站
                    if not ticket_info["departure_station"]:
                        ticket_info["departure_station"] = station_name
                    elif not ticket_info["arrival_station"]:
                        ticket_info["arrival_station"] = station_name
                continue

        # 3. 发车时间匹配（日期+时间）
        if not ticket_info["datetime"]:
            # 处理时间被分割的情况，如['2023年', '10月', '01日', '08:30开']
            # 检查是否包含时间相关关键词
            time_related = any(keyword in txt for keyword in ['年', '月', '日', '开', ':'])
            if time_related:
                # 如果当前文本块包含时间相关关键词，尝试与前后文本块组合
                idx = ocr_texts.index(txt)
                # 尝试组合当前文本块和后续文本块
                combined_time = txt
                for i in range(idx + 1, min(idx + 4, len(ocr_texts))):
                    combined_time += ocr_texts[i]
                    # 检查组合后的文本是否符合时间格式
                    datetime_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)\s*(\d{1,2}:\d{2})开', combined_time)
                    if datetime_match:
                        ticket_info["datetime"] = f"{datetime_match.group(1)} {datetime_match.group(2)}"
                        break

                # 如果已经匹配到时间，跳过后续处理
                if ticket_info["datetime"]:
                    continue

                # 单独匹配当前文本块
                datetime_match1 = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)\s*(\d{1,2}:\d{2})', txt)
                if datetime_match1:
                    ticket_info["datetime"] = f"{datetime_match1.group(1)} {datetime_match1.group(2)}"
                    continue
                # 不带冒号
                datetime_match2 = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)\s*(\d{2})(\d{2})', txt)
                if datetime_match2:
                    hour = datetime_match2.group(2)
                    minute = datetime_match2.group(3)
                    ticket_info['datetime'] = f"{datetime_match2.group(1)} {hour}:{minute}"
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

        # 9. 座位类型匹配（如新车空调硬卧）
        if not ticket_info["seat_type"]:
            seat_types = ["一等座", "二等座", "商务座", "特等座", "硬座", "软座", "硬卧", "软卧"]
            for seat_type in seat_types:
                if seat_type in txt:
                    ticket_info["seat_type"] = seat_type
                    break
            if ticket_info["seat_type"]:
                continue

        # 10. 优惠类型匹配（学生票/儿童票等）
        if not ticket_info["discount_type"]:
            # 扩展优惠类型关键词，包括"学惠"
            discount_types = ["学生票", "儿童票", "优惠票", "残疾军人票", "学惠"]
            for discount in discount_types:
                if discount in txt:
                    ticket_info["discount_type"] = "学生票" if discount == "学惠" else discount
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
            non_name_words = ["学惠", "报销", "凭证", "遗失", "不补", "退票", "改签", "车站", "检票", "仅供报销使用"]
            if re.fullmatch(r'[\u4e00-\u9fa5]{2,6}', txt) and txt not in non_name_words:
                ticket_info["name"] = txt
                continue

    return ticket_info
