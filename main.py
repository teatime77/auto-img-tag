import os
import sys
import math
import random
import argparse
import glob
import cv2
import numpy as np
import PySimpleGUI as sg
from odtk import _corners2rotatedbbox, ODTK
from yolo_v5 import YOLOv5
from util import spin, show_image, getContour, edge_width, setPlaying

data_size = 1000
playing = False
network = None

hue_shift = 10
saturation_shift = 15
value_shift = 15

classIdx = 0
imageClasses = []

# 背景画像ファイルのインデックス
bgImgIdx = 0

V_lo = 250

S_mag =  100
V_mag =  100


class ImageClass:
    """画像のクラス(カテゴリー)
    """
    def __init__(self, name, class_dir):
        self.name = name
        self.classDir = class_dir
        self.videoPathes = []


def initCap():
    """動画のキャプチャーの初期処理をする。

    Returns:
        VideoCapture: キャプチャー オブジェクト
    """
    global VideoIdx, playing

    # 動画ファイルのパス
    video_path = imageClasses[classIdx].videoPathes[VideoIdx]

    # 動画のキャプチャー オブジェクト
    cap = cv2.VideoCapture(video_path)    

    if not cap.isOpened():
        print("動画再生エラー")
        sys.exit()

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    window['-img-pos-'].update(range=(0, frame_count))
    window['-img-pos-'].update(value=0)
    print(f'再生開始 フレーム数:{cap.get(cv2.CAP_PROP_FRAME_COUNT)} {os.path.basename(video_path)}')

    playing = setPlaying(window, True)

    return cap

def stopSave():
    global VideoIdx, classIdx, network, playing

    network.save()

    VideoIdx = 0
    classIdx = 0
    network = None

    playing = setPlaying(window, False)
    # cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

def readCap():
    global cap, VideoIdx, classIdx

    ret, frame = cap.read()
    if ret:
        # 画像が取得できた場合

        # 動画の現在位置
        pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

        # 動画の現在位置の表示を更新する。
        window['-img-pos-'].update(value=pos)

        showVideo(frame)

        if network is not None:
            # 保存中の場合

            # 取得画像枚数
            images_cnt = network.images_cnt()

            window['-images-cnt-'].update(f'  {images_cnt}枚')

            # 現在のクラスのテータ数をカウントアップ
            class_data_cnt[classIdx] += 1

            if data_size <= class_data_cnt[classIdx]:
                # 現在のクラスのテータ数が指定値に達した場合

                # キャプチャー オブジェクトを解放する。
                cap.release()

                if data_size <= min(class_data_cnt):
                    # すべてのクラスのデータ数が指定値に達した場合

                    stopSave()
                    print("保存終了")

                else:
                    # データ数が指定値に達していないクラスがある場合

                    # データ数が最小のクラスのインデックス
                    classIdx = class_data_cnt.index(min(class_data_cnt))

                    # 動画のインデックス
                    VideoIdx = 0

                    cap = initCap()

    else:
        # 動画の終わりの場合

        # 動画のインデックスをカウントアップ
        VideoIdx += 1

        # キャプチャー オブジェクトを解放する。
        cap.release()

        if VideoIdx < len(imageClasses[classIdx].videoPathes):
            # 同じクラスの別の動画ファイルがある場合

            cap = initCap()
        else:
            # 同じクラスの別の動画ファイルがない場合

            # データ数が最小のクラスのインデックス
            classIdx = class_data_cnt.index(min(class_data_cnt))

            # 動画のインデックス
            VideoIdx = 0

            cap = initCap()


def augment_color(img):
    # BGRからHSVに変える。
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV) 

    # HSVの各チャネルに対し
    for channel, shift in enumerate([hue_shift, saturation_shift, value_shift]):
        if shift == 0:
            continue

        # 変化量を乱数で決める。
        change = np.random.randint(-shift, shift)

        if channel == 0:
            # 色相の場合

            data = hsv_img[:, :, channel].astype(np.int32)

            # 変化後の色相が0～180の範囲に入るように色相をずらす。
            data = (data + change + 180) % 180

        else:
            # 彩度や明度の場合

            data  = hsv_img[:, :, channel].astype(np.float32)

            # 変化量は百分率(%)として作用させる。
            data  = (data * ((100 + change) / 100.0) ).clip(0, 255)

        # 変化させた値をチャネルにセットする。
        hsv_img[:, :, channel] = data.astype(np.uint8)

    # HSVからBGRに変える。
    return cv2.cvtColor(hsv_img, cv2.COLOR_HSV2BGR)
        

