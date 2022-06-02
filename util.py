import math
import numpy as np
import cv2
from PIL import Image, ImageTk

def setPlaying(window, is_playing):
    if is_playing:
        window['-play/pause-'].update(text='Pause')
    else:
        window['-play/pause-'].update(text='Play ')

    return is_playing

def show_image(image_element, img, dsp_size=360):
    h, w = img.shape[:2]

    if h < w:
        h = dsp_size * h // w
        w = dsp_size
    else:
        w = dsp_size * w // h
        h = dsp_size

    # 長辺がdsp_sizeになるようにサイズに変換する。
    img = cv2.resize(img, dsize=(w, h))       

    if len(img.shape) == 3:
        # カラー画像の場合

        # BGRからRGBに変換する。
        image_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # RGBからPILフォーマットへ変換する。
        image_pil = Image.fromarray(image_rgb)

    else:
        # グレースケール画像の場合

        # グレースケール画像からPILフォーマットへ変換する。
        image_pil = Image.fromarray(img)

    bg_pil = Image.fromarray(np.zeros((dsp_size,dsp_size,3), dtype=np.uint8))

    x = (dsp_size - w) // 2
    y = (dsp_size - h) // 2
    bg_pil.paste(image_pil, (x,y))

    # PILフォーマットからImageTkフォーマットへ変換する。
    image_tk  = ImageTk.PhotoImage(bg_pil) 

    # 画像を表示する。
    image_element.update(data=image_tk, size=(dsp_size, dsp_size))


def center_distance(cx, cy, contour):
    # 輪郭のモーメントを計算する。
    M = cv2.moments(contour)

    if M['m00'] == 0:
        return 10000

    # モーメントから重心のXY座標を計算す。
    bx = int(M['m10']/M['m00'])
    by = int(M['m01']/M['m00'])

    # 画像の中心から物体の重心までの変位
    dx = bx - cx
    dy = by - cy

    # 画像の中心から物体の重心までの距離を返す。
    return math.sqrt(dx * dx + dy * dy)

def bounding_rect(img_width, img_height, contour):
    """外接矩形の辺の長さを返す。

    Args:
        img_width (_type_): 元画像の幅
        img_height (_type_): 元画像の高さ
        contour (_type_): 輪郭

    Returns:
        _type_: 輪郭の長さ
    """
    x,y,w,h = cv2.boundingRect(contour)

    if x < 5 or y < 5 or img_width - 5 < x + w or img_height - 5 < y + h:
        return False

    return (w + h) / (img_width + img_height) < 0.9

def getContour(bin_img):
    """二値化画像から輪郭とマスク画像を得る。

    Args:
        bin_img (_type_): 二値化画像

    Returns:
        _type_: 輪郭
    """

    # 二値化画像から輪郭のリストを得る。
    contours, hierarchy = cv2.findContours(bin_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)   #  RETR_TREE RETR_CCOMP 

    # 画像の高さと幅
    img_height, img_width = bin_img.shape[:2]

    # 画像の面積
    img_area = img_width * img_height

    # 大きさが画像の10%未満の輪郭は除く。
    contours = [ c for c in contours if 0.10 < math.sqrt(cv2.contourArea(c) / img_area) ]
    if len(contours) == 0:
        # 輪郭がない場合

        print('side len')
        return [None, None]

    # 外接矩形の辺の長さが画像の辺の長さの90%以上の輪郭は除く。
    contours = [ c for c in contours if bounding_rect(img_width, img_height, c) ]

    if len(contours) == 0:
        # 輪郭がない場合

        print('area check')
        return [None, None]

    # 画像の中心
    cx = img_width  / 2
    cy = img_height / 2

    # 重心と画像の中心との距離が最小の輪郭のインデックス
    center_idx = np.argmin( [ center_distance(cx, cy, cont) for cont in contours ] )

    # 重心と画像の中心との距離が最小の輪郭
    contour = contours[center_idx]

    # 輪郭から0と255のグレースケールの内部のマスク画像を作る。
    mask_img = np.zeros(bin_img.shape, dtype=np.uint8)
    cv2.drawContours(mask_img, [ contour ], -1, 255, -1)

    return contour, mask_img
