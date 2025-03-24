import cv2
import numpy as np
import os
import glob
from matplotlib import pyplot as plt


# =============================================================================
#  !! DEBUG ONLY !!
# This a tool for debugging ocr_hand.py
# should be ran inside the package directory
# expects the ocr_input.png file in ../ocr_input.png
# # =============================================================================

new_templates = False # set to true only if you want to save new templates
# Expected values for each card, must if correct if new_templates is True
correct_values = ["2", "5", "6", "9", "10","command-3","command-3", "prime-0"]



# ------------------ Non-Maximum Suppression with IoU ------------------

def compute_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
    if interArea == 0:
        return 0.0

    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

def non_max_suppression(detections, iou_thresh=0.3):
    if len(detections) == 0:
        return []

    box_size = 36  # Assuming templates are ~36x36
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

# ------------------ PART 1: Suit Detection ------------------

# Load suit templates (grayscale)
template_paths = {
    "Fire": ["fire.png", "fire_variant_2.png"],
    "moon": ["moon.png"],
    "diamond": ["stone.png", "stone_variant_2.png","stone_variant_3.png", "stone_variant_4.png", "stone_variant_5.png"],
    "sun": ["sun.png", "sun_variant_2.png", "sun_variant_3.png"]
}

multi_templates = {
    suit: [cv2.cvtColor(cv2.imread(f"templates/suit/{fname}"), cv2.COLOR_BGR2GRAY) for fname in files]
    for suit, files in template_paths.items()
}

# Load target card image
img = cv2.imread("../ocr_input.png")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Match with custom thresholds for suits
thresholds = {"Fire": 0.6, "moon": 0.7, "diamond": 0.7, "sun": 0.85}
all_detections = []

for suit, templates in multi_templates.items():
    for tmpl in templates:
        w, h = tmpl.shape[::-1]
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= thresholds[suit])
        for pt in zip(*loc[::-1]):
            all_detections.append((pt[0], pt[1], suit, res[pt[1], pt[0]]))

# Apply improved Non-Maximum Suppression
cleaned = non_max_suppression(all_detections, iou_thresh=0.3)
print(f"Detected {len(cleaned)} raw suit detections.")
print("Raw detections:", cleaned)
# ------------------ Remove Y-coordinate outliers ------------------

# Compute median Y of detected suit boxes
y_coords = [y for (x, y, suit, score) in cleaned]
if y_coords:
    median_y = np.median(y_coords)
    # Set a max allowable vertical deviation (in pixels)
    max_dev = np.std(y_coords)
    max_dev = min(max_dev, 36)
    print(max_dev)
    # Filter out detections too far from the median Y
    cleaned = [d for d in cleaned if abs(d[1] - median_y) <= max_dev]
print(f"Filtered {len(cleaned)} suit detections based on Y-coordinates.")
print("Filtered detections:", cleaned)
# Sort by horizontal position
cleaned.sort(key=lambda x: x[0])

# Infer suits per card based on position
card_suits = [""] * len(cleaned)
for i, (x, y, suit, score) in enumerate(cleaned):
    card_suits[i] = suit

# Draw suit detection results on a copy of the image
output = img.copy()
print(f"Detected {len(cleaned)} aligned suits:")
for i, (x, y, suit, score) in enumerate(cleaned):
    print(i, x, y, suit, score)
    cv2.rectangle(output, (x, y), (x + 36, y + 36), (0, 255, 255), 2)
    cv2.putText(output, f"{suit}{i}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

# Debug: Draw the median Y line
if y_coords:
    cv2.line(output, (0, int(median_y)), (output.shape[1], int(median_y)), (0, 0, 255), 1)

# Optionally show or save the result
# cv2.imshow("Detected Suits", output)
# cv2.waitKey(0)
# cv2.destroyAllWindows()
# cv2.imwrite("suit_detections_result.png", output)

# ------------------ PART 2: Save Cropped Boxes for Values as Templates ------------------
# Expected values for each card (order corresponds to card order)


# Create output folder for value templates
templates_folder = "templates/values"
if not os.path.exists(templates_folder):
    os.makedirs(templates_folder)

# For each detected suit, define the corresponding value region and save it.
# We also avoid overwriting existing files.
cropped_value_regions = []  # store region and position info for later detection
save = False
for i, (x, y, suit, score) in enumerate(cleaned):
    # Determine card index based on x coordinate

    
    
    # Define the box coordinates for the value region (adjust offsets as needed)
    x0 = x - 72
    x1 = x - 18
    y0 = y - 18
    y1 = y + 36
    
    # Crop the region from the grayscale image
    crop = gray[y0:y1, x0:x1]
    cropped_value_regions.append((crop, (x0, y0, x1, y1)))
    if new_templates:
        value_name = correct_values[i]
        # # # # # # Build a glob pattern to see if files for this value already exist
        pattern = os.path.join(templates_folder, f"value_template_{value_name}_*.png")
        existing_files = glob.glob(pattern)
        if existing_files:
            # find the highest index so far
            indices = []
            for file in existing_files:
                base = os.path.basename(file)
                try:
                    idx = int(base.split('_')[-1].split('.')[0])
                    indices.append(idx)
                except:
                    pass
            next_index = max(indices) + 1 if indices else 1
        else:
            next_index = 1
        
        template_filename = os.path.join(templates_folder, f"value_template_{value_name}_{next_index}.png")

        cv2.imwrite(template_filename, crop)
    
    # Optional: draw a red rectangle for visualization
    cv2.rectangle(output, (x0, y0), (x1, y1), (0, 0, 255), 2)

# Save the image with drawn boxes
cv2.imwrite("suit_detections_final.png", output)
print("Detected suits:", card_suits)
# print("Saved value templates to:", templates_folder)

# ------------------ PART 3: Detect Value for Each Cropped Region ------------------
# First, group saved templates by value candidate.
value_templates = {}
for file in os.listdir(templates_folder):
    if file.endswith(".png"):
        # Extract the candidate value from filename pattern "value_template_{value}_{n}.png"
        parts = file.split('_')
        if len(parts) >= 3:
            candidate_value = parts[2]  # e.g., "2", "command-2", etc.
            value_templates.setdefault(candidate_value, []).append(os.path.join(templates_folder, file))

# For each cropped value region (from the detected card), run matching against the saved templates
detected_values = []
for idx, (crop, (x0, y0, x1, y1)) in enumerate(cropped_value_regions):
    best_score = -1
    best_value = None
    # For each candidate value, test all its templates
    for candidate, tmpl_files in value_templates.items():
        for tmpl_file in tmpl_files:
            tmpl = cv2.imread(tmpl_file, cv2.IMREAD_GRAYSCALE)
            # Both crop and template should be of the same size.
            # If not, you might consider resizing or skipping.
            if tmpl.shape != crop.shape:
                # Resize the template to the crop size for comparison (or vice versa)
                tmpl = cv2.resize(tmpl, (crop.shape[1], crop.shape[0]))
            # Use matchTemplate; result is a single number since they are the same size.
            res = cv2.matchTemplate(crop, tmpl, cv2.TM_CCOEFF_NORMED)
            score = cv2.minMaxLoc(res)[1]  # max value
            if score > best_score:
                best_score = score
                best_value = candidate
    detected_values.append(best_value)
    # Draw the detected value on the output image near the region
    cv2.putText(output, best_value, (x0, y0 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    print(f"Detected value for card {idx}: {best_value} (score: {best_score:.3f})")

# Save final output with detected values
cv2.imwrite("detected_values.png", output)
cv2.imshow("Detected Values", output)
cv2.waitKey(0)
cv2.destroyAllWindows()
