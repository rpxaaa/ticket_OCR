import cv2
import os
import json
from paddleocr import PaddleOCR
from ultralytics import YOLO
from ticket_parser import extract_text, parse_ticket_info


def process_ticket_recognition():
    # 确保输出目录存在
    os.makedirs("output", exist_ok=True)
    # 初始化 YOLO 模型
    yolo_model = YOLO(model=r'best.pt')
    # 使用 YOLO 进行车票提取
    yolo_results = yolo_model.predict(source=r'222.png',save=False,show=False)
    # 初始化 PaddleOCR 实例
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='ch')
    # 用于存储所有解析结果
    all_ticket_info = []

    # 处理 YOLO 的检测结果
    for result in yolo_results:
        # 获取原始图像
        orig_img = result.orig_img
        # 获取检测框信息
        boxes = result.boxes
        if boxes is not None:
            # 遍历每个检测到的目标
            for i, box in enumerate(boxes):
                # 获取边界框坐标
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy)
                # 裁剪检测区域
                crop_img = orig_img[y1:y2, x1:x2]
                # 临时保存裁剪的图像用于OCR
                temp_path = f"temp_crop_{i}.png"
                cv2.imwrite(temp_path, crop_img)
                # 对裁剪区域执行 OCR
                ocr_result = ocr.predict(input=temp_path)
                print(f"检测目标 {i} 的OCR结果:")
                for res in ocr_result:
                    res.print()
                    # 保存原始OCR结果到JSON
                    json_filename = f"output/temp_crop_{i}_ocr.json"
                    res.save_to_json(json_filename)

                # 清理临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                # 从JSON文件中提取文本
                json_path = f"output/temp_crop_{i}_ocr.json"
                if os.path.exists(json_path):
                    print(f"从JSON文件读取: {json_path}")

                    # 从JSON文件中提取文本
                    ocr_texts = extract_text(json_path)

                    # 解析车票信息
                    ticket_info = parse_ticket_info(ocr_texts)
                    ticket_info["detection_id"] = i
                    all_ticket_info.append(ticket_info)

                    # 打印解析结果
                    print(f"\n检测目标 {i} 解析结果:")
                    for key, value in ticket_info.items():
                        print(f"  {key}: {value}")
                    print()
                else:
                    print(f"未找到OCR JSON文件: {json_path}")

    # 保存结构化车票信息到JSON
    with open("ticket_structured_info.json", "w", encoding="utf-8") as f:
        json.dump(all_ticket_info, f, ensure_ascii=False, indent=2)

    print(f"\n所有解析结果已保存到 ticket_structured_info.json")


if __name__ == '__main__':
    process_ticket_recognition()