def rotate_corners(box):
    rad45 = math.radians(45)

    for i1 in range(4):
        i2 = (i1 + 1) % 4

        dx = box[i2][0] - box[i1][0]
        dy = box[i2][1] - box[i1][1]

        theta = math.atan2(dy, dx)
        if abs(theta) <= rad45:
            return box[i1:] + box[:i1]

    return None


def showVideo(frame):
    global bgImgPaths, bgImgIdx

    # 原画を表示する。
    show_image(window['-image11-'], frame)

    # グレー画像を表示する。
    gray_img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 
    show_image(window['-image12-'], gray_img)

    # 二値画像を表示する。
    bin_img = 255 - cv2.inRange(gray_img, V_lo, 255)
    show_image(window['-image13-'], bin_img)

    # 輪郭とマスク画像とエッジ画像を得る。
    contour, mask_img, edge_img = getContour(bin_img)
    if contour is None:
        return

    aug_img = augment_color(frame)

    # 元画像にマスクをかける。
    clip_img = aug_img * mask_img

    cv2.drawContours(clip_img, [ contour ], -1, (255,0,0), edge_width)

    # 回転を考慮した外接矩形を得る。
    rect = cv2.minAreaRect(contour)

    # 外接矩形の頂点
    box = cv2.boxPoints(rect)

    # 外接矩形を描く。
    cv2.drawContours(clip_img, [ np.int0(box) ], 0, (0,255,0), 2)

    # マスクした元画像を表示する。
    show_image(window['-image21-'], clip_img)

    # 最小外接円の中心と半径
    (cx, cy), radius = cv2.minEnclosingCircle(contour)    

    # 最小外接円を描く。
    cv2.circle(clip_img, (int(cx), int(cy)), int(radius), (255,255,255), 1)

    # 画像の高さと幅
    height, width = aug_img.shape[:2]

    # 画像の短辺の長さ
    min_size = min(height, width)

    # 物体の直径
    diameter = 2 * radius

    # 最大スケール = 画像の短辺の30% ÷ 物体の直径
    max_scale = (0.3 * min_size) / diameter

    # 最小スケール = 画像の短辺の20% ÷ 物体の直径
    min_scale = (0.2 * min_size) / diameter

    # 乱数でスケールを決める。
    scale = random.uniform(min_scale, max_scale)

    # スケール変換後の半径   
    radius2 = scale * radius

    # 乱数で移動量を決める。
    margin = 1
    dx = random.uniform(radius2 - cx + margin, width - radius2 - cx - margin)
    dy = random.uniform(radius2 - cy + margin, height - radius2 - cy - margin)

    assert radius2 <= cx + dx and cx + dx <= width - radius2
    assert radius2 <= cy + dy and cy + dy <= height - radius2

    # 乱数で回転量を決める。
    angle = random.uniform(-180, 180)

    # 回転とスケール
    m1 = cv2.getRotationMatrix2D((cx,cy), angle, scale)
    m1 = np.concatenate((m1, np.array([[0.0, 0.0, 1.0]])))

    # 平行移動
    m2 = np.array([
        [ 1, 0, dx], 
        [ 0, 1, dy], 
        [ 0, 0,  1]
    ], dtype=np.float32)

    m3 = np.dot(m2, m1)
    M = m3[:2,:]

    # 画像に変換行列を作用させる。
    dst_img2 = cv2.warpAffine(clip_img, M, (width, height))
    aug_img2 = cv2.warpAffine(aug_img, M, (width, height))
    mask_img2 = cv2.warpAffine(mask_img, M, (width, height))
    edge_img2 = cv2.warpAffine(edge_img, M, (width, height))

    # 背景画像ファイルを読む。
    bg_img = cv2.imread(bgImgPaths[bgImgIdx])
    bgImgIdx = (bgImgIdx + 1) % len(bgImgPaths)

    # 背景画像を元画像と同じサイズにする。
    bg_img = cv2.resize(bg_img, dsize=aug_img.shape[:2])                    

    # 内部のマスクを使って、背景画像と元画像を合成する。
    compo_img = np.where(mask_img2 == 0, bg_img, aug_img2)

    # 背景と元画像を7対3の割合で合成する。
    blend_img = cv2.addWeighted(bg_img, 0.7, aug_img2, 0.3, 0.0)

    # 縁の部分をブレンドした色で置き換える。
    compo_img = np.where(edge_img2 == 0, compo_img, blend_img)

    # 頂点に変換行列をかける。
    corners2 = [ np.dot(M, np.array(p + [1])).tolist() for p in box.tolist() ]

    # 最初の頂点から2番目の頂点へ向かう辺の角度が±45°以下になるように、頂点の順番を変える。
    corners2 = rotate_corners(corners2)
    if corners2 is None:
        print('slope is None')
        
        return

    # 座標変換後の外接矩形を描く。
    cv2.drawContours(dst_img2, [ np.int0(corners2)  ], 0, (0,255,0), 2)

    # バウンディングボックスと回転角を得る。
    bounding_box = _corners2rotatedbbox(corners2)
    x, y, w, h, theta = bounding_box

    # バウンディングボックスを描く。
    cv2.rectangle(dst_img2, (int(x),int(y)), (int(x+w),int(y+h)), (0,0,255), 3)

    # バウンディングボックスの左上の頂点の位置に円を描く。
    cv2.circle(dst_img2, (int(x), int(y)), 10, (255,255,255), -1)


    show_image(window['-image22-'], dst_img2)

    show_image(window['-image23-'], compo_img)

    if network is not None:

        # 動画の現在位置
        pos = cap.get(cv2.CAP_PROP_POS_FRAMES)

        network.add_image(classIdx, VideoIdx, pos, compo_img, corners2, bounding_box)

