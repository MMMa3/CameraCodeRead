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
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTextEdit, QGroupBox, QMessageBox
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QPixmap
import logging

# Import SDK and custom modules
from camera_worker import CameraWorker
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
    """

    def __init__(self):
        super().__init__()
        # Logger
        logging.basicConfig(filename='camera_app.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Industrial Camera Control - QR/Barcode Recognition")
        self.setGeometry(100, 100, 1200, 800)

        # Camera and worker thread references
        self.camera = MvCamera()
        self.worker = None
        self.device_list = None
        self.selected_device_index = -1

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

        # ===== Device Selection Group =====
        device_group = QGroupBox("Device Selection")
        device_layout = QHBoxLayout()

        # Device dropdown
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(400)
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

        # ===== Video Display Group =====
        video_group = QGroupBox("Camera Preview")
        video_layout = QVBoxLayout()

        # Video display label
        self.video_label = QLabel("No camera connected")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center alignment, original parameter:"Qt.AlignCenter"
        self.video_label.setMinimumSize(800, 600)
        self.video_label.setStyleSheet("QLabel { background-color: #2b2b2b; color: white; }")
        video_layout.addWidget(self.video_label)

        video_group.setLayout(video_layout)
        main_layout.addWidget(video_group)

        # ===== Results Display Group =====
        results_group = QGroupBox("Recognition Results & Status Log")
        results_layout = QVBoxLayout()

        # Results text area
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        self.results_text.setPlaceholderText("QR/Barcode recognition results will appear here...")
        results_layout.addWidget(self.results_text)

        results_group.setLayout(results_layout)
        main_layout.addWidget(results_group)

        # Status bar
        self.statusBar().showMessage("Ready - Please select a device")

    def discover_devices(self):
        """
        Discover and list all available camera devices.

        This function:
        1. Calls IMV_EnumDevices to find all connected cameras
        2. Populates the device dropdown with device information
        3. Enables the connect button if devices are found

        TODO: Add support for different interface types (USB, GigE, etc.)
        TODO: Add error handling for device enumeration failures
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
                # TODO: Decode device name, serial number, and other info properly
                device_name = f"Device {i}: "

                # Try to get manufacturer and model info
                try:
                    manufacturer = device_info.vendorName.decode('utf-8') if device_info.vendorName else "Unknown"
                    model = device_info.modelName.decode('utf-8') if device_info.modelName else "Unknown"
                    serial = device_info.serialNumber.decode('utf-8') if device_info.serialNumber else "Unknown"
                    device_name += f"{manufacturer} {model} (S/N: {serial})"
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
        else:
            self.disconnect_camera()

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
                IMV_ECreateHandleMode.modeByIndex,  # TODO: Use modeByIPAddress instead
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

        TODO: Add graceful shutdown timeout
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
                self.worker.stop()
                self.worker.wait(5000)  # Wait up to 5 seconds for thread to finish

                if self.worker.isRunning():
                    self.log_message("WARNING: Worker thread did not stop gracefully")
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
            self.video_label.setText("No camera connected")
            self.video_label.setPixmap(QPixmap())

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

        Args:
            q_image: QImage object containing the processed frame

        TODO: Add frame rate display
        TODO: Implement zoom and pan controls
        """
        if q_image is not None:
            # Scale image to fit display while maintaining aspect ratio
            pixmap = QPixmap.fromImage(q_image)
            scaled_pixmap = pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio, # Original parameter:Qt.KeepAspectRatio
                Qt.TransformationMode.SmoothTransformation # Original parameter:Qt.SmoothTransformation
            )
            self.video_label.setPixmap(scaled_pixmap)

    @Slot(str)
    def update_recognition_results(self, result_text):
        """
        Update the recognition results display.

        Args:
            result_text: Decoded QR/Barcode text

        TODO: Add result history with timestamps
        TODO: Implement result filtering and search
        """
        if result_text:
            self.results_text.append(f"[DETECTED] {result_text}")
            self.statusBar().showMessage(f"Code detected: {result_text[:50]}...")

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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No # Original parameter:QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.disconnect_camera()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


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
