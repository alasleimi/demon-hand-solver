import importlib
import cv2
import numpy as np
import os
import pyautogui
from pynput import keyboard

def compute_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA + 1) * (yB - yA + 1)
    if interArea == 0:
        return 0.0
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)
    return interArea / float(boxAArea + boxBArea - interArea)

def non_max_suppression(detections, iou_thresh=0.3):
    if len(detections) == 0:
        return []
    box_size = 36
    boxes = np.array([[x, y, x + box_size, y + box_size, name, score] for (x, y, name, score) in detections], dtype=object)
    boxes = boxes[np.argsort([b[5] for b in boxes])[::-1]]
    keep = []
    while len(boxes) > 0:
        best = boxes[0]
        keep.append(best)
        rest = boxes[1:]
        boxes = []
        for box in rest:
            if compute_iou(best[:4], box[:4]) < iou_thresh:
                boxes.append(box)
        boxes = np.array(boxes, dtype=object) if boxes else np.empty((0, 6))
    return [(int(b[0]), int(b[1]), b[4], float(b[5])) for b in keep]

def get_hands_ocr(screenshot_path = "ocr_input.png"):
    # ------------------ Wait for keypress ------------------
    print("Waiting for key '0' to be pressed...")

    def on_press(key):
        if isinstance(key, keyboard.KeyCode):
            print(f"The key was pressed!: {key.vk}")
            
            if key.vk == 96 or key.vk == 48:
                listener.stop()
        

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    listener.join()

    # ------------------ Take Screenshot ------------------
    screenshot = pyautogui.screenshot()
    screenshot.save(screenshot_path)

    # ------------------ Load Suit Templates ------------------
    template_paths = {
        "Fire": ["fire.png", "fire_variant_2.png"],
        "Moon": ["moon.png"],
        "Stone": [
            "stone.png",
            "stone_variant_2.png",
            "stone_variant_3.png",
            "stone_variant_4.png",
            "stone_variant_5.png",
        ],
        "Sun": ["sun.png", "sun_variant_2.png", "sun_variant_3.png"],
    }

    multi_templates = {}

    for suit, files in template_paths.items():
        loaded_templates = []
        for fname in files:
            path = importlib.resources.files(__package__).joinpath(f"templates/suit/{fname}")
            if not path.is_file():
                raise FileNotFoundError(f"Missing file: {path}")
            data = path.read_bytes()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
            loaded_templates.append(img)
        multi_templates[suit] = loaded_templates

    img = cv2.imread(screenshot_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    thresholds = {"Fire": 0.6, "Moon": 0.7, "Stone": 0.7, "Sun": 0.85}
    all_detections = []

    for suit, templates in multi_templates.items():
        for tmpl in templates:
            res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= thresholds[suit])
            for pt in zip(*loc[::-1]):
                all_detections.append((pt[0], pt[1], suit, res[pt[1], pt[0]]))

    cleaned = non_max_suppression(all_detections, iou_thresh=0.3)

    y_coords = [y for (x, y, suit, score) in cleaned]
    if y_coords:
        median_y = np.median(y_coords)
        cleaned = [d for d in cleaned if abs(d[1] - median_y) <= 36]

    cleaned.sort(key=lambda x: x[0])
    card_suits = [suit for (x, y, suit, score) in cleaned]

    templates_folder = "templates/values"
    value_templates = {}

    # Check if the folder exists using importlib.resources
    try:
        templates_folder_path = importlib.resources.files(__package__).joinpath(templates_folder)
        if not templates_folder_path.is_dir():
            raise FileNotFoundError(f"Folder not found: {templates_folder_path}")
    except FileNotFoundError as e:
        raise e

    for file in templates_folder_path.iterdir():
        if file.name.endswith(".png") and file.is_file():
            parts = file.name.split('_')
            if len(parts) >= 3:
                candidate_value = parts[2]
                value_templates.setdefault(candidate_value, []).append(file)

    # ------------------ Crop and Match Values ------------------
    cropped_value_regions = []
    for (x, y, suit, score) in cleaned:
        x0 = x - 72
        x1 = x - 18
        y0 = y - 18
        y1 = y + 36
        crop = gray[y0:y1, x0:x1]
        cropped_value_regions.append(crop)

    detected_values = []
    for crop in cropped_value_regions:
        best_score = -1
        best_value = None
        for candidate, tmpl_files in value_templates.items():
            for tmpl_file in tmpl_files:
                try:
                    tmpl = cv2.imdecode(np.frombuffer(tmpl_file.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
                    if tmpl is None:
                        raise ValueError(f"Could not read image: {tmpl_file}")
                except Exception as e:
                    raise FileNotFoundError(f"Error reading template file {tmpl_file}: {e}")
                if tmpl.shape != crop.shape:
                    tmpl = cv2.resize(tmpl, (crop.shape[1], crop.shape[0]))
                score = cv2.minMaxLoc(cv2.matchTemplate(crop, tmpl, cv2.TM_CCOEFF_NORMED))[1]
                if score > best_score:
                    best_score = score
                    best_value = candidate
        detected_values.append(best_value)

    # ------------------ Return Results ------------------
    return list(zip(card_suits, detected_values))

if __name__ == "__main__":
    print(get_hands_ocr())