def make_image_classes(video_dir):
    global imageClasses

    imageClasses = []

    for class_dir in glob.glob(f'{video_dir}/*'):
        category_name = os.path.basename(class_dir)

        img_class = ImageClass(category_name, class_dir)
        imageClasses.append(img_class)

        # クラスのフォルダ内の動画ファイルに対し
        for video_path in glob.glob(f'{class_dir}/*'):

            video_path_str = str(video_path).replace('\\', '/')

            img_class.videoPathes.append(video_path_str)


def get_tree_data():
    treedata = sg.TreeData()

    # すべてのクラスに対し
    for img_class in imageClasses:
        treedata.Insert('', img_class.name, img_class.name, values=[])

        # クラスの動画に対し
        for video_path in img_class.videoPathes:
            video_name = os.path.basename(video_path)
            treedata.Insert(img_class.name, video_path, video_name, values=[video_path])

    return treedata

def saveImgs():
    global cap, VideoIdx, classIdx

    VideoIdx = 0

    cap = initCap()

def showImgPos():
    if cap is not None:
        pos = int(values['-img-pos-'])
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        readCap()

def parse(args):
    parser = argparse.ArgumentParser(description='Auto Image Tag')
    parser.add_argument('-i','--input', type=str, help='path to videos')
    parser.add_argument('-bg', type=str, help='path to background images')
    parser.add_argument('-o','--output', type=str, help='path to outpu')

    return parser.parse_args(args)

