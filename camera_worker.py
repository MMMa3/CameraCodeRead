#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Camera Worker Thread Module
============================

This module implements the worker thread that handles:
- Camera frame acquisition (IMV_GetFrame)
- Image format conversion (raw buffer to OpenCV format)
- QR/Barcode recognition
- Signal emission to UI thread

Thread Safety:
- Runs in separate thread to avoid blocking UI
- Uses Qt signals for thread-safe communication
- Proper resource cleanup in finally block
"""

import sys
import numpy as np
import cv2
import time
import queue
import threading
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import logging

from code_recognition import CodeRecognizer
from code_storage import CodeStorage
from ctypes import *

sys.path.append("C:/Program Files/HuarayTech/MV Viewer/Development/Samples/Python/IMV/MVSDK")
from IMVApi import *


class CameraWorker(QThread):
    """
    Worker thread for camera operations and image processing.

    Signals:
        image_signal: Emits QImage for video display
        result_signal: Emits decoded QR/Barcode text
        error_signal: Emits error messages
        status_signal: Emits status messages for logging
        fps_signal: Emits FPS (frames per second) value
        detection_signal: Emits detection results with position info
    """

    # Define signals for thread-safe communication
    image_signal = Signal(QImage)
    result_signal = Signal(str)
    error_signal = Signal(str)
    status_signal = Signal(str)
    fps_signal = Signal(float)
    detection_signal = Signal(list)  # Emits list of detections with positions

    def __init__(self, camera):
        """
        Initialize the camera worker.

        Args:
            camera: MvCamera instance (already opened)
        """
        super().__init__()
        # Create a dedicated logger for this module
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # Create file handler if not already exists
        if not self.logger.handlers:
            file_handler = logging.FileHandler('camera_worker.log', mode='w')
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        self.camera = camera
        self.running = False
        self.recognizer = CodeRecognizer()
        self.storage = CodeStorage()

        # Async recognition queue and thread
        self.recognition_queue = queue.Queue(maxsize=2)  # Limit queue size to avoid memory buildup
        self.recognition_thread = None
        self.recognition_running = False

        # Frame skip counter for recognition optimization
        self.frame_count = 0
        self.recognition_interval = 10  # Process every 10th frame for async recognition

        # Display frame skip counter for UI optimization
        self.display_count = 0
        self.display_interval = 1  # Emit every frame for maximum smoothness with callback

        # FPS calculation variables
        self.fps_frame_count = 0
        self.fps_start_time = time.time()
        self.fps_update_interval = 30  # Update FPS every 30 frames

        # Callback function reference
        self.callback_func = None

        # TODO: Add configurable recognition interval

    def run(self):
        """
        Main worker thread loop using callback mode.

        Workflow:
        1. Start async recognition thread
        2. Attach callback to camera
        3. Start grabbing frames (camera will call callback)
        4. Wait until stopped
        5. Cleanup: Stop threads and camera
        """
        self.running = True

        try:
            # Step 1: Start async recognition thread
            self.status_signal.emit("Starting recognition thread...")
            self.recognition_running = True
            self.recognition_thread = threading.Thread(target=self._recognition_worker, daemon=True)
            self.recognition_thread.start()
            self.logger.info("Recognition thread started")

            # Step 2: Create and attach callback function
            self.status_signal.emit("Attaching frame callback...")
            pFrame = POINTER(IMV_Frame)
            FrameCallbackType = CFUNCTYPE(None, pFrame, c_void_p)
            self.callback_func = FrameCallbackType(self._frame_callback)

            ret = self.camera.IMV_AttachGrabbing(self.callback_func, None)
            if ret != IMV_OK:
                self.error_signal.emit(f"Failed to attach callback. Error code: {ret}")
                self.logger.error(f"IMV_AttachGrabbing failed with code: {ret}")
                return

            self.status_signal.emit("Callback attached successfully")
            self.logger.info("Frame callback attached")

            # Step 3: Start grabbing frames
            self.status_signal.emit("Starting frame acquisition...")
            ret = self.camera.IMV_StartGrabbing()

            if ret != IMV_OK:
                self.error_signal.emit(f"Failed to start grabbing. Error code: {ret}")
                self.logger.error(f"IMV_StartGrabbing failed with code: {ret}")
                return

            self.status_signal.emit("Frame acquisition started successfully")
            self.logger.info("Camera grabbing started (callback mode)")

            # Step 4: Wait until stopped (callback handles frames)
            while self.running:
                self.msleep(100)  # Sleep to avoid busy waiting

        except Exception as e:
            self.error_signal.emit(f"Critical error in worker thread: {str(e)}")
            self.logger.exception("Critical error in worker thread")

        finally:
            # Step 5: Cleanup - Always executed
            self._cleanup()

    def _frame_callback(self, pFrame, pUser):
        """
        Frame callback function called by camera SDK.

        This function is called from camera SDK thread.

        Args:
            pFrame: Pointer to IMV_Frame
            pUser: User data (not used)
        """
        try:
            if pFrame is None:
                return

            # Get frame data
            frame = cast(pFrame, POINTER(IMV_Frame)).contents

            # Convert to RGB format
            rgb_image = self._convert_frame_to_rgb(frame)

            if rgb_image is None:
                return

            # Emit for display (fast, no blocking)
            self.frame_count += 1
            self.display_count += 1

            if self.display_count % self.display_interval == 0:
                q_image = self._convert_to_qimage(rgb_image)
                if q_image is not None:
                    self.image_signal.emit(q_image)

            # Queue for async recognition
            if self.frame_count % self.recognition_interval == 0:
                try:
                    # Non-blocking put, discard if queue is full
                    self.recognition_queue.put_nowait(rgb_image.copy())
                except queue.Full:
                    self.logger.debug("Recognition queue full, skipping frame")

            # Calculate and emit FPS
            self.fps_frame_count += 1
            if self.fps_frame_count >= self.fps_update_interval:
                elapsed_time = time.time() - self.fps_start_time
                fps = self.fps_frame_count / elapsed_time
                self.fps_signal.emit(fps)
                # Reset counters
                self.fps_frame_count = 0
                self.fps_start_time = time.time()

        except Exception as e:
            self.logger.error(f"Callback error: {str(e)}")

    def _recognition_worker(self):
        """
        Async recognition worker thread.

        Processes frames from recognition queue without blocking display.
        """
        self.logger.info("Recognition worker started")

        while self.recognition_running:
            try:
                # Wait for frame with timeout
                rgb_image = self.recognition_queue.get(timeout=0.5)

                # Convert RGB to BGR for recognition
                bgr_image = rgb_image[:, :, ::-1]

                # Detect codes with positions
                decoded_text, detections = self.recognizer.detect_codes_with_positions(bgr_image)

                # Emit results and Store
                if decoded_text:
                    codes = decoded_text.split(',')
                    for code in codes:
                        code_type = code.split(':', 1)[0] if ":" in code else "Unknown"
                        text = code.split(':', 1)[1] if ":" in code else code

                    is_new = self.storage.add_code(text, code_type=code_type)

                    if is_new: # Only emit new codes
                        self.result_signal.emit(decoded_text)
                        self.logger.info(f"New code recognized and stored: {decoded_text}")
                    else:
                        self.logger.debug(f"Duplicate code recognized: {decoded_text}")

                self.detection_signal.emit(detections) # Emit detections for display

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Recognition worker error: {str(e)}")

        self.logger.info("Recognition worker stopped")

    def _convert_frame_to_rgb(self, frame_data):
        """
        Convert SDK frame to RGB format in callback.

        Similar to _convert_to_opencv but optimized for callback use.

        Args:
            frame_data: IMV_Frame object

        Returns:
            numpy array (RGB image) or None
        """
        try:
            width = frame_data.frameInfo.width
            height = frame_data.frameInfo.height
            pixel_format = frame_data.frameInfo.pixelFormat

            # Handle different pixel formats
            if pixel_format == IMV_EPixelType.gvspPixelMono8:
                image_array = np.ctypeslib.as_array(
                    (c_ubyte * frame_data.frameInfo.size).from_address(frame_data.pData)
                ).reshape((height, width))
                rgb_image = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)

            elif pixel_format == IMV_EPixelType.gvspPixelBGR8:
                image_array = np.ctypeslib.as_array(
                    (c_ubyte * frame_data.frameInfo.size).from_address(frame_data.pData)
                ).reshape((height, width, 3))
                rgb_image = image_array[:, :, ::-1]  # Fast BGR to RGB

            else:
                # Use SDK conversion
                stPixelConvertParams = IMV_PixelConvertParam()
                dst_pixel = IMV_EPixelType.gvspPixelBGR8
                dst_size = int(width) * int(height) * 3
                dst_buffer = (c_ubyte * dst_size)()
                memset(byref(dst_buffer), 0, sizeof(stPixelConvertParams))

                stPixelConvertParams.nWidth = c_uint(width)
                stPixelConvertParams.nHeight = c_uint(height)
                stPixelConvertParams.ePixelFormat = c_int(pixel_format)
                stPixelConvertParams.pSrcData = frame_data.pData
                stPixelConvertParams.nSrcDataLen = c_uint(frame_data.frameInfo.size)
                stPixelConvertParams.nPaddingX = c_uint(frame_data.frameInfo.paddingX)
                stPixelConvertParams.nPaddingY = c_uint(frame_data.frameInfo.paddingY)
                stPixelConvertParams.eBayerDemosaic = c_int(
                    IMV_EBayerDemosaic.demosaicBilinear if hasattr(IMV_EBayerDemosaic, 'demosaicBilinear') else 1
                )
                stPixelConvertParams.eDstPixelFormat = c_int(dst_pixel)
                stPixelConvertParams.pDstBuf = dst_buffer
                stPixelConvertParams.nDstBufSize = c_uint(dst_size)
                stPixelConvertParams.nDstDataLen = c_uint(0)

                ret = self.camera.IMV_PixelConvert(stPixelConvertParams)
                if ret != IMV_OK:
                    self.logger.error(f"Pixel conversion failed: {ret}")
                    return None

                image_array = np.ctypeslib.as_array(dst_buffer).reshape((height, width, 3))
                rgb_image = image_array[:, :, ::-1]  # BGR to RGB

            # Release frame buffer (important!)
            self.camera.IMV_ReleaseFrame(frame_data)

            return rgb_image

        except Exception as e:
            self.logger.error(f"Frame conversion error: {str(e)}")
            return None
        
# Deprecated method:
#     def _get_frame(self):
#         """
#         Get a frame from the camera with latest frame strategy.

