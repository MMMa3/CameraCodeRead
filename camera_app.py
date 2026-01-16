#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Industrial Camera Control Application with QR/Barcode Recognition
==================================================================

This is the main application file that creates the UI interface and manages
the camera control workflow.

Architecture:
- UI Thread (Main): Handles user interface and user interactions
- Worker Thread: Handles camera operations and image processing
- Signal-based communication between threads for thread safety

Workflow:
1. Startup: Find and list available camera devices
2. Connect: Create handle -> Open camera -> Start streaming
3. Runtime: Capture frames -> Process QR/Barcode -> Display results
4. Disconnect: Stop streaming -> Close camera -> Destroy handle
"""

import sys
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTextEdit, QGroupBox, QMessageBox, QSizePolicy,
    QDoubleSpinBox, QLineEdit, QScrollArea
)
from PySide6.QtCore import Qt, Slot, QPoint
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
import logging

# Import SDK and custom modules
from camera_worker import CameraWorker
from camera_config import CameraConfig
from ctypes import *

sys.path.append("C:/Program Files/HuarayTech/MV Viewer/Development/Samples/Python/IMV/MVSDK")
from IMVApi import *

class CameraControlApp(QMainWindow):
    """
    Main application window for industrial camera control.

    This class manages:
    - Device discovery and selection
    - Camera connection/disconnection
    - Video stream display
    - QR/Barcode recognition results display

    TODO: Add camera temperature monitoring and alerts
    """

    def __init__(self):
        super().__init__()
        # Logger
        logging.basicConfig(
            filename='camera_app.log',
            filemode='w',
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Industrial Camera Control - QR/Barcode Recognition")
        self.setGeometry(100, 100, 1200, 800)

        # Camera and worker thread references
        self.camera = MvCamera()
        self.worker = None
        self.device_list = None
        self.selected_device_index = -1

        # Frame processing flag to prevent queue buildup
        self.is_processing_frame = False

        # Detection results for annotation overlay
        self.current_detections = []

        # Initialize UI
        self.init_ui()

        # Auto-discover devices on startup
        self.discover_devices()

    def init_ui(self):
        """
        Initialize the user interface components.

        Layout structure:
        - Top: Device selection and connection controls
        - Middle: Video display area
        - Bottom: Recognition results and status log
        """
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ===== Device Selection and Configuration Group =====
        device_group = QGroupBox("Device Selection and Configuration")
        device_layout = QHBoxLayout()

        # Device dropdown
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(600)
        device_layout.addWidget(QLabel("Available Devices:"))
        device_layout.addWidget(self.device_combo)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh Devices")
        self.refresh_btn.clicked.connect(self.discover_devices)
        device_layout.addWidget(self.refresh_btn)

        # Connect/Disconnect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.connect_btn.setEnabled(False)
        device_layout.addWidget(self.connect_btn)

        device_layout.addStretch()
        device_group.setLayout(device_layout)
        main_layout.addWidget(device_group)

        # Parameter configuration button
        self.param_btn = QPushButton("Camera Parameters")
        self.param_btn.clicked.connect(self.open_camera_parameter_window)
        self.param_btn.setEnabled(False)
        device_layout.addWidget(self.param_btn)

        # ===== Video Display Group =====
        video_group = QGroupBox("Camera Preview")
        video_layout = QVBoxLayout()

        # Video display label
        self.video_label = QLabel("No camera connected")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(800, 600)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_label.setStyleSheet("QLabel { background-color: #2b2b2b; color: white; }")
        video_layout.addWidget(self.video_label)

        # FPS display label
        self.fps_label = QLabel("FPS: --")
        self.fps_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.fps_label.setStyleSheet("QLabel { color: #00ff00; font-weight: bold; padding: 5px; }")
        video_layout.addWidget(self.fps_label)

        video_group.setLayout(video_layout)
        main_layout.addWidget(video_group)

        # ===== Results Display Group =====
        results_group = QGroupBox("Recognition Results and Status Log")
        results_layout = QVBoxLayout()

        # Results text area
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("QR/Barcode recognition results will appear here...")
        self.results_text.setMinimumHeight(100)
        self.results_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        results_layout.addWidget(self.results_text)

        results_group.setLayout(results_layout)
        main_layout.addWidget(results_group)

        main_layout.setStretch(0, 0)  # Device selection
        main_layout.setStretch(1, 3)  # Video display
        main_layout.setStretch(2, 1)  # Results display

        # Status bar
        self.statusBar().showMessage("Ready - Please select a device")

    def discover_devices(self):
        """
        Discover and list all available camera devices.

        This function:
        1. Calls IMV_EnumDevices to find all connected cameras
        2. Populates the device dropdown with device information
        3. Enables the connect button if devices are found
        4. Logs discovery status and errors
        """
        self.log_message("Discovering devices...")
        self.logger.info("Discovering devices...")

        try:
            # Create device list structure
            self.device_list = IMV_DeviceList()
            interface_type = IMV_EInterfaceType.interfaceTypeAll  # Search all interface types, Ignore Error

            # Enumerate devices
            ret = MvCamera.IMV_EnumDevices(self.device_list, interface_type)

            if ret != IMV_OK:
                self.log_message(f"ERROR: Failed to enumerate devices. Error code: {ret}")
                QMessageBox.critical(self, "Error", f"Failed to discover devices.\nError code: {ret}")
                return

            # Clear existing items
            self.device_combo.clear()

            # Check if any devices found
            if self.device_list.nDevNum == 0:
                self.log_message("No devices found. Please check camera connection.")
                self.logger.info("No devices found during discovery")
                self.device_combo.addItem("No devices found")
                self.connect_btn.setEnabled(False)
                return

            # Populate device list
            self.log_message(f"Found {self.device_list.nDevNum} device(s)")
            self.logger.info(f"Found {self.device_list.nDevNum} device(s)")

            for i in range(self.device_list.nDevNum):
                device_info = self.device_list.pDevInfo[i]

                # Extract device information
                device_name = f"Device {i}: "

                # Try to get manufacturer and model info
                try:
                    manufacturer = device_info.vendorName.decode('utf-8') if device_info.vendorName else "Unknown"
                    model = device_info.modelName.decode('utf-8') if device_info.modelName else "Unknown"
                    serial = device_info.serialNumber.decode('utf-8') if device_info.serialNumber else "Unknown"
                    ip_address = device_info.DeviceSpecificInfo.gigeDeviceInfo.ipAddress.decode('utf-8') if device_info.DeviceSpecificInfo.gigeDeviceInfo.ipAddress else "N/A"
                    device_name += f"{manufacturer} {model} (S/N: {serial}) IP: {ip_address}"
                except:
                    device_name += "Camera Device"

                self.device_combo.addItem(device_name)

            # Enable connect button
            self.connect_btn.setEnabled(True)
            self.log_message("Device discovery completed successfully")
            self.logger.info("Device discovery completed successfully")
            self.statusBar().showMessage(f"Found {self.device_list.nDevNum} device(s) - Ready to connect")

        except Exception as e:
            self.log_message(f"ERROR: Exception during device discovery: {str(e)}")
            self.logger.exception("Exception during device discovery")
            QMessageBox.critical(self, "Error", f"Exception occurred:\n{str(e)}")

    def toggle_connection(self):
        """
        Toggle camera connection state.

        When disconnected: Initiates connection sequence
        When connected: Initiates disconnection sequence
        """
        if self.worker is None:
            self.connect_camera()
            self.param_btn.setEnabled(True)
        else:
            self.disconnect_camera()
            self.param_btn.setEnabled(False)

    def connect_camera(self):
        """
        Connect to the selected camera device.

        Connection sequence:
        1. Get selected device from dropdown
        2. Create device handle (IMV_CreateHandle)
        3. Open camera (IMV_Open)
        4. Start worker thread for streaming

        TODO: Add camera parameter configuration (exposure, gain, etc.)
        TODO: Implement connection timeout handling
        """
        # Get selected device index
        self.selected_device_index = self.device_combo.currentIndex()

        if self.selected_device_index < 0 or self.device_list is None:
            QMessageBox.warning(self, "Warning", "Please select a valid device")
            return

        self.log_message(f"Connecting to device {self.selected_device_index}...")
        self.statusBar().showMessage("Connecting to camera...")
        self.logger.info(f"Connecting to device index: {self.selected_device_index}")

        try:
            # Step 1: Create device handle
            self.log_message("Step 1/3: Creating device handle...")
            self.logger.info("Creating device handle")
            device_info = self.device_list.pDevInfo[self.selected_device_index]
            ret = self.camera.IMV_CreateHandle(
                IMV_ECreateHandleMode.modeByIndex,
                byref(c_uint(self.selected_device_index))
            )

            if ret != IMV_OK:
                self.logger.error(f"IMV_CreateHandle failed: {ret}")
                raise Exception(f"Failed to create device handle. Error code: {ret}")

            self.log_message("Device handle created successfully")

            # Step 2: Open camera
            self.log_message("Step 2/3: Opening camera...")
            ret = self.camera.IMV_Open()

            if ret != IMV_OK:
                self.camera.IMV_DestroyHandle()
                raise Exception(f"Failed to open camera. Error code: {ret}")

            self.log_message("Camera opened successfully")
            self.logger.info("Camera opened successfully")

            # Step 3: Start worker thread for streaming
            self.log_message("Step 3/3: Starting video stream...")
            self.logger.info("Starting worker thread for streaming")
            self.worker = CameraWorker(self.camera)

            # Connect worker signals to UI slots
            self.worker.image_signal.connect(self.update_video_display)
            self.worker.result_signal.connect(self.update_recognition_results)
            self.worker.error_signal.connect(self.handle_worker_error)
            self.worker.status_signal.connect(self.log_message)
            self.worker.fps_signal.connect(self.update_fps_display)
            self.worker.detection_signal.connect(self.update_detections)  # New: detection results

            # Start the worker thread
            self.worker.start()

            # Update UI state
            self.connect_btn.setText("Disconnect")
            self.device_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)

            self.log_message("Camera connected and streaming started successfully!")
            self.logger.info("Camera connected and streaming started successfully")
            self.statusBar().showMessage("Camera connected - Streaming active")

        except Exception as e:
            self.log_message(f"ERROR: Connection failed - {str(e)}")
            self.logger.exception("Connection failed")
            QMessageBox.critical(self, "Connection Error", f"Failed to connect to camera:\n{str(e)}")
            self.statusBar().showMessage("Connection failed")

            # Cleanup on failure
            if self.camera.IMV_IsOpen():
                self.camera.IMV_Close()
            self.camera.IMV_DestroyHandle()
            self.logger.info("Cleanup after failed connection executed")

    def disconnect_camera(self):
        """
        Disconnect from the camera device.

        Disconnection sequence:
        1. Stop worker thread (stops frame grabbing)
        2. Close camera (IMV_Close)
        3. Destroy device handle (IMV_DestroyHandle)

        TODO: Implement force disconnect option
        """
        self.log_message("Disconnecting camera...")
        self.statusBar().showMessage("Disconnecting...")
        self.logger.info("Disconnect initiated by user")

        try:
            # Step 1: Stop worker thread
            if self.worker is not None:
                self.log_message("Step 1/3: Stopping video stream...")
                self.logger.info("Stopping worker thread")

                # Disconnect signals first to prevent queued signals from updating UI
                self.worker.image_signal.disconnect()
                self.worker.result_signal.disconnect()
                self.worker.error_signal.disconnect()
                self.worker.status_signal.disconnect()

                self.worker.stop()
                self.worker.wait(5000)  # Wait up to 5 seconds for thread to finish

                if self.worker.isRunning():
                    self.log_message("WARNING: Worker thread kept running after stop request")
                    self.worker.terminate()
                    self.worker.wait()

                self.worker = None
                self.log_message("Video stream stopped")

            # Step 2: Close camera
            self.log_message("Step 2/3: Closing camera...")
            self.logger.info("Closing camera if open")
            if self.camera.IMV_IsOpen():
                ret = self.camera.IMV_Close()
                if ret != IMV_OK:
                    self.log_message(f"WARNING: Camera close returned error code: {ret}")
                    self.logger.warning(f"Camera close returned error code: {ret}")
                else:
                    self.log_message("Camera closed successfully")
                    self.logger.info("Camera closed successfully")

            # Step 3: Destroy device handle
            self.log_message("Step 3/3: Destroying device handle...")
            ret = self.camera.IMV_DestroyHandle()
            if ret != IMV_OK:
                self.log_message(f"WARNING: Handle destruction returned error code: {ret}")
                self.logger.warning(f"Handle destruction returned error code: {ret}")
            else:
                self.log_message("Device handle destroyed successfully")
                self.logger.info("Device handle destroyed successfully")

            # Update UI state
            self.connect_btn.setText("Connect")
            self.device_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.current_detections = []  # Clear detection results
            self.video_label.clear()
            self.video_label.setText("No camera connected")
            self.fps_label.setText("FPS: --")
            self.param_window = None  # Close parameter window if open

            self.log_message("Camera disconnected successfully")
            self.statusBar().showMessage("Disconnected - Ready to connect")

        except Exception as e:
            self.log_message(f"ERROR: Disconnection error - {str(e)}")
            self.logger.exception("Disconnection error")
            QMessageBox.warning(self, "Disconnection Error", f"Error during disconnection:\n{str(e)}")

    @Slot(QImage)
    def update_video_display(self, q_image):
        """
        Update the video display with a new frame.

        Uses frame dropping strategy to prevent queue buildup and reduce latency.
        Overlays detection boxes if available.

        Args:
            q_image: QImage object containing the processed frame
        """
        # Drop frame if still processing previous frame (prevents queue buildup)
        if self.is_processing_frame:
            return

        self.is_processing_frame = True

        try:
            if q_image is not None:
                # Draw detections on image if available
                if self.current_detections:
                    q_image = self.draw_detections_on_qimage(q_image, self.current_detections)

                # Scale image to fit display while maintaining aspect ratio
                pixmap = QPixmap.fromImage(q_image)
                scaled_pixmap = pixmap.scaled(
                    self.video_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
                self.video_label.setPixmap(scaled_pixmap)
        finally:
            self.is_processing_frame = False

    @Slot(str)
    def update_recognition_results(self, result_text):
        """
        Update the recognition results display.

        Args:
            result_text: Decoded QR/Barcode text
        """
        if result_text:
            self.results_text.append(f"[DETECTED] {result_text}")
            self.statusBar().showMessage(f"Code detected: {result_text[:50]}...")

    @Slot(float)
    def update_fps_display(self, fps):
        """
        Update the FPS display label.

        Args:
            fps: Frames per second value
        """
        self.fps_label.setText(f"FPS: {fps:.1f}")

    @Slot(list)
    def update_detections(self, detections):
        """
        Update detection results for overlay.

        Args:
            detections: List of detection dicts with 'type', 'text', 'points'
        """
        self.current_detections = detections

    def draw_detections_on_qimage(self, q_image, detections):
        """
        Draw detection boxes on QImage using QPainter.

        Args:
            q_image: QImage to draw on
            detections: List of detection dicts

        Returns:
            QImage with detections drawn
        """
        if not detections:
            return q_image

        # Create a copy to draw on
        result_image = q_image.copy()

        # Create painter
        painter = QPainter(result_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen()
        pen.setWidth(12)
        
        for detection in detections:
            det_type = detection.get('type', 'Unknown')
            points = detection.get('points', None)

            if points is None or len(points) == 0:
                continue

            # Draw polygon
            qpoints = [QPoint(int(p[0]), int(p[1])) for p in points]

            # Choose color based on type
            if det_type == 'QR':
                pen.setColor(QColor(0, 255, 0))  # Green for QR codes
                painter.setPen(pen)

                # Draw QR code box
                painter.drawPolygon(qpoints)
            else:
                pen.setColor(QColor(255, 0, 0))  # Red for barcodes
                painter.setPen(pen)

                # Draw barcode box
                painter.drawPolygon(qpoints)

        painter.end()
        return result_image

    @Slot(str)
    def handle_worker_error(self, error_message):
        """
        Handle errors from the worker thread.

        Args:
            error_message: Error description
        """
        self.log_message(f"WORKER ERROR: {error_message}")
        QMessageBox.critical(self, "Worker Error", error_message)

        # Attempt to disconnect on critical error
        if self.worker is not None:
            self.disconnect_camera()

    def log_message(self, message):
        """
        Log a message to the results text area.

        Args:
            message: Message to log
        """
        self.results_text.append(f"[LOG] {message}")

    def closeEvent(self, event):
        """
        Handle application close event.

        Ensures proper cleanup of camera resources before exit.
        """
        if self.worker is not None:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Camera is still connected. Disconnect and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.disconnect_camera()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def open_camera_parameter_window(self):
        """
        Open the camera parameter configuration window.
        """
        self.param_window = CameraParameterWindow(self.worker, self.camera, self.logger, self)
        self.param_window.show()

# SubWindow to configure camera parameters
class CameraParameterWindow(QWidget):
    """
    Sub-window for configuring camera parameters.

    This window allows users to adjust settings such as exposure,
    gain, white balance, and other camera-specific parameters.
    
    Exposure Time: Float type
    Exposure Mode: Enum type (Off, Once, Continuous)
    Raw Gain: Float type
    Gamma: Float type
    Frame Rate: Float type
    ipAddress: String type
    Pixel Format: Enum type
    Balance White Auto: Enum type (Off, Once, Continuous)
    Balance Ratio Selector: Enum type (Red, Green, Blue)
    Balance Ratio: Float type
    """

    def __init__(self, worker, camera, logger, parent_window=None):
        super().__init__()
        self.camera = camera
        self.worker = worker
        self.logger = logger
        self.parent_window = parent_window  # Store parent window reference
        self.is_grabbing = True  # Track grabbing state
        self.setWindowTitle("Camera Parameter Configuration")
        self.setGeometry(150, 150, 700, 800)

        # --- Use centralized configuration ---
        self.config = CameraConfig()

        # --- Load parameter values from camera ---
        self.config.load_from_camera(self.camera, self.logger)

        # Initialize UI
        self.init_ui()

        # Load current parameters from camera
        self.load_parameters()

    def init_ui(self):
        """Initialize the user interface with all parameter controls."""
        main_layout = QVBoxLayout()

        # Create scroll area for parameters
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout()

        # --- Stop Grabbing for Configuration ---
        stop_group = QGroupBox("Stream Control")
        stop_layout = QVBoxLayout()

        self.toggle_grab_btn = QPushButton("Pause Stream")
        self.toggle_grab_btn.clicked.connect(self.toggle_grabbing)
        self.toggle_grab_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)

        stop_layout.addWidget(self.toggle_grab_btn)
        stop_group.setLayout(stop_layout)
        layout.addWidget(stop_group)

        # --- Exposure Time ---
        # Get exposure time, min, max from camera
        exposure_group = QGroupBox("Exposure Time (μs)")
        exposure_layout = QVBoxLayout()

        max_exposure = c_double(0)
        min_exposure = c_double(0)
        ret = self.camera.IMV_GetDoubleFeatureMin("ExposureTime", min_exposure)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get ExposureTime min: {ret}")
        ret = self.camera.IMV_GetDoubleFeatureMax("ExposureTime", max_exposure)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get ExposureTime max: {ret}")

        self.exposure_spinbox = QDoubleSpinBox()
        self.exposure_spinbox.setMinimum(min_exposure.value)
        self.exposure_spinbox.setMaximum(max_exposure.value)
        self.exposure_spinbox.setSuffix(" μs")
        # Set value BEFORE connecting signal to avoid triggering during init
        self.exposure_spinbox.blockSignals(True)
        self.exposure_spinbox.setValue(self.config.exposure_time.value)
        self.exposure_spinbox.blockSignals(False)
        self.exposure_spinbox.valueChanged.connect(self.on_exposure_spinbox_changed)

        exposure_layout.addWidget(self.exposure_spinbox)
        exposure_group.setLayout(exposure_layout)
        layout.addWidget(exposure_group)

        if self.config.get_editability(self.camera, "ExposureTime") == False:
            self.exposure_spinbox.setEnabled(False)
            
        # --- Exposure Mode ---
        exposure_mode_group = QGroupBox("Auto Exposure Mode")
        exposure_mode_layout = QHBoxLayout()

        self.exposure_mode_combo = QComboBox()
        self.exposure_mode_combo.addItems(["Off", "Once", "Continuous"])

        # Set initial value BEFORE connecting signal to avoid triggering during init
        exposure_mode_str = self.config.exposure_mode.str.decode('utf-8') if self.config.exposure_mode.str else "Off"
        if exposure_mode_str:
            self.exposure_mode_combo.blockSignals(True)
            index = self.exposure_mode_combo.findText(exposure_mode_str)
            if index >= 0:
                self.exposure_mode_combo.setCurrentIndex(index)
            self.exposure_mode_combo.blockSignals(False)

        self.exposure_mode_combo.currentTextChanged.connect(self.on_exposure_mode_changed)

        exposure_mode_layout.addWidget(self.exposure_mode_combo)
        exposure_mode_group.setLayout(exposure_mode_layout)
        layout.addWidget(exposure_mode_group)

        if self.config.get_editability(self.camera, "ExposureAuto") == False:
            self.exposure_mode_combo.setEnabled(False)

        # --- Raw Gain ---
        gain_group = QGroupBox("Raw Gain (dB)")
        gain_layout = QVBoxLayout()

        max_gain = c_double(0)
        min_gain = c_double(0)
        ret = self.camera.IMV_GetDoubleFeatureMin("GainRaw", min_gain)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get GainRaw min: {ret}")
        ret = self.camera.IMV_GetDoubleFeatureMax("GainRaw", max_gain)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get GainRaw max: {ret}")

        self.gain_spinbox = QDoubleSpinBox()
        self.gain_spinbox.setMinimum(min_gain.value)
        self.gain_spinbox.setMaximum(max_gain.value)
        self.gain_spinbox.setSingleStep(0.1)
        self.gain_spinbox.setSuffix(" dB")
        # Set value BEFORE connecting signal
        self.gain_spinbox.blockSignals(True)
        self.gain_spinbox.setValue(self.config.raw_gain.value)
        self.gain_spinbox.blockSignals(False)
        self.gain_spinbox.valueChanged.connect(self.on_gain_spinbox_changed)

        gain_layout.addWidget(self.gain_spinbox)
        gain_group.setLayout(gain_layout)
        layout.addWidget(gain_group)

        if self.config.get_editability(self.camera, "GainRaw") == False:
            self.gain_spinbox.setEnabled(False)

        # --- Gamma ---
        gamma_group = QGroupBox("Gamma")
        gamma_layout = QVBoxLayout()

        max_gamma = c_double(0)
        min_gamma = c_double(0)
        ret = self.camera.IMV_GetDoubleFeatureMin("Gamma", min_gamma)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get Gamma min: {ret}")
        ret = self.camera.IMV_GetDoubleFeatureMax("Gamma", max_gamma)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get Gamma max: {ret}")

        self.gamma_spinbox = QDoubleSpinBox()
        self.gamma_spinbox.setMinimum(min_gamma.value)
        self.gamma_spinbox.setMaximum(max_gamma.value)
        self.gamma_spinbox.setSingleStep(0.1)
        # Set value BEFORE connecting signal
        self.gamma_spinbox.blockSignals(True)
        self.gamma_spinbox.setValue(self.config.gamma.value)
        self.gamma_spinbox.blockSignals(False)
        self.gamma_spinbox.valueChanged.connect(self.on_gamma_spinbox_changed)

        gamma_layout.addWidget(self.gamma_spinbox)
        gamma_group.setLayout(gamma_layout)
        layout.addWidget(gamma_group)

        if self.config.get_editability(self.camera, "Gamma") == False:
            self.gamma_spinbox.setEnabled(False)

        # --- Frame Rate ---
        framerate_group = QGroupBox("Frame Rate (fps)")
        framerate_layout = QVBoxLayout()

        min_framerate = c_double(0)
        max_framerate = c_double(0)
        ret = self.camera.IMV_GetDoubleFeatureMin("AcquisitionFrameRate", min_framerate)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get AcquisitionFrameRate min: {ret}")
        ret = self.camera.IMV_GetDoubleFeatureMax("AcquisitionFrameRate", max_framerate)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get AcquisitionFrameRate max: {ret}")

        self.framerate_spinbox = QDoubleSpinBox()
        self.framerate_spinbox.setMinimum(min_framerate.value)
        self.framerate_spinbox.setMaximum(max_framerate.value)
        self.framerate_spinbox.setSuffix(" fps")
        # Set value BEFORE connecting signal
        self.framerate_spinbox.blockSignals(True)
        self.framerate_spinbox.setValue(self.config.frame_rate.value)
        self.framerate_spinbox.blockSignals(False)
        self.framerate_spinbox.valueChanged.connect(self.on_framerate_spinbox_changed)

        framerate_layout.addWidget(self.framerate_spinbox)
        framerate_group.setLayout(framerate_layout)
        layout.addWidget(framerate_group)

        if self.config.get_editability(self.camera, "AcquisitionFrameRate") == False:
            self.framerate_spinbox.setEnabled(False)

        # --- IP Address ---
        ip_group = QGroupBox("IP Address")
        ip_layout = QHBoxLayout()

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText(self.config.ip_address.str.decode('utf-8') if self.config.ip_address.str else "Enter IP Address")
        self.ip_input.editingFinished.connect(self.on_ip_changed)

        ip_layout.addWidget(self.ip_input)
        ip_group.setLayout(ip_layout)
        layout.addWidget(ip_group)

        if self.config.get_editability(self.camera, "GevCurrentIPAddress") == False:
            self.ip_input.setEnabled(False)

        # --- Pixel Format ---
        pixel_format_group = QGroupBox("Pixel Format")
        pixel_format_layout = QHBoxLayout()

        self.pixel_format_combo = QLineEdit()
        self.pixel_format_combo.setPlaceholderText(self.config.pixel_format.str.decode('utf-8') if self.config.pixel_format.str else "Enter Pixel Format (e.g., Mono8, RGB8)")  #TODO: Test how pixel format string is like
        self.pixel_format_combo.textChanged.connect(self.on_pixel_format_changed)

        pixel_format_layout.addWidget(self.pixel_format_combo)
        pixel_format_group.setLayout(pixel_format_layout)
        layout.addWidget(pixel_format_group)

        if self.config.get_editability(self.camera, "PixelFormat") == False:
            self.pixel_format_combo.setEnabled(False)

        # --- Balance White Auto ---
        balance_auto_group = QGroupBox("Balance White Auto")
        balance_auto_layout = QHBoxLayout()

        self.balance_auto_combo = QComboBox()
        self.balance_auto_combo.addItems(["Off", "Once", "Continuous"])

        # Set initial value BEFORE connecting signal
        balance_auto_string = self.config.balance_auto.str.decode('utf-8') if self.config.balance_auto.str else "Off"
        if balance_auto_string:
            self.balance_auto_combo.blockSignals(True)
            index = self.balance_auto_combo.findText(balance_auto_string)
            if index >= 0:
                self.balance_auto_combo.setCurrentIndex(index)
            self.balance_auto_combo.blockSignals(False)

        self.balance_auto_combo.currentTextChanged.connect(self.on_balance_auto_changed)
        
        balance_auto_layout.addWidget(self.balance_auto_combo)
        balance_auto_group.setLayout(balance_auto_layout)
        layout.addWidget(balance_auto_group)

        if self.config.get_editability(self.camera, "BalanceWhiteAuto") == False:
            self.balance_auto_combo.setEnabled(False)

        # --- Balance Ratio Selector ---
        balance_selector_group = QGroupBox("Balance Ratio Selector")
        balance_selector_layout = QHBoxLayout()

        self.balance_selector_combo = QComboBox()
        self.balance_selector_combo.addItems(["Red", "Green", "Blue"])

        # Set initial value BEFORE connecting signal
        balance_selector_string = self.config.balance_ratio_selector.str.decode('utf-8') if self.config.balance_ratio_selector.str else "Off"
        if balance_selector_string:
            self.balance_selector_combo.blockSignals(True)
            index = self.balance_selector_combo.findText(balance_selector_string)
            if index >= 0:
                self.balance_selector_combo.setCurrentIndex(index)
            self.balance_selector_combo.blockSignals(False)

        self.balance_selector_combo.currentTextChanged.connect(self.on_balance_selector_changed)

        balance_selector_layout.addWidget(self.balance_selector_combo)
        balance_selector_group.setLayout(balance_selector_layout)
        layout.addWidget(balance_selector_group)

        if self.config.get_editability(self.camera, "BalanceRatioSelector") == False:
            self.balance_selector_combo.setEnabled(False)

        # --- Balance Ratio ---
        balance_ratio_group = QGroupBox("Balance Ratio")
        balance_ratio_layout = QVBoxLayout()

        balance_ratio_max = c_double(0)
        balance_ratio_min = c_double(0)
        ret = self.camera.IMV_GetDoubleFeatureMin("BalanceRatio", balance_ratio_min)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get BalanceRatio min: {ret}")
        ret = self.camera.IMV_GetDoubleFeatureMax("BalanceRatio", balance_ratio_max)
        if ret != IMV_OK:
            self.logger.error(f"Failed to get BalanceRatio max: {ret}")

        self.balance_ratio_spinbox = QDoubleSpinBox()
        self.balance_ratio_spinbox.setMinimum(balance_ratio_min.value)
        self.balance_ratio_spinbox.setMaximum(balance_ratio_max.value)
        self.balance_ratio_spinbox.setSingleStep(0.1)
        # Set value BEFORE connecting signal
        self.balance_ratio_spinbox.blockSignals(True)
        self.balance_ratio_spinbox.setValue(self.config.balance_ratio.value)
        self.balance_ratio_spinbox.blockSignals(False)
        self.balance_ratio_spinbox.valueChanged.connect(self.on_balance_ratio_spinbox_changed)

        balance_ratio_layout.addWidget(self.balance_ratio_spinbox)
        balance_ratio_group.setLayout(balance_ratio_layout)
        layout.addWidget(balance_ratio_group)

        if self.config.get_editability(self.camera, "BalanceRatio") == False:
            self.balance_ratio_spinbox.setEnabled(False)

        # --- Buttons ---
        button_layout = QHBoxLayout()

        self.apply_btn = QPushButton("Apply All")
        self.apply_btn.clicked.connect(self.apply_all_parameters)

        self.reset_btn = QPushButton("Reset to Default")
        self.reset_btn.clicked.connect(self.reset_to_default)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # Set scroll widget
        scroll_widget.setLayout(layout)
        scroll.setWidget(scroll_widget)

        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    # --- Event Handlers for Exposure Time ---
    def on_exposure_spinbox_changed(self, value):
        """Handle exposure spinbox change."""
        self.set_camera_parameter("ExposureTime", value)

    # --- Event Handlers for Auto Exposure Mode ---
    def on_exposure_mode_changed(self, text):
        """Handle exposure mode change."""
        self.set_camera_parameter("ExposureAuto", text)

    # --- Event Handlers for Gain ---
    def on_gain_spinbox_changed(self, value):
        """Handle gain spinbox change."""
        self.set_camera_parameter("GainRaw", value)

    # --- Event Handlers for Gamma ---
    def on_gamma_spinbox_changed(self, value):
        """Handle gamma spinbox change."""
        self.set_camera_parameter("Gamma", value)

    # --- Event Handlers for Frame Rate ---
    def on_framerate_spinbox_changed(self, value):
        """Handle frame rate spinbox change."""
        self.set_camera_parameter("AcquisitionFrameRate", value)
        self.set_camera_parameter("AcquisitionFrameRateEnable", True)

    # --- Event Handlers for IP Address ---
    def on_ip_changed(self):
        """Handle IP address change."""
        ip_address = self.ip_input.text()
        self.set_camera_parameter("IPAddress", ip_address)

    # --- Event Handlers for Pixel Format ---
    def on_pixel_format_changed(self):
        """Handle pixel format change."""
        pixel_format = self.pixel_format_combo.text()
        self.set_camera_parameter("PixelFormat", pixel_format)

    # --- Event Handlers for Balance White Auto ---
    def on_balance_auto_changed(self, text):
        """Handle balance white auto change."""
        self.set_camera_parameter("BalanceWhiteAuto", text)

    # --- Event Handlers for Balance Ratio Selector ---
    def on_balance_selector_changed(self, text):
        """Handle balance ratio selector change."""
        self.set_camera_parameter("BalanceRatioSelector", text)
        # When selector changes, update the balance ratio display for that channel
        self.load_balance_ratio()

    # --- Event Handlers for Balance Ratio ---
    def on_balance_ratio_spinbox_changed(self, value):
        """Handle balance ratio spinbox change."""
        self.set_camera_parameter("BalanceRatio", value)

    # --- Camera Parameter Methods ---
    def set_camera_parameter(self, param_name, value):
        """Set a camera parameter."""
        try:
            if param_name in ["ExposureTime", "GainRaw", "Gamma", "AcquisitionFrameRate", "BalanceRatio"]:
                ret = self.camera.IMV_SetDoubleFeatureValue(param_name, value)
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name}. Error code: {ret}")
            elif param_name in ["ExposureAuto", "BalanceWhiteAuto", "BalanceRatioSelector"]:
                ret = self.camera.IMV_SetEnumFeatureValue(param_name, value.encode('utf-8'))
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name}. Error code: {ret}")
            elif param_name == "AcquisitionFrameRateEnable":
                ret = self.camera.IMV_SetBoolFeatureValue(param_name, value)
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name}. Error code: {ret}")
            else:  # String parameters
                ret = self.camera.IMV_SetStringFeatureValue(param_name, value.encode('utf-8'))
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name}. Error code: {ret}")

        except Exception as e:
            logging.error(f"Failed to set {param_name}: {e}")
            QMessageBox.warning(self, "Parameter Error", f"Failed to set {param_name}: {str(e)}")

    def load_parameters(self):
        """Load current parameters from camera and populate UI controls."""
        try:
            # --- Load Exposure Time ---
            self.exposure_spinbox.setValue(self.config.exposure_time.value)

            # --- Load Exposure Mode (Enum) ---
            exposure_mode_str = self.config.exposure_mode.str.decode('utf-8') if self.config.exposure_mode.str else ""
            if exposure_mode_str:
                index = self.exposure_mode_combo.findText(exposure_mode_str)
                if index >= 0:
                    self.exposure_mode_combo.setCurrentIndex(index)

            # --- Load Raw Gain ---
            self.gain_spinbox.setValue(self.config.raw_gain.value)

            # --- Load Gamma ---
            self.gamma_spinbox.setValue(self.config.gamma.value)

            # --- Load Frame Rate ---
            self.framerate_spinbox.setValue(self.config.frame_rate.value)

            # --- Load IP Address ---
            ip_str = self.config.ip_address.str.decode('utf-8') if self.config.ip_address.str else ""
            self.ip_input.setText(ip_str)

            # --- Load Pixel Format (Enum) ---
            pixel_format_str = self.config.pixel_format.str.decode('utf-8') if self.config.pixel_format.str else ""
            self.pixel_format_combo.setText(pixel_format_str)

            # --- Load Balance White Auto (Enum) ---
            balance_auto_str = self.config.balance_auto.str.decode('utf-8') if self.config.balance_auto.str else ""
            if balance_auto_str:
                index = self.balance_auto_combo.findText(balance_auto_str)
                if index >= 0:
                    self.balance_auto_combo.setCurrentIndex(index)

            # --- Load Balance Ratio Selector (Enum) ---
            selector_str = self.config.balance_ratio_selector.str.decode('utf-8') if self.config.balance_ratio_selector.str else ""
            if selector_str:
                index = self.balance_selector_combo.findText(selector_str)
                if index >= 0:
                    self.balance_selector_combo.setCurrentIndex(index)

            # --- Load Balance Ratio ---
            self.balance_ratio_spinbox.setValue(self.config.balance_ratio.value)

            self.logger.info("Camera parameters loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load parameters: {e}")

    def load_balance_ratio(self):
        """Load balance ratio for the currently selected channel."""
        try:
            self.config.load_from_camera(self.camera, self.logger)
            self.balance_ratio_spinbox.setValue(self.config.balance_ratio.value)
        except Exception as e:
            logging.error(f"Failed to load balance ratio: {e}")

    def apply_all_parameters(self):
        """Apply all parameters to camera at once."""
        try:
            # Re-apply all parameters
            self.on_exposure_spinbox_changed(self.exposure_spinbox.value())
            self.on_exposure_mode_changed(self.exposure_mode_combo.currentText())
            self.on_gain_spinbox_changed(self.gain_spinbox.value())
            self.on_gamma_spinbox_changed(self.gamma_spinbox.value())
            self.on_framerate_spinbox_changed(self.framerate_spinbox.value())
            self.on_ip_changed()
            self.on_pixel_format_changed()
            self.on_balance_auto_changed(self.balance_auto_combo.currentText())
            self.on_balance_selector_changed(self.balance_selector_combo.currentText())
            self.on_balance_ratio_spinbox_changed(self.balance_ratio_spinbox.value())

            QMessageBox.information(self, "Success", "All parameters applied successfully!")
        except Exception as e:
            logging.error(f"Failed to apply parameters: {e}")
            QMessageBox.warning(self, "Error", f"Failed to apply parameters: {str(e)}")

    def reset_to_default(self):
        """Reset all parameters to default values."""
        # TODO: Implement default status
        pass

    def toggle_grabbing(self):
        """Toggle between pausing and resuming stream grabbing."""
        if self.worker is None:
            QMessageBox.warning(self, "Warning", "No active worker thread!")
            return

        if self.is_grabbing:
            # Currently grabbing, so pause it
            self.pause_grabbing()
            # After pausing, check parameter editability and update UI
            self.update_parameter_editability()
        else:
            # Currently paused, so resume it
            self.resume_grabbing()
            # After resuming, check parameter editability and update UI
            self.update_parameter_editability()

    def update_parameter_editability(self):
        """Check editability for each parameter and enable/disable controls accordingly."""
        try:
            # Map parameter names to their corresponding UI controls
            param_control_map = {
                "ExposureTime": self.exposure_spinbox,
                "ExposureAuto": self.exposure_mode_combo,
                "GainRaw": self.gain_spinbox,
                "Gamma": self.gamma_spinbox,
                "AcquisitionFrameRate": self.framerate_spinbox,
                "GevCurrentIPAddress": self.ip_input,
                "PixelFormat": self.pixel_format_combo,
                "BalanceWhiteAuto": self.balance_auto_combo,
                "BalanceRatioSelector": self.balance_selector_combo,
                "BalanceRatio": self.balance_ratio_spinbox
            }

            # Check editability for each parameter and update controls
            for param_name, control in param_control_map.items():
                is_editable = self.config.get_editability(self.camera, param_name)
                control.setEnabled(is_editable)

                # Log the editability status
                status = "editable" if is_editable else "not editable"
                self.logger.info(f"Parameter '{param_name}' is {status}")

        except Exception as e:
            self.logger.error(f"Failed to update parameter editability: {e}")
            QMessageBox.warning(self, "Error", f"Failed to check parameter editability: {str(e)}")


    def pause_grabbing(self):
        """Pause the stream grabbing."""
        try:
            if self.worker is not None:
                # Temporarily disconnect signals to stop processing
                self.worker.image_signal.disconnect()
                self.worker.result_signal.disconnect()
                self.worker.error_signal.disconnect()
                self.worker.status_signal.disconnect()

                # Stop the worker thread
                self.worker.stop()
                self.worker.wait(1000)

                # Update state
                self.is_grabbing = False
                self.toggle_grab_btn.setText("Resume Stream")
                self.toggle_grab_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #27ae60;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                    }
                    QPushButton:hover {
                        background-color: #229954;
                    }
                """)

                logging.info("Stream grabbing paused")
        except Exception as e:
            logging.error(f"Failed to pause grabbing: {e}")
            QMessageBox.warning(self, "Error", f"Failed to pause stream: {str(e)}")

    def resume_grabbing(self):
        """Resume the stream grabbing."""
        try:
            if self.worker is not None and self.parent_window is not None:
                # Reconnect signals to parent window slots
                self.worker.image_signal.connect(self.parent_window.update_video_display)
                self.worker.result_signal.connect(self.parent_window.update_recognition_results)
                self.worker.error_signal.connect(self.parent_window.handle_worker_error)
                self.worker.status_signal.connect(self.parent_window.log_message)

                # Restart the worker thread
                self.worker.start()

                # Update state
                self.is_grabbing = True
                self.toggle_grab_btn.setText("Pause Stream")
                self.toggle_grab_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f39c12;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                    }
                    QPushButton:hover {
                        background-color: #e67e22;
                    }
                """)

                logging.info("Stream grabbing resumed")
            else:
                QMessageBox.warning(self, "Error", "Parent window reference not found!")
        except Exception as e:
            logging.error(f"Failed to resume grabbing: {e}")
            QMessageBox.warning(self, "Error", f"Failed to resume stream: {str(e)}")


def main():
    """
    Application entry point.
    """
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = CameraControlApp()
    window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