if __name__ == '__main__':
    args = parse(sys.argv[1:])

    print(args)

    print(cv2.getBuildInformation())

    # 動画ファイルのフォルダのパス
    video_dir = args.input.replace('\\', '/')

    # 背景画像ファイルのフォルダのパス
    bg_img_dir = args.bg.replace('\\', '/')

    # 出力先フォルダのパス
    output_dir = args.output.replace('\\', '/')

    # 出力先フォルダを作る。
    os.makedirs(output_dir, exist_ok=True)

    # 背景画像ファイルのパス
    bgImgPaths = [ x for x in glob.glob(f'{bg_img_dir}/*') if os.path.splitext(x)[1] in [ '.jpg', '.png' ] ]

    print(f'背景画像数:{len(bgImgPaths)}')

    make_image_classes(video_dir)

    # ツリー表示のデータを作る。
    treedata = get_tree_data()

    sg.theme('DarkAmber')   # Add a touch of color

    # All the stuff inside your window.
    layout = [  
        [ sg.Tree(data=treedata,
                headings=[],
                auto_size_columns=True,
                num_rows=24,
                col0_width=50,
                key="-tree-",
                show_expanded=False,
                enable_events=True),
            sg.Column([
                [ sg.Image(filename='', size=(256,256), key='-image11-') ],
                [ sg.Image(filename='', size=(256,256), key='-image21-') ]
            ])
            ,
            sg.Column([
                [ sg.Image(filename='', size=(256,256), key='-image12-') ],
                [ sg.Image(filename='', size=(256,256), key='-image22-') ]
            ])
            ,
            sg.Column([
                [ sg.Image(filename='', size=(256,256), key='-image13-') ],
                [ sg.Image(filename='', size=(256,256), key='-image23-') ]
            ])
        ]
        ,
        [ sg.Slider(range=(0,100), default_value=0, size=(100,15), orientation='horizontal', change_submits=True, key='-img-pos-') ]
        ,
        [ sg.Input(str(data_size), key='-data-size-', size=(6,1)), sg.Text('', size=(6,1), key='-images-cnt-') ]
        ,
        [ sg.Frame('Color Augmentation', [
            spin('Hue', '-hue-shift-', hue_shift, 0, 30),
            spin('Saturation', '-saturation-shift-', saturation_shift, 0, 50),
            spin('Value', '-value-shift-', value_shift, 0, 50)
        ])]
        ,
        spin('V lo', '-Vlo-', V_lo, 0, 255),
        [ sg.Text('network', size=(6,1)), sg.Combo(['ODTK', 'YOLOv5'], default_value = 'YOLOv5', key='-network-') ],
        [ sg.Button('Play', key='-play/pause-'), sg.Button('Save All', key='-save-all-'), sg.Button('Close')] ]

    # Create the Window
    window = sg.Window('Window Title', layout)

    # tree = window['-tree-']
    # tree.add_treeview_data(node)

    # Event Loop to process "events" and get the "values" of the inputs


    cap = None
    while True:
        # event, values = window.read()
        event, values = window.read(timeout=1)

        if event == sg.WIN_CLOSED or event == 'Close': # if user closes window or clicks cancel
            break

        if event == '-tree-':
            print(f'クリック [{values[event]}] [{values[event][0]}]')

            # クリックされたノードのvaluesの最初の値
            video_path = values[event][0]

            if os.path.isfile(video_path):
                # 動画ファイルの場合

                if cap is not None:
                    # 再生中の場合

                    # キャプチャー オブジェクトを解放する。
                    cap.release()


                # 動画ファイルを含むクラスとインデックス
                classIdx, img_class = [ (idx, c) for idx, c in enumerate(imageClasses) if video_path in c.videoPathes ][0]

                VideoIdx  = img_class.videoPathes.index(video_path)

                cap = initCap()

        elif event == '-Vlo-':
            V_lo = int(values[event])

        elif event == '-hue-shift-':
            hue_shift = int(values[event])

        elif event == '-saturation-shift-':
            saturation_shift = int(values[event])

        elif event == '-value-shift-':
            value_shift = int(values[event])

        elif event == '__TIMEOUT__':
            if cap is not None and playing:
                readCap()

        elif event == '-img-pos-':
            showImgPos()

        elif event == '-play/pause-':
            playing = setPlaying(window, not playing)

        elif event == '-save-all-':
            data_size = int(values['-data-size-'])
            class_data_cnt = [0] * len(imageClasses)
            classIdx = 0

            # 背景画像ファイルのインデックス
            bgImgIdx = 0

            if values['-network-'] == 'ODTK':
                network = ODTK(output_dir, imageClasses)
            else:
                network = YOLOv5(output_dir, imageClasses)

            saveImgs()

        else:

            print('You entered ', event)

    window.close()
