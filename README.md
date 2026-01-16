# Industrial Camera Control Application

A Python application for controlling industrial cameras with real-time QR code and barcode recognition.

## Features

- **Device Discovery**: Automatically find and list connected cameras
- **Live Preview**: Real-time video stream display
- **Code Recognition**: Detect QR codes and barcodes in real-time
- **Thread-Safe Architecture**: UI thread + Worker thread for responsive interface

## Architecture

```
camera_app.py          - Main UI application (PySide6)
camera_worker.py       - Worker thread for camera operations
code_recognition.py    - QR/Barcode detection engine
MVSDK/                 - Huaray camera SDK wrapper installed in default position
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Huaray MVSDK is installed (from manufacturer) in **default** position

3. Make Sure installed opencv-contrib-python >= 4.5.0 and wechat QR CNN Model in local project

## Usage

Run the application:
```bash
python camera_app.py
```

**Workflow:**
1. Click "Refresh Devices" to discover cameras
2. Select a device from dropdown
3. Click "Connect" to start streaming
4. QR/Barcode results appear in the results panel
5. Click "Disconnect" to stop

## TODO List

### High Priority
- [x] Add support for more pixel formats (Bayer, YUV)
- [x] High Delay and chopping animation
- [x] Implement visual bounding boxes for detected codes
- [ ] Add camera parameter controls (exposure, gain)
- [x] Implement frame rate display

### Medium Priority
- [ ] Implement configuration file for settings
- [ ] Add zoom and pan controls for video

### Low Priority
- [x] Add result export functionality
- [ ] Create installer package
