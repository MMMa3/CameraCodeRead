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
import json
import os
import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTextEdit, QGroupBox, QMessageBox, QSizePolicy,
    QDoubleSpinBox, QLineEdit, QScrollArea
)
from PySide6.QtCore import Qt, Slot, QPoint, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QIcon
import logging

# Import SDK and custom modules
from camera_worker import CameraWorker
from camera_config import CameraConfig
from ctypes import *

sys.path.append("C:/Program Files/HuarayTech/MV Viewer/Development/Samples/Python/IMV/MVSDK")
from IMVApi import *

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class CameraControlApp(QMainWindow):
    """
    Main application window for industrial camera control.

    This class manages:
    - Device discovery and selection
    - Camera connection/disconnection
    - Video stream display
    - QR/Barcode recognition results display
    """

    def __init__(self):
        super().__init__()
        # Logger
        logging.basicConfig(
            filename='camera_app.log',
            filemode='w',
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.WARNING
        )
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Industrial Camera Control - QR/Barcode Recognition")
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setGeometry(100, 100, 1100, 700)

        # Camera and worker thread references
        self.camera = MvCamera()
        self.worker = None
        self.device_list = None
        self.selected_device_index = -1

        # Frame processing flag to prevent queue buildup
        self.is_processing_frame = False

        # Detection results for annotation overlay
        self.current_detections = []

        # fps 
        self.current_fps = 0.0

        # Temperature monitoring
        self.temperature_warning_threshold = 65.0  # Warning at 60°C
        self.temperature_critical_threshold = 70.0  # Critical at 70°C
        self.temperature_warned = False  # Flag to prevent repeated warnings

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

        # Single capture button
        self.single_btn = QPushButton("Single Capture")
        self.single_btn.clicked.connect(self.single_capture)
        self.single_btn.setEnabled(True)
        device_layout.addWidget(self.single_btn)

        # Parameter configuration button
        self.param_btn = QPushButton("Camera Parameters")
        self.param_btn.clicked.connect(self.open_camera_parameter_window)
        self.param_btn.setEnabled(False)
        device_layout.addWidget(self.param_btn)

        device_layout.addStretch()
        device_group.setLayout(device_layout)
        main_layout.addWidget(device_group)
        # ===== Video Display Group =====
        video_group = QGroupBox("Camera Preview")
        video_layout = QVBoxLayout()

        # Video display label
        self.video_label = QLabel("No camera connected")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(700, 600)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_label.setStyleSheet("QLabel { background-color: #2b2b2b; color: white; }")
        video_layout.addWidget(self.video_label)

        # # FPS display label (Deprecated)
        # self.fps_label = QLabel("FPS: --")
        # self.fps_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # self.fps_label.setStyleSheet("QLabel { color: #00ff00; font-weight: bold; padding: 5px; }")
        # video_layout.addWidget(self.fps_label)

        # Temperature display label
        self.temperature_label = QLabel("Mainboard Temp.: --")
        self.temperature_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.temperature_label.setStyleSheet("QLabel { color: green; font-weight :bold; padding: 5px}")
        video_layout.addWidget(self.temperature_label)
        
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

            # Ensure acquisition mode is Off for continuous streaming
            self.log_message("Configuring camera for continuous streaming...")
            ret = self.camera.IMV_SetEnumFeatureSymbol("AcquisitionMode", "Continuous")
            if ret != IMV_OK:
                self.log_message(f"WARNING: Failed to set AcquisitionMode to Continuous. Error code: {ret}")
                self.logger.warning(f"Failed to set AcquisitionMode to Off: {ret}")
            else:
                self.log_message("AcquisitionMode set to Continuous")

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
            self.worker.temperature_signal.connect(self.update_temperature_display)  # New: temperature monitoring

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
            self.temperature_label.setText("Mainboard Temp.: --")
            self.temperature_label.setStyleSheet("QLabel { color: red; font-weight: bold; padding: 5px; }")
            self.temperature_warned = False  # Reset temperature warning flag
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
        self.current_fps = fps

    @Slot(float)
    def update_temperature_display(self, temperature):
        """
        Update the temperature display label and check for alerts.

        Args:
            temperature: Device temperature in Celsius
        """
        # Update temperature label
        self.temperature_label.setText(f"Mainboard Temp.: {temperature:.1f}°C")

        # Check for temperature alerts
        if temperature >= self.temperature_critical_threshold:
            # Critical temperature - red color and show alert
            self.temperature_label.setStyleSheet("QLabel { color: red; font-weight: bold; padding: 5px; background-color: #ffcccc; }")
            if not self.temperature_warned:
                self.temperature_warned = True
                QMessageBox.critical(
                    self,
                    "Critical Temperature Alert",
                    f"Device temperature has reached critical level: {temperature:.1f}°C\n\n"
                    f"Critical threshold: {self.temperature_critical_threshold}°C\n"
                    f"Please check device cooling and consider disconnecting the camera."
                )
                self.log_message(f"CRITICAL: Device temperature {temperature:.1f}°C exceeds critical threshold {self.temperature_critical_threshold}°C")
        elif temperature >= self.temperature_warning_threshold:
            # Warning temperature - orange color and show warning
            self.temperature_label.setStyleSheet("QLabel { color: orange; font-weight: bold; padding: 5px; background-color: #fff4e6; }")
            if not self.temperature_warned:
                self.temperature_warned = True
                QMessageBox.warning(
                    self,
                    "Temperature Warning",
                    f"Device temperature is elevated: {temperature:.1f}°C\n\n"
                    f"Warning threshold: {self.temperature_warning_threshold}°C\n"
                    f"Please monitor the device temperature."
                )
                self.log_message(f"WARNING: Device temperature {temperature:.1f}°C exceeds warning threshold {self.temperature_warning_threshold}°C")
        else:
            # Normal temperature - green color
            self.temperature_label.setStyleSheet("QLabel { color: green; font-weight: bold; padding: 5px; }")
            # Reset warning flag when temperature returns to normal
            if self.temperature_warned and temperature < self.temperature_warning_threshold - 5.0:
                self.temperature_warned = False
                self.log_message(f"INFO: Device temperature normalized to {temperature:.1f}°C")

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

        # Draw detections and fps
        pen = QPen()
        pen.setWidth(12)

        painter.setPen(QColor(0, 255, 9))
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)

        painter.drawText(20, 50, f"FPS: {self.current_fps:.1f}")
        
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

    def single_capture(self):
        """
        Execute single capture and save to file command.

        Two modes:
        1. If worker is running (streaming): Save the latest frame from the video stream
        2. If worker is not running: Use soft trigger to capture a single frame
        """
        try:
            if self.worker is not None:
                # Mode 1: Worker is running, save latest frame from stream
                self.log_message("Capturing frame from video stream...")

                # Get the latest QImage from the video display
                pixmap = self.video_label.pixmap()
                if pixmap is None or pixmap.isNull():
                    QMessageBox.warning(self, "Capture Failed", "No frame available to capture.")
                    self.log_message("ERROR: No frame available in video stream")
                    return

                # Generate filename with timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_{timestamp}.jpg"

                # Save the pixmap as JPEG
                if pixmap.save(filename, "JPEG", 90):
                    self.log_message(f"SUCCESS: Image saved to {filename}")
                    QMessageBox.information(self, "Capture Success", f"Image saved to:\n{filename}")
                    self.logger.info(f"Single capture saved: {filename}")
                else:
                    self.log_message("ERROR: Failed to save image")
                    QMessageBox.warning(self, "Save Failed", "Failed to save the captured image.")

            else:
                # Mode 2: Worker not running, use soft trigger
                self.log_message("Camera not streaming. Using soft trigger mode...")

                self.selected_device_index = self.device_combo.currentIndex()

                # Check if a device is selected
                if self.selected_device_index < 0:
                    QMessageBox.warning(self, "No Device Selected",
                                      "Please select a camera device first.")
                    self.log_message("ERROR: No device selected for soft trigger")
                    return

                # Track if we need to cleanup (for devices not previously connected)
                need_cleanup = False
                was_open = self.camera.IMV_IsOpen()

                try:
                    # If camera is not open, we need to create handle and open it
                    if not was_open:
                        self.log_message("Creating device handle and opening camera...")

                        # Create device handle
                        ret = self.camera.IMV_CreateHandle(
                            IMV_ECreateHandleMode.modeByIndex,
                            byref(c_uint(self.selected_device_index))
                        )
                        if ret != IMV_OK:
                            raise Exception(f"Failed to create device handle. Error code: {ret}")

                        need_cleanup = True

                        # Open camera
                        ret = self.camera.IMV_Open()
                        if ret != IMV_OK:
                            raise Exception(f"Failed to open camera. Error code: {ret}")

                        self.log_message("Camera opened for single capture")

                    # Set soft trigger configuration
                    ret = self.camera.IMV_SetEnumFeatureSymbol("TriggerSource", "Software")
                    if ret != IMV_OK:
                        raise Exception(f"Failed to set TriggerSource. Error code: {ret}")

                    ret = self.camera.IMV_SetEnumFeatureSymbol("TriggerSelector", "FrameStart")
                    if ret != IMV_OK:
                        raise Exception(f"Failed to set TriggerSelector. Error code: {ret}")

                    ret = self.camera.IMV_SetEnumFeatureSymbol("TriggerMode", "On")
                    if ret != IMV_OK:
                        raise Exception(f"Failed to set TriggerMode. Error code: {ret}")

                    self.log_message("Soft trigger configured, starting grab...")

                    # Start grabbing
                    ret = self.camera.IMV_StartGrabbing()
                    if ret != IMV_OK:
                        raise Exception(f"Failed to start grabbing. Error code: {ret}")

                    # Execute soft trigger
                    ret = self.camera.IMV_ExecuteCommandFeature("TriggerSoftware")
                    if ret != IMV_OK:
                        raise Exception(f"Failed to execute soft trigger. Error code: {ret}")

                    # Get frame
                    frame = IMV_Frame()
                    ret = self.camera.IMV_GetFrame(frame, 1000)
                    if ret != IMV_OK:
                        raise Exception(f"Failed to get frame. Error code: {ret}")

                    self.log_message("Frame captured, saving to file...")

                    # Generate filename with timestamp
                    save_dir = "captured_images"

                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir)
                    
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"capture_{timestamp}.jpg"

                    filepath = os.path.join(save_dir, filename)

                    # Prepare save parameters
                    saveParam = IMV_SaveImageToFileParam()
                    saveParam.eImageType = IMV_ESaveType.typeImageJpeg
                    saveParam.nWidth = frame.frameInfo.width
                    saveParam.nHeight = frame.frameInfo.height
                    saveParam.nPixelFormat = frame.frameInfo.pixelFormat
                    saveParam.pSrcData = frame.pData
                    saveParam.nSrcDataLen = frame.frameInfo.size
                    saveParam.nBayerDemosaic = 2
                    saveParam.nQuality = 90
                    saveParam.pImagePath = filepath.encode("utf-8")

                    # Save image to file
                    ret = self.camera.IMV_SaveImageToFile(saveParam)

                    # Release frame
                    self.camera.IMV_ReleaseFrame(frame)

                    # Stop grabbing
                    self.camera.IMV_StopGrabbing()

                    # Restore trigger mode to Off (for normal streaming)
                    self.camera.IMV_SetEnumFeatureSymbol("TriggerMode", "Off")

                    # Cleanup if we opened the camera just for this capture
                    if need_cleanup:
                        self.camera.IMV_Close()
                        self.camera.IMV_DestroyHandle()
                        self.log_message("Camera closed after single capture")

                    # Check save result
                    if ret != IMV_OK:
                        raise Exception(f"Failed to save image. Error code: {ret}")
                    
                    # Load picture to video display widget
                    try:
                        captured_picture =  QPixmap(filepath)
                        if not captured_picture.isNull():
                            scaled_picture = captured_picture.scaled(
                                self.video_label.size(),
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.FastTransformation
                            )
                            self.video_label.setPixmap(scaled_picture)
                    except Exception as display_error:
                        self.logger.error(f"Failed to display captured image in video label: {display_error}")

                    self.log_message(f"SUCCESS: Image saved to {filename}")
                    QMessageBox.information(self, "Capture Success", f"Image saved to:\n{filename}")
                    self.logger.info(f"Single capture (soft trigger) saved: {filename}")

                except Exception as capture_error:
                    self.log_message(f"ERROR: Soft trigger capture failed - {str(capture_error)}")
                    # Cleanup on error if needed
                    if need_cleanup:
                        try:
                            self.camera.IMV_StopGrabbing()
                        except:
                            pass
                        try:
                            self.camera.IMV_Close()
                        except:
                            pass
                        try:
                            self.camera.IMV_DestroyHandle()
                        except:
                            pass
                    raise capture_error

        except Exception as e:
            self.log_message(f"ERROR: Single capture failed - {str(e)}")
            self.logger.exception("Single capture error")
            QMessageBox.critical(self, "Capture Error", f"An error occurred:\n{str(e)}")

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
        self.config.load_from_camera(self.camera)

        # Initialize UI
        self.init_ui()

        # Load current parameters from camera (Deprecated Function)
        # self.load_parameters()

        # Update parameter editability based on current camera state
        self.update_parameter_editability()

        # --- Timer for continuous mode refresh ---
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.fresh_if_continuous)
        self.refresh_timer.start(10000)  # Refresh every 10 seconds

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
        # Removed immediate application - will apply on "Apply All" button click

        exposure_layout.addWidget(self.exposure_spinbox)
        exposure_group.setLayout(exposure_layout)
        layout.addWidget(exposure_group)

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
        # Removed immediate application - will apply on "Apply All" button click

        gain_layout.addWidget(self.gain_spinbox)
        gain_group.setLayout(gain_layout)
        layout.addWidget(gain_group)

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
        # Removed immediate application - will apply on "Apply All" button click

        gamma_layout.addWidget(self.gamma_spinbox)
        gamma_group.setLayout(gamma_layout)
        layout.addWidget(gamma_group)

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
        # Removed immediate application - will apply on "Apply All" button click

        framerate_layout.addWidget(self.framerate_spinbox)
        framerate_group.setLayout(framerate_layout)
        layout.addWidget(framerate_group)

        # --- IP Address ---
        ip_group = QGroupBox("IP Address")
        ip_layout = QHBoxLayout()

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText(self.config.ip_address.str.decode('utf-8') if self.config.ip_address.str else "Enter IP Address")
        # Removed immediate application - will apply on "Apply All" button click

        ip_layout.addWidget(self.ip_input)
        ip_group.setLayout(ip_layout)
        layout.addWidget(ip_group)

        # --- Pixel Format ---
        pixel_format_group = QGroupBox("Pixel Format")
        pixel_format_layout = QHBoxLayout()

        self.pixel_format_combo = QComboBox()
        self.pixel_format_combo.addItems(["BayerRG8", "BayerRG10", "BayerRG12", "BayerRG10Packed", "BayerRG12Packed", "YUV422Packed"])

        # See initial value BEFORE connecting signal
        pixel_format_string = self.config.pixel_format.str.decode("utf-8") if self.config.pixel_format.str else ""
        if pixel_format_string:
            self.pixel_format_combo.blockSignals(True)
            index = self.pixel_format_combo.findText(pixel_format_string)
            if index >= 0:
                self.pixel_format_combo.setCurrentIndex(index)
            self.pixel_format_combo.blockSignals(False)

        self.pixel_format_combo.currentTextChanged.connect(self.on_pixel_format_changed)

        pixel_format_layout.addWidget(self.pixel_format_combo)
        pixel_format_group.setLayout(pixel_format_layout)
        layout.addWidget(pixel_format_group)

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
        # Removed immediate application - will apply on "Apply All" button click

        balance_ratio_layout.addWidget(self.balance_ratio_spinbox)
        balance_ratio_group.setLayout(balance_ratio_layout)
        layout.addWidget(balance_ratio_group)

        # --- Buttons ---
        button_layout = QHBoxLayout()

        self.apply_btn = QPushButton("Apply All")
        self.apply_btn.clicked.connect(self.apply_all_parameters)

        self.reset_btn = QPushButton("Reset to Default")
        self.reset_btn.clicked.connect(self.reset_to_default)

        self.close_btn = QPushButton("Set as Default")
        self.close_btn.clicked.connect(self.set_as_default)

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
        if self.config.get_editability(self.camera, "ExposureTime"):
            self.set_camera_parameter("ExposureTime", value)

    # --- Event Handlers for Auto Exposure Mode ---
    def on_exposure_mode_changed(self, text):
        """Handle exposure mode change."""
        if self.config.get_editability(self.camera, "ExposureAuto"):
            self.set_camera_parameter("ExposureAuto", text)
            self.update_parameter_editability()

    # --- Event Handlers for Gain ---
    def on_gain_spinbox_changed(self, value):
        """Handle gain spinbox change."""
        if self.config.get_editability(self.camera, "GainRaw"):
            self.set_camera_parameter("GainRaw", value)

    # --- Event Handlers for Gamma ---
    def on_gamma_spinbox_changed(self, value):
        """Handle gamma spinbox change."""
        if self.config.get_editability(self.camera, "Gamma"):
            self.set_camera_parameter("Gamma", value)

    # --- Event Handlers for Frame Rate ---
    def on_framerate_spinbox_changed(self, value):
        """Handle frame rate spinbox change."""
        if self.config.get_editability(self.camera, "AcquisitionFrameRate"):
            self.set_camera_parameter("AcquisitionFrameRate", value)
            self.set_camera_parameter("AcquisitionFrameRateEnable", True)

    # --- Event Handlers for IP Address ---
    def on_ip_changed(self):
        """Handle IP address change."""
        if self.config.get_editability(self.camera, "GevCurrentIPAddress"):
            ip_address = self.ip_input.text()
            self.set_camera_parameter("IPAddress", ip_address)

    # --- Event Handlers for Pixel Format ---
    def on_pixel_format_changed(self, text):
        """Handle pixel format change."""
        if self.config.get_editability(self.camera, "PixelFormat"):
            self.set_camera_parameter("PixelFormat", text)

    # --- Event Handlers for Balance White Auto ---
    def on_balance_auto_changed(self, text):
        """Handle balance white auto change."""
        if self.config.get_editability(self.camera, "BalanceWhiteAuto"):
            self.set_camera_parameter("BalanceWhiteAuto", text)
            self.update_parameter_editability()

    # --- Event Handlers for Balance Ratio Selector ---
    def on_balance_selector_changed(self, text):
        """Handle balance ratio selector change."""
        if self.config.get_editability(self.camera, "BalanceRatioSelector"):
            self.set_camera_parameter("BalanceRatioSelector", text)
            # When selector changes, update the balance ratio display for that channel
            self.update_parameter_editability()
            self.load_balance_ratio()

    # --- Event Handlers for Balance Ratio ---
    def on_balance_ratio_spinbox_changed(self, value):
        """Handle balance ratio spinbox change."""
        if self.config.get_editability(self.camera, "BalanceRatio"):
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
                    raise Exception(f"Failed to set {param_name} to {value}. Error code: {ret}")
            elif param_name in ["ExposureAuto", "BalanceWhiteAuto", "BalanceRatioSelector", "PixelFormat"]:
                ret = self.camera.IMV_SetEnumFeatureSymbol(param_name, str(value))
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name} to {value}. Error code: {ret}")
            elif param_name == "AcquisitionFrameRateEnable":
                ret = self.camera.IMV_SetBoolFeatureValue(param_name, value)
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name} to {value}. Error code: {ret}")
            else:  # String parameters
                ret = self.camera.IMV_SetStringFeatureValue(param_name, value.encode('utf-8'))
                if ret == IMV_OK:
                    logging.info(f"Setting {param_name} to {value}")
                else:
                    raise Exception(f"Failed to set {param_name}. Error code: {ret}")

        except Exception as e:
            logging.error(f"Failed to set {param_name} to {value}: {e}")
            QMessageBox.warning(self, "Parameter Error", f"Failed to set {param_name}: {str(e)}")

