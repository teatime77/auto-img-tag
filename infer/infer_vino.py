import glob
import cv2
# import matplotlib.pyplot as plt
import numpy as np
import openvino
from openvino.runtime import Core
from openvino.pyopenvino import ConstOutput
import time

ie = Core()

devices = ie.available_devices

for device in devices:
    device_name = ie.get_property(device_name=device, name="FULL_DEVICE_NAME")
    print(f"{device}: {device_name}")

model = ie.read_model(model="model.xml")
compiled_model = ie.compile_model(model=model, device_name="GPU")

input_layer_ir = next(iter(compiled_model.inputs))

# Create inference request
request = compiled_model.create_infer_request()

cv2.namedWindow('window')

img_dir = '../data/ichigo/img'
for img_path in glob.glob(f'{img_dir}/*.png'):
    bmp = cv2.imread(img_path)

    img = bmp.astype(np.float32)
    img = img / 255.0

    img = cv2.resize(img, dsize=(1280,1280))

    img = img.transpose(2, 0, 1)
    img = img[np.newaxis, :, :, :]

    start_time = time.time()
    ret = request.infer({input_layer_ir.any_name: img})
    sec = '%.1f' % (time.time() - start_time)
    
    print(sec, img_path, type(ret))

    scores = [None] * 5
    boxes  = [None] * 5

    score_names = [ 'score_1', 'score_2', 'score_3', 'score_4', 'score_5' ]
    box_names = [ 'box_1', 'box_2', 'box_3', 'box_4', 'box_5' ]
    for k, v in ret.items():
        assert type(k) is ConstOutput
        print("    ", type(k), type(k.names), k.names, type(v), v.shape)

        name = k.any_name
        if name in score_names:
           score_idx =  score_names.index(name)
           scores[score_idx] = v

        if name in box_names:
            box_idx = box_names.index(name)
            boxes[box_idx] = v

    max_score = 0
    max_score_idx = 0
    for score_idx, score in enumerate(scores):
        idx = np.unravel_index(score.argmax(), score.shape)
        if max_score < score[idx]:
            max_score = score[idx]
            max_score_idx = score_idx
            max_idx = idx
    b, a, row, col = max_idx
    a1 = a * 6
    a2 = (a + 1) * 6
    score = scores[max_score_idx]
    box = boxes[max_score_idx]
    print("    ", sec, scores[max_score_idx].shape, box.shape, max_idx, max_score, score[max_idx], box[0, a1:a2, row, col])

    bmp_h = bmp.shape[0]
    bmp_w = bmp.shape[1]

    num_box_h = box.shape[2]
    num_box_w = box.shape[3]

    box_h = bmp_h / num_box_h
    box_w = bmp_w / num_box_w

    cy = int(row * box_h + box_h / 2) 
    cx = int(col * box_w + box_w / 2)

    cv2.circle(bmp, (int(cx), int(cy)), 10, (255,255,255), -1)

    cv2.imshow('window', bmp)
    k = cv2.waitKey(0)
    if k == ord('q'):
        break
    print('next')