#         Clears the buffer to get the most recent frame, reducing latency.

#         Returns:
#             IMV_Frame object or None on error
#         """
#         # Clear buffer by reading all pending frames with short timeout
#         frame = IMV_Frame()
#         latest_frame = None

#         # Try to drain the buffer (max 10 frames to avoid infinite loop)
#         for _ in range(10):
#             ret = self.camera.IMV_GetFrame(frame, 50)  # Short 50ms timeout
#             if ret == IMV_OK:
#                 latest_frame = frame
#                 frame = IMV_Frame()  # Prepare for next read
#             else:
#                 break  # No more frames in buffer

#         # If we got at least one frame, return the latest
#         if latest_frame is not None:
#             return latest_frame

#         # Otherwise, wait for a new frame with normal timeout
#         ret = self.camera.IMV_GetFrame(frame, 1000)  # 1000ms timeout

#         if ret != IMV_OK:  # IMV_OK defined in IMVADefines
#             self.status_signal.emit(f"Frame acquisition error: {ret}")
#             self.logger.error(f"IMV_GetFrame failed with code: {ret}")
#             return None
#         self.logger.debug("Frame acquired successfully")
#         return frame

# Deprecated method:
#     def _convert_to_opencv(self, frame_data):
#         """
#         Convert SDK frame buffer to RGB format (numpy array).