# Deprecated Method:
    # def load_parameters(self):
    #     """Load current parameters from camera and populate UI controls."""
    #     try:
    #         # --- Load Exposure Time ---
    #         self.exposure_spinbox.setValue(self.config.exposure_time.value)

    #         # --- Load Exposure Mode (Enum) ---
    #         exposure_mode_str = self.config.exposure_mode.str.decode('utf-8') if self.config.exposure_mode.str else ""
    #         if exposure_mode_str:
    #             index = self.exposure_mode_combo.findText(exposure_mode_str)
    #             if index >= 0:
    #                 self.exposure_mode_combo.setCurrentIndex(index)

    #         # --- Load Raw Gain ---
    #         self.gain_spinbox.setValue(self.config.raw_gain.value)

    #         # --- Load Gamma ---
    #         self.gamma_spinbox.setValue(self.config.gamma.value)

    #         # --- Load Frame Rate ---
    #         self.framerate_spinbox.setValue(self.config.frame_rate.value)

    #         # --- Load IP Address ---
    #         ip_str = self.config.ip_address.str.decode('utf-8') if self.config.ip_address.str else ""
    #         self.ip_input.setText(ip_str)

    #         # --- Load Pixel Format (Enum) ---
    #         pixel_format_str = self.config.pixel_format.str.decode('utf-8') if self.config.pixel_format.str else ""
    #         if pixel_format_str:
    #             index = self.pixel_format_combo.findText(pixel_format_str)
    #             if index >= 0:
    #                 self.pixel_format_combo.setCurrentIndex(index)

    #         # --- Load Balance White Auto (Enum) ---
    #         balance_auto_str = self.config.balance_auto.str.decode('utf-8') if self.config.balance_auto.str else ""
    #         if balance_auto_str:
    #             index = self.balance_auto_combo.findText(balance_auto_str)
    #             if index >= 0:
    #                 self.balance_auto_combo.setCurrentIndex(index)

    #         # --- Load Balance Ratio Selector (Enum) ---
    #         selector_str = self.config.balance_ratio_selector.str.decode('utf-8') if self.config.balance_ratio_selector.str else ""
    #         if selector_str:
    #             index = self.balance_selector_combo.findText(selector_str)
    #             if index >= 0:
    #                 self.balance_selector_combo.setCurrentIndex(index)

    #         # --- Load Balance Ratio ---
    #         self.balance_ratio_spinbox.setValue(self.config.balance_ratio.value)

    #         self.logger.info("Camera parameters loaded successfully")

    #     except Exception as e:
    #         self.logger.error(f"Failed to load parameters: {e}")

    def load_balance_ratio(self):
        """Load balance ratio for the currently selected channel."""
        try:
            self.config.load_from_camera(self.camera)
            self.balance_ratio_spinbox.setValue(self.config.balance_ratio.value)
        except Exception as e:
            logging.error(f"Failed to load balance ratio: {e}")

    def apply_all_parameters(self):
        """Apply all text input parameters to camera. Dropdown menus are applied immediately."""
        try:
            # Apply text input parameters (SpinBox and LineEdit)
            # Note: Dropdown menus (ComboBox) are already applied immediately on change
            self.on_exposure_spinbox_changed(self.exposure_spinbox.value())
            self.on_gain_spinbox_changed(self.gain_spinbox.value())
            self.on_gamma_spinbox_changed(self.gamma_spinbox.value())
            self.on_framerate_spinbox_changed(self.framerate_spinbox.value())
            self.on_ip_changed()
            self.on_balance_ratio_spinbox_changed(self.balance_ratio_spinbox.value())

            QMessageBox.information(self, "Success", "All parameters applied successfully!")
            self.update_parameter_editability()
        except Exception as e:
            logging.error(f"Failed to apply parameters: {e}")
            QMessageBox.warning(self, "Error", f"Failed to apply parameters: {str(e)}")

    def reset_to_default(self):
        """Reset all parameters to default values from saved configuration file."""
        try:
            # Define default config file path
            config_file = "camera_default_config.json"

            if not os.path.exists(config_file):
                QMessageBox.warning(
                    self,
                    "No Default Configuration",
                    "No default configuration file found. Please set default parameters first using 'Set as Default' button."
                )
                return

            # Load default parameters from JSON file
            with open(config_file, 'r') as f:
                default_params = json.load(f)

            # Stop grabbing before applying parameters
            was_grabbing = self.is_grabbing
            if was_grabbing:
                self.pause_grabbing()

            # Apply each parameter to camera
            try:
                # Apply exposure time
                if 'exposure_time' in default_params:
                    self.on_exposure_spinbox_changed(default_params['exposure_time'])
                    self.exposure_spinbox.setValue(default_params['exposure_time'])

                # Apply exposure mode
                if 'exposure_mode' in default_params:
                    self.on_exposure_mode_changed(default_params['exposure_mode'])
                    index = self.exposure_mode_combo.findText(default_params['exposure_mode'])
                    if index >= 0:
                        self.exposure_mode_combo.setCurrentIndex(index)

                # Apply gain
                if 'raw_gain' in default_params:
                    self.on_gain_spinbox_changed(default_params['raw_gain'])
                    self.gain_spinbox.setValue(default_params['raw_gain'])

                # Apply gamma
                if 'gamma' in default_params:
                    self.on_gamma_spinbox_changed(default_params['gamma'])
                    self.gamma_spinbox.setValue(default_params['gamma'])

                # Apply frame rate
                if 'frame_rate' in default_params:
                    self.on_framerate_spinbox_changed(default_params['frame_rate'])
                    self.framerate_spinbox.setValue(default_params['frame_rate'])

                # Apply pixel format
                if 'pixel_format' in default_params:
                    self.on_pixel_format_changed(default_params['pixel_format'])
                    index = self.pixel_format_combo.findText(default_params['pixel_format'])
                    if index >= 0:
                        self.pixel_format_combo.setCurrentIndex(index)

                # Apply balance white auto
                if 'balance_auto' in default_params:
                    self.on_balance_auto_changed(default_params['balance_auto'])
                    index = self.balance_auto_combo.findText(default_params['balance_auto'])
                    if index >= 0:
                        self.balance_auto_combo.setCurrentIndex(index)

                # Apply balance ratios for all three channels
                # Save current selector to restore later
                current_selector = default_params.get('balance_ratio_selector', 'Red')

                # Apply balance ratio for each channel
                for channel, param_key in [('Red', 'balance_ratio_red'),
                                           ('Green', 'balance_ratio_green'),
                                           ('Blue', 'balance_ratio_blue')]:
                    if param_key in default_params:
                        # Set selector to the channel
                        ret = self.camera.IMV_SetEnumFeatureSymbol("BalanceRatioSelector", channel)
                        if ret == IMV_OK:
                            # Apply the balance ratio for this channel
                            ret = self.camera.IMV_SetDoubleFeatureValue("BalanceRatio", default_params[param_key])
                            if ret == IMV_OK:
                                self.logger.info(f"Applied BalanceRatio for {channel}: {default_params[param_key]}")
                            else:
                                self.logger.error(f"Failed to set BalanceRatio for {channel}. Error code: {ret}")
                        else:
                            self.logger.error(f"Failed to set BalanceRatioSelector to {channel}. Error code: {ret}")

                # Restore the balance ratio selector to the saved value
                if 'balance_ratio_selector' in default_params:
                    self.camera.IMV_SetEnumFeatureSymbol("BalanceRatioSelector", default_params['balance_ratio_selector'])
                    index = self.balance_selector_combo.findText(default_params['balance_ratio_selector'])
                    if index >= 0:
                        self.balance_selector_combo.setCurrentIndex(index)
                    # Update the displayed balance ratio for the current selector
                    self.load_balance_ratio()

                self.logger.info("Successfully reset parameters to default values")
                QMessageBox.information(self, "Success", "Parameters have been reset to default values!")

            finally:
                # Resume grabbing if it was active before
                if was_grabbing:
                    self.resume_grabbing()

                # Update parameter editability
                self.update_parameter_editability()

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse default configuration file: {e}")
            QMessageBox.critical(self, "Error", f"Invalid configuration file format: {str(e)}")
        except Exception as e:
            self.logger.error(f"Failed to reset to default: {e}")
            QMessageBox.critical(self, "Error", f"Failed to reset parameters: {str(e)}")

    def set_as_default(self):
        """Set current parameters to a configuration file as default."""
        try:
            # Reload current parameters from camera to ensure we have the latest values
            self.config.load_from_camera(self.camera)

            # Get all current parameters as a dictionary
            default_params = self.config.get_dict()

            # Save current balance ratio selector to restore later
            current_selector = self.balance_selector_combo.currentText()

            # Read balance ratios for all three channels
            balance_ratios = {}
            for channel in ["Red", "Green", "Blue"]:
                # Set the selector to the channel
                ret = self.camera.IMV_SetEnumFeatureSymbol("BalanceRatioSelector", channel)
                if ret == IMV_OK:
                    # Read the balance ratio for this channel
                    channel_ratio = c_double(0)
                    ret = self.camera.IMV_GetDoubleFeatureValue("BalanceRatio", channel_ratio)
                    if ret == IMV_OK:
                        balance_ratios[channel] = channel_ratio.value
                        self.logger.info(f"Read BalanceRatio for {channel}: {channel_ratio.value}")
                    else:
                        self.logger.error(f"Failed to read BalanceRatio for {channel}. Error code: {ret}")
                else:
                    self.logger.error(f"Failed to set BalanceRatioSelector to {channel}. Error code: {ret}")

            # Restore original selector
            self.camera.IMV_SetEnumFeatureSymbol("BalanceRatioSelector", current_selector)

            # Replace single balance_ratio with channel-specific ratios
            if balance_ratios:
                default_params['balance_ratio_red'] = balance_ratios.get('Red', 1.0)
                default_params['balance_ratio_green'] = balance_ratios.get('Green', 1.0)
                default_params['balance_ratio_blue'] = balance_ratios.get('Blue', 1.0)
                # Remove the old single balance_ratio field
                default_params.pop('balance_ratio', None)

            # Define default config file path
            config_file = "camera_default_config.json"

            # Save parameters to JSON file
            with open(config_file, 'w') as f:
                json.dump(default_params, f, indent=4)

            self.logger.info(f"Successfully saved default configuration to {config_file}")
            QMessageBox.information(
                self,
                "Success",
                f"Current parameters have been saved as default configuration!\n\nFile: {config_file}"
            )

        except Exception as e:
            self.logger.error(f"Failed to save default configuration: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save default configuration: {str(e)}")

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

    def fresh_if_continuous(self):
        """
        If ExposureAuto == Continuous, refresh exposure time every 10 seconds;
        if BalanceWhiteAuto == Continuous, refresh balance ratio every 10 seconds
        """
        try:
            # Check if ExposureAuto is in Continuous mode
            if self.exposure_mode_combo.currentText() == "Continuous":
                # Reload exposure time from camera
                ret = self.camera.IMV_GetDoubleFeatureValue("ExposureTime", self.config.exposure_time)
                if ret == IMV_OK:
                    # Update UI with new value
                    self.exposure_spinbox.blockSignals(True)
                    self.exposure_spinbox.setValue(self.config.exposure_time.value)
                    self.exposure_spinbox.blockSignals(False)
                    self.logger.info(f"Refreshed ExposureTime: {self.config.exposure_time.value} μs")
                else:
                    self.logger.error(f"Failed to refresh ExposureTime. Error code: {ret}")

            # Check if BalanceWhiteAuto is in Continuous mode
            if self.balance_auto_combo.currentText() == "Continuous":
                # Reload balance ratio from camera for currently selected channel
                ret = self.camera.IMV_GetDoubleFeatureValue("BalanceRatio", self.config.balance_ratio)
                if ret == IMV_OK:
                    # Update UI with new value
                    self.balance_ratio_spinbox.blockSignals(True)
                    self.balance_ratio_spinbox.setValue(self.config.balance_ratio.value)
                    self.balance_ratio_spinbox.blockSignals(False)
                    current_channel = self.balance_selector_combo.currentText()
                    self.logger.info(f"Refreshed BalanceRatio for {current_channel}: {self.config.balance_ratio.value}")
                else:
                    self.logger.error(f"Failed to refresh BalanceRatio. Error code: {ret}")

        except Exception as e:
            self.logger.error(f"Error in fresh_if_continuous: {e}")

    def closeEvent(self, event):
        if not self.is_grabbing:
            self.resume_grabbing()
        else:
            pass

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
