import cv2
import socket
import subprocess
import sys
import time
from ultralytics import YOLO

# --- 主模式选择 ---
MODE = 'camera'

# --- 网络配置 ---
ESP32_IP = "172.20.10.2"  # <--- !!! 修改为你的ESP32的实际IP地址 !!!
ESP32_PORT = 12345

# --- YOLO模型与跟踪配置 ---
MODEL_PATH = 'yolov8n.pt'
CONFIDENCE_THRESHOLD = 0.5
OBSTACLE_CLASSES = ['person', 'bicycle', 'car', 'motorcycle', 'bus', 'train', 'truck']

# --- 检测与避障逻辑配置 ---
CENTER_DEAD_ZONE_PERCENT = 0.4  # 中央区域占比扩大到40%
MIN_AREA_THRESHOLD = 8000  # 最小障碍物面积阈值，根据实际情况调整
AVOIDANCE_DIRECTION = 'L'  # 默认的避障转向：'L' 或 'R'

# --- 【新增】状态机配置 ---
STATE_SEARCHING = "SEARCHING"
STATE_AVOIDING = "AVOIDING"
current_state = STATE_SEARCHING
tracked_obstacle_id = None

# --- 防卡顿：每 N 帧做一次检测，其余帧复用结果，保证画面刷新（Mac 上尤其有效）
DETECT_EVERY_N_FRAMES = 2
# Mac 上给窗口更多时间处理事件，避免 IMK/mach port 报错和画面卡住
WAITKEY_MS = 10 if sys.platform == "darwin" else 1


def check_esp32_reachable(ip, timeout_sec=2):
    """
    检查 ESP32 是否在线（ping 其 IP）。
    返回 True 表示可达，False 表示不可达。
    """
    if sys.platform.lower().startswith("win"):
        cmd = ["ping", "-n", "1", "-w", str(timeout_sec * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), ip]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout_sec + 1)
        return out.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def find_closest_obstacle(detections):
    """从所有检测到的障碍物中，找到面积最大的那一个（作为最近的代表）"""
    closest_obstacle = None
    max_area = 0

    for obstacle in detections:
        x1, y1, x2, y2 = obstacle['box']
        area = (x2 - x1) * (y2 - y1)
        if area > max_area:
            max_area = area
            closest_obstacle = obstacle

    return closest_obstacle


