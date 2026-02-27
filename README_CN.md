# Tactile-Navigator
面向视障人士的实时触觉导航设备。

## 🔧 项目架构

项目由 Host PC 与 ESP32 Client 组成，通过局域网 Wi‑Fi 通信。

```
[Camera / Video File]
       |
       | (Video Stream)
       v
+-----------------------------+   (UDP Commands: 'L', 'R', 'C')     +-------------------------+
|        Host PC              | ----------------------------------> |      ESP32-C3 Client    |
| - Python                    |                                     | - Arduino               |
| - OpenCV                    |                                     | - Wi-Fi UDP Receiver    |
| - YOLOv8 (Detect & Track)   |                                     | - Smooth Servo Control  |
| - Avoidance State Machine   |                                     |                         |
+-----------------------------+                                     +------------+------------+
                                                                                 | (PWM Signal)
                                                                                 |
                                                                                 v
                                                                            [ Servo Motor ]
```

## 🛠️ 硬件与软件要求

### 硬件清单

- **PC**：性能较好的电脑（推荐带 NVIDIA GPU 以加速 YOLOv8）。
- **相机**：标准 USB 摄像头。
- **ESP32**：ESP32‑C3 开发板（或任意支持 Wi‑Fi 的 ESP32）。
- **舵机**：如 SG90 / MG90S 等标准舵机。
- **电源**：强烈建议为舵机单独提供 5V 外部电源。
- **线材**：USB 数据线与若干杜邦线。

### 软件清单

- **PC 端**：
  - Python (3.8+)
  - `pip` 包管理器
  - Git
- **ESP32 端**：
  - Arduino IDE (2.0+)
  - Arduino IDE 的 ESP32 开发板支持包
  - `ESP32Servo` 库

## 🚀 部署与使用

### Step 0：克隆仓库

```bash
git clone https://github.com/jelly2187/Tactile-Navigator.git
cd /control
```

### Step 1：硬件连接

**注意**：舵机电流较大，强烈建议外接 5V 电源，并确保外部电源、ESP32、舵机三者 **共地**。

1. **ESP32 `GND`** → **舵机 `GND`**（棕线）
2. **ESP32 `+5V`** → **舵机 `VCC`**（红线）
3. **ESP32 `GPIO06`**（可配置）→ **舵机 `Signal`**（橙线）

### Step 2：ESP32 固件烧录

1. **环境准备**：
   - 打开 Arduino IDE。
   - 通过 Boards Manager 安装 `esp32` 开发板支持。
   - 通过 Library Manager 安装 `ESP32Servo` 库。
2. **修改代码**：
   - 打开固件文件 `tactile.ino`。
   - 修改 Wi‑Fi 信息：
     ```cpp
     const char* ssid = "YOUR_WIFI_SSID";         // 替换为你的 Wi‑Fi 名称
     const char* password = "YOUR_WIFI_PASSWORD"; // 替换为你的 Wi‑Fi 密码
     ```
3. **上传固件**：
   - 用 USB 连接 ESP32。
   - 选择正确的板型（如 `ESP32C3 Dev Module`）和端口（COM）。
   - **注意：flash mode 选择 DIO**
   - 点击 Upload。
4. **获取 IP**：
   - 打开串口监视器（115200）。
   - 记录 ESP32 打印的 IP 地址：
     ```
     Wi-Fi connected!
     IP Address: 192.168.1.105  <-- 记录此地址
     ```

### Step 3：PC 环境配置

1. **创建虚拟环境（推荐）或使用 conda**：
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```
2. **安装依赖**：
   ```bash
   pip install ultralytics opencv-python numpy
   ```

### Step 4：运行项目

1. **配置脚本**：
   - 打开 PC 端主脚本 `demo_v3.py`。
   - 修改顶部配置：
     ```python
     # --- Main Mode Selection ---
     MODE = 'camera'  # 'camera' 或 'video'

     # --- Video File Configuration (仅 'video' 模式) ---
     VIDEO_INPUT_PATH = "path/to/your/test_video.mp4"
     VIDEO_OUTPUT_PATH = "output/result_video.mp4"

     # --- Network Configuration (仅 'camera' 模式) ---
     ESP32_IP = "192.168.1.105" # <-- 替换为 Step 2 中记录的 IP
     ```
2. **运行**：
   ```bash
   python demo_v3.py
   ```
   - `MODE='camera'`：启用摄像头、连接 ESP32、实时避障。
   - `MODE='video'`：处理视频文件，并输出可视化结果到 `VIDEO_OUTPUT_PATH`。

## ⚙️ 配置与调参

可在 `obstacle_detector_final.py` 的配置区调整参数：

| 参数 | 说明 |
| --- | --- |
| `MODE` | `'camera'` 或 `'video'`，程序运行模式。 |
| `ESP32_IP` | ESP32 的 IP 地址。 |
| `OBSTACLE_CLASSES` | YOLOv8 中视为障碍物的类别列表。 |
| `CENTER_DEAD_ZONE_PERCENT` | 中央“前进”区域宽度百分比，障碍物进入此区域会触发避障。 |
| `MIN_AREA_THRESHOLD` | 目标框最小面积阈值，用于过滤远处小目标。 |
| `AVOIDANCE_DIRECTION` | `'L'` 或 `'R'`，避障默认转向。 |

## 未来改进

- **动态路径规划**：根据障碍物位置与尺寸动态选择转向角度。
- **多传感器融合**：融合超声/激光雷达等信息，弥补视觉在距离估计及弱光下的不足。
- **边缘端部署**：优化模型并部署到 Jetson 等边缘设备，实现脱离 PC 的独立运行。
- **复杂机体支持**：适配麦克纳姆轮、双足等更复杂平台。

---