#         Note: Returns RGB format (not BGR) to avoid redundant color conversion
#         for display. Recognition will convert to BGR only when needed.

#         Args:
#             frame_data: IMV_Frame object

#         Returns:
#             numpy array (RGB image) or None

#         """
#         try:
#             # Get frame properties
#             width = frame_data.frameInfo.width
#             height = frame_data.frameInfo.height
#             pixel_format = frame_data.frameInfo.pixelFormat

#             # Create numpy array from buffer
#             if pixel_format == IMV_EPixelType.gvspPixelMono8:
#                 # Mono 8-bit
#                 image_array = np.ctypeslib.as_array(
#                     (c_ubyte * frame_data.frameInfo.size).from_address(frame_data.pData)).reshape((height, width))

#                 # Convert to RGB for consistency
#                 rgb_image = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)

#             elif pixel_format == IMV_EPixelType.gvspPixelBGR8:
#                 # BGR 8-bit - convert to RGB using fast numpy slicing
#                 image_array = np.ctypeslib.as_array(
#                     (c_ubyte * frame_data.frameInfo.size).from_address(frame_data.pData)).reshape((height, width, 3))
#                 rgb_image = image_array[:, :, ::-1]  # Fast BGR to RGB conversion

#             else:  # Use SDK pixel convert function, convert to BGR8 then to RGB
#                 self.logger.debug(f"Trying pixel convert from format {pixel_format} to BGR8")

#                 stPixelConvertParams = IMV_PixelConvertParam()

#                 dst_pixel = IMV_EPixelType.gvspPixelBGR8
#                 dst_size = int(width) * int(height) * 3
#                 dst_buffer = (c_ubyte * dst_size)()
#                 memset(byref(dst_buffer), 0, sizeof(stPixelConvertParams))

#                 stPixelConvertParams.nWidth = c_uint(width)
#                 stPixelConvertParams.nHeight = c_uint(height)
#                 stPixelConvertParams.ePixelFormat = c_int(pixel_format)
#                 stPixelConvertParams.pSrcData = frame_data.pData
#                 stPixelConvertParams.nSrcDataLen = c_uint(frame_data.frameInfo.size)
#                 stPixelConvertParams.nPaddingX = c_uint(frame_data.frameInfo.paddingX)
#                 stPixelConvertParams.nPaddingY = c_uint(frame_data.frameInfo.paddingY)
#                 stPixelConvertParams.eBayerDemosaic = c_int(IMV_EBayerDemosaic.demosaicBilinear if hasattr(IMV_EBayerDemosaic, 'demosaicBilinear') else 1)
#                 stPixelConvertParams.eDstPixelFormat = c_int(dst_pixel)
#                 stPixelConvertParams.pDstBuf = dst_buffer
#                 stPixelConvertParams.nDstBufSize = c_uint(dst_size)
#                 stPixelConvertParams.nDstDataLen = c_uint(0)

#                 # Perform pixel conversion
#                 ret = self.camera.IMV_PixelConvert(stPixelConvertParams)
#                 if ret != IMV_OK:
#                     self.status_signal.emit(f"Pixel conversion failed: {ret}")
#                     self.logger.error(f"Pixel conversion failed: {ret}")
#                     return None

#                 # Create numpy array and convert BGR to RGB using fast slicing
#                 image_array = np.ctypeslib.as_array(dst_buffer).reshape((height, width, 3))
#                 rgb_image = image_array[:, :, ::-1]  # Fast BGR to RGB conversion, change memory reading order rather than data copy

#             # Release frame buffer
#             self.camera.IMV_ReleaseFrame(frame_data)
#             self.logger.debug("Released frame buffer back to SDK")

#             return rgb_image

#         except Exception as e:
#             self.status_signal.emit(f"Image conversion error: {str(e)}")
#             return None

    def _convert_to_qimage(self, rgb_image):
        """
        Convert RGB image to QImage for Qt display.

        Args:
            rgb_image: RGB image (numpy array)

        Returns:
            QImage object or None
        """
        try:
            height, width, channels = rgb_image.shape
            bytes_per_line = channels * width

            # Image is already in RGB format, no conversion needed
            # Use tobytes() to create independent data copy (faster than .copy())
            q_image = QImage(
                rgb_image.tobytes(),
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )

            return q_image  # No need for .copy() as tobytes() already creates a copy

        except Exception as e:
            self.status_signal.emit(f"QImage conversion error: {str(e)}")
            return None

    def stop(self):
        """
        Signal the worker thread to stop.
        """
        self.status_signal.emit("Stop signal received")
        self.running = False
        self.recognition_running = False  # Stop recognition thread

    def _cleanup(self):
        """
        Cleanup camera resources and threads.

        Always called in finally block to ensure proper resource release.
        """
        try:
            self.status_signal.emit("Cleaning up camera resources...")

            # Stop recognition thread
            if self.recognition_thread and self.recognition_thread.is_alive():
                self.recognition_running = False
                self.recognition_thread.join(timeout=2.0)
                self.status_signal.emit("Recognition thread stopped")

            # Stop grabbing
            if self.camera.IMV_IsGrabbing():
                ret = self.camera.IMV_StopGrabbing()
                if ret == IMV_OK:
                    self.status_signal.emit("Frame grabbing stopped")
                else:
                    self.status_signal.emit(f"Stop grabbing error: {ret}")

            self.status_signal.emit("Worker thread cleanup completed")

        except Exception as e:
            self.status_signal.emit(f"Cleanup error: {str(e)}")