def process_live_camera(model):
    """
    处理实时摄像头流，实现基于状态机和对象跟踪的智能避障。
    """
    global current_state, tracked_obstacle_id

    # 初始化网络
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    esp32_address = (ESP32_IP, ESP32_PORT)
    print(f"UDP模式启动，将向 {ESP32_IP}:{ESP32_PORT} 发送数据")

    # 检查 ESP32 是否可达
    print("正在检查 ESP32 连接...", end=" ")
    if check_esp32_reachable(ESP32_IP):
        print("✓ ESP32 已连接，可以正常发送指令。")
    else:
        print("✗ 无法连接到 ESP32，请检查：")
        print("  1. ESP32 已上电并连接到与电脑相同的 Wi-Fi")
        print("  2. demo_v3.py 中的 ESP32_IP 是否与 ESP32 串口监视器显示的 IP 一致")
        print("  3. 防火墙是否允许 ping / UDP")
        print("程序将继续运行，但指令可能无法送达 ESP32。")

    # macOS 可能打印 AVCaptureDeviceTypeExternal 弃用警告，可忽略，不影响使用
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("错误: 无法打开摄像头。请检查摄像头权限与连接，或尝试其他设备索引（如 1）。")
        return

    # 摄像头预热：部分 Mac/外接摄像头前几帧会失败，先读掉几帧再进入主循环
    print("正在启动摄像头...", end=" ", flush=True)
    warmup_ok = False
    for _ in range(30):
        ok, _ = cap.read()
        if ok:
            warmup_ok = True
            break
        time.sleep(0.05)
    if not warmup_ok:
        print("失败。")
        print("错误: 无法读取摄像头画面。请关闭占用摄像头的程序（如 FaceTime、Zoom、Chrome 视频网页等）后重试。")
        cap.release()
        return
    print("就绪。")

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    dead_zone_width = frame_width * CENTER_DEAD_ZONE_PERCENT
    left_bound = (frame_width / 2) - (dead_zone_width / 2)
    right_bound = (frame_width / 2) + (dead_zone_width / 2)

    last_signal_time = 0
    signal_interval = 0.2
    frame_count = 0
    last_detections = []
    last_results = None

    def draw_overlay(img, detections_for_draw):
        """在画面上绘制辅助线、状态和检测框（跳帧时复用）"""
        out = img.copy()
        cv2.line(out, (int(left_bound), 0), (int(left_bound), out.shape[0]), (255, 0, 0), 1)
        cv2.line(out, (int(right_bound), 0), (int(right_bound), out.shape[0]), (255, 0, 0), 1)
        cv2.putText(out, f"State: {current_state}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(out, f"Tracking ID: {tracked_obstacle_id}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        for d in detections_for_draw:
            x1, y1, x2, y2 = d['box']
            cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(out, str(d['id']), (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return out

    try:
        while True:
            success, frame = cap.read()
            if not success:
                print("错误: 无法读取摄像头画面。请关闭占用摄像头的程序（如 FaceTime、Zoom、Chrome 视频网页等）后重试。")
                break

            do_detect = (frame_count % DETECT_EVERY_N_FRAMES == 0)
            frame_count += 1

            if do_detect:
                # 【核心】使用 model.track()
                results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)
                last_results = results

                # 提取所有有效的检测结果
                detections = []
                if results[0].boxes.id is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
                    ids = results[0].boxes.id.cpu().numpy().astype(int)
                    confs = results[0].boxes.conf.cpu().numpy()
                    clss = results[0].boxes.cls.cpu().numpy().astype(int)
                    for i, box in enumerate(boxes):
                        class_name = model.names[clss[i]]
                        area = (box[2] - box[0]) * (box[3] - box[1])
                        if confs[i] > CONFIDENCE_THRESHOLD and class_name in OBSTACLE_CLASSES and area > MIN_AREA_THRESHOLD:
                            detections.append({
                                'id': ids[i],
                                'box': box,
                                'center_x': (box[0] + box[2]) / 2
                            })
                last_detections = detections
            else:
                detections = last_detections

            # 找到最近的障碍物
            closest_obstacle = find_closest_obstacle(detections)
            command = 'C'

            # --- 状态机逻辑 ---
            if current_state == STATE_SEARCHING:
                command = 'C'
                if closest_obstacle and left_bound < closest_obstacle['center_x'] < right_bound:
                    current_state = STATE_AVOIDING
                    tracked_obstacle_id = closest_obstacle['id']
                    command = AVOIDANCE_DIRECTION
                    print(f"--- 状态切换: SEARCHING -> AVOIDING (ID: {tracked_obstacle_id}) ---")

            elif current_state == STATE_AVOIDING:
                command = AVOIDANCE_DIRECTION
                obstacle_passed = True
                for obs in detections:
                    if obs['id'] == tracked_obstacle_id:
                        obstacle_passed = False
                        if obs['center_x'] < left_bound or obs['center_x'] > right_bound:
                            current_state = STATE_SEARCHING
                            tracked_obstacle_id = None
                            command = 'C'
                            print(f"--- 状态切换: AVOIDING -> SEARCHING (成功越过 ID: {obs['id']}) ---")
                        break
                if obstacle_passed:
                    current_state = STATE_SEARCHING
                    tracked_obstacle_id = None
                    command = 'C'
                    print(f"--- 状态切换: AVOIDING -> SEARCHING (目标 ID 消失) ---")

            # 发送信号
            current_time = time.time()
            if current_time - last_signal_time > signal_interval:
                try:
                    sock.sendto(command.encode(), esp32_address)
                except OSError as e:
                    pass  # ESP32 不可达时静默跳过，避免程序崩溃
                last_signal_time = current_time

            # --- 可视化：检测帧用 results.plot()，跳帧用上一帧结果画在当前画面上 ---
            if do_detect and last_results is not None and last_results[0].boxes.id is not None:
                annotated_frame = last_results[0].plot()
            else:
                annotated_frame = frame
            annotated_frame = draw_overlay(annotated_frame, detections)

            cv2.imshow("YOLOv8 Advanced Obstacle Avoidance", annotated_frame)
            if cv2.waitKey(WAITKEY_MS) & 0xFF == ord('q'):
                try:
                    sock.sendto('C'.encode(), esp32_address)
                except OSError:
                    pass
                break
    finally:
        cap.release()   # 用代码关闭摄像头（Mac/各平台通用），释放设备给系统或其他应用
        cv2.destroyAllWindows()
        sock.close()


if __name__ == "__main__":
    yolo_model = YOLO(MODEL_PATH)
    print("YOLOv8 模型加载成功.")
    process_live_camera(yolo_model)