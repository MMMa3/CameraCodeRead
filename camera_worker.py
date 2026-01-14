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
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import logging

from code_recognition import CodeRecognizer
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
    """

    # Define signals for thread-safe communication
    image_signal = Signal(QImage)
    result_signal = Signal(str)
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, camera):
        """
        Initialize the camera worker.

        Args:
            camera: MvCamera instance (already opened)
        """
        super().__init__()
        logging.basicConfig(filename='camera_worker.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.camera = camera
        self.running = False
        self.recognizer = CodeRecognizer()

        # Frame skip counter for recognition optimization
        self.frame_count = 0
        self.recognition_interval = 3  # Process every 3rd frame

        # TODO: Add configurable recognition interval
        # TODO: Add frame rate monitoring

    def run(self):
        """
        Main worker thread loop.

        Workflow:
        1. Start grabbing frames (IMV_StartGrabbing)
        2. Loop: Get frame -> Convert -> Recognize -> Emit signals
        3. Cleanup: Stop grabbing -> Release resources
        """
        self.running = True

        try:
            # Step 1: Start grabbing frames
            self.status_signal.emit("Starting frame acquisition...")
            ret = self.camera.IMV_StartGrabbing()

            if ret != IMV_OK:
                self.error_signal.emit(f"Failed to start grabbing. Error code: {ret}")
                logging.error(f"IMV_StartGrabbing failed with code: {ret}")
                return

            self.status_signal.emit("Frame acquisition started successfully")
            logging.info("Camera grabbing started")

            # Step 2: Main frame processing loop
            while self.running:
                try:
                    # Get frame from camera
                    frame_data = self._get_frame()

                    if frame_data is None:
                        continue

                    # Convert to OpenCV format
                    cv_image = self._convert_to_opencv(frame_data)

                    if cv_image is None:
                        continue

                    # Perform recognition (with frame skipping)
                    self.frame_count += 1
                    if self.frame_count % self.recognition_interval == 0:
                        decoded_text = self.recognizer.detect_codes(cv_image)
                        if decoded_text:
                            self.result_signal.emit(decoded_text)

                    # Convert to QImage and emit for display
                    q_image = self._convert_to_qimage(cv_image)
                    if q_image is not None:
                        logger.debug("Emitting image signal to UI thread")
                        self.image_signal.emit(q_image)

                except Exception as e:
                    self.status_signal.emit(f"Frame processing error: {str(e)}")
                    logging.error(f"Frame processing exception: {str(e)}")
                    continue

        except Exception as e:
            self.error_signal.emit(f"Critical error in worker thread: {str(e)}")

        finally:
            # Step 3: Cleanup - Always executed
            self._cleanup()

    def _get_frame(self):
        """
        Get a frame from the camera.

        Returns:
            IMV_Frame object or None on error

        TODO: Add timeout configuration
        TODO: Implement frame buffer management
        """
        frame = IMV_Frame()  # IMV_Frame defined in IMVADefines
        ret = self.camera.IMV_GetFrame(frame, 1000)  # 1000ms timeout

        if ret != IMV_OK:  # IMV_OK defined in IMVADefines
            self.status_signal.emit(f"Frame acquisition error: {ret}")
            logger.error(f"IMV_GetFrame failed with code: {ret}")
            return None
        logger.debug("Frame acquired successfully")
        return frame

    def _convert_to_opencv(self, frame_data):
        """
        Convert SDK frame buffer to OpenCV (numpy) format.

        Args:
            frame_data: IMV_Frame object

        Returns:
            numpy array (OpenCV image) or None

        """
        try:
            # Get frame properties
            width = frame_data.frameInfo.width
            height = frame_data.frameInfo.height
            pixel_format = frame_data.frameInfo.pixelFormat

            # Create numpy array from buffer
            # TODO: Handle different pixel formats (A7500CG20 output format: gvspPixelBayRG8--17301513) [done, unverified]
            if pixel_format == IMV_EPixelType.gvspPixelMono8:
                # Mono 8-bit
                image_array = np.ctypeslib.as_array(
                    (c_ubyte * frame_data.frameInfo.size).from_address(frame_data.pData)).reshape((height, width))

                # Convert to BGR for consistency
                cv_image = cv2.cvtColor(image_array, cv2.COLOR_GRAY2BGR)
    
            elif pixel_format == IMV_EPixelType.gvspPixelBGR8:
                # BGR 8-bit
                image_array = np.ctypeslib.as_array(
                    (c_ubyte * frame_data.frameInfo.size).from_address(frame_data.pData)).reshape((height, width, 3))
                cv_image = image_array

            else:  # Use SDK pixel convert function, convert to BGR8 and then convert to OpenCV format
                logger.debug(f"Trying pixel convert from format {pixel_format} to BGR8")

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
                stPixelConvertParams.eBayerDemosaic = c_int(IMV_EBayerDemosaic.demosaicBilinear if hasattr(IMV_EBayerDemosaic, 'demosaicBilinear') else 1)  # demosaic algorithm, bilinear is the medium choice, if frame rate low, try demosaicNearestNeighbor
                stPixelConvertParams.eDstPixelFormat = c_int(dst_pixel)
                stPixelConvertParams.pDstBuf = dst_buffer
                stPixelConvertParams.nDstBufSize = c_uint(dst_size)
                stPixelConvertParams.nDstDataLen = c_uint(0)

                # Perform pixel conversion
                ret = self.camera.IMV_PixelConvert(stPixelConvertParams)
                if ret != IMV_OK:
                    self.status_signal.emit(f"Pixel conversion failed: {ret}")
                    logger.error(f"Pixel conversion failed: {ret}")
                    return None

                # Create numpy array from converted buffer
                image_array = np.ctypeslib.as_array(dst_buffer).reshape((height, width, 3))
                cv_image = image_array

            # Release frame buffer
            self.camera.IMV_ReleaseFrame(frame_data)
            logger.debug("Released frame buffer back to SDK")

            return cv_image

        except Exception as e:
            self.status_signal.emit(f"Image conversion error: {str(e)}")
            return None

    def _convert_to_qimage(self, cv_image):
        """
        Convert OpenCV image to QImage for Qt display.

        Args:
            cv_image: OpenCV image (numpy array)

        Returns:
            QImage object or None
        """
        try:
            height, width, channels = cv_image.shape
            bytes_per_line = channels * width

            # Convert BGR to RGB for Qt
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)

            q_image = QImage(
                rgb_image.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )

            return q_image.copy()  # Create a copy to avoid data corruption

        except Exception as e:
            self.status_signal.emit(f"QImage conversion error: {str(e)}")
            return None

    def stop(self):
        """
        Signal the worker thread to stop.
        """
        self.status_signal.emit("Stop signal received")
        self.running = False

    def _cleanup(self):
        """
        Cleanup camera resources.

        Always called in finally block to ensure proper resource release.
        """
        try:
            self.status_signal.emit("Cleaning up camera resources...")

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
