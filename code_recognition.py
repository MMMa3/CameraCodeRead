#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
QR Code and Barcode Recognition Module
=======================================

This module provides QR code and barcode detection functionality using:
- OpenCV's wechat_qrcode detector (high accuracy for QR codes)
- pyzbar library (standard barcode detection)

Features:
- Multi-code detection in single frame
- Visual annotation (bounding boxes)
- Result deduplication
"""

import cv2
import numpy as np

# TODO: Install these libraries: pip install opencv-contrib-python pyzbar
try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    print("WARNING: pyzbar not available. Barcode detection disabled.")


class CodeRecognizer:
    """
    QR Code and Barcode recognition engine.

    Supports:
    - QR codes (via OpenCV wechat_qrcode)
    - Barcodes (via pyzbar: EAN, UPC, Code128, etc.)
    """

    def __init__(self):
        """
        Initialize recognition engines.

        TODO: Add model path configuration for wechat_qrcode
        TODO: Add barcode type filtering options
        """
        # Initialize QR code detector
        try:
            self.qr_detector = cv2.wechat_qrcode_WeChatQRCode(
                "detect.prototxt", "detect.caffemodel",
                "sr.prototxt", "sr.caffemodel"
            )
            self.qr_available = True
        except:
            self.qr_available = False
            print("WARNING: OpenCV wechat_qrcode not available. QR detection disabled.")

        self.last_result = None  # For deduplication

    def detect_codes(self, image):
        """
        Detect QR codes and barcodes in image.

        Args:
            image: OpenCV image (numpy array, BGR format)

        Returns:
            str: Decoded text (comma-separated if multiple codes)
            None: If no codes detected

        TODO: Return structured data (type, position, confidence)
        TODO: Add result filtering by confidence threshold
        """
        results = []

        # Detect QR codes
        if self.qr_available:
            qr_results = self._detect_qr_codes(image)
            results.extend(qr_results)

        # Detect barcodes
        if PYZBAR_AVAILABLE:
            barcode_results = self._detect_barcodes(image)
            results.extend(barcode_results)

        # Return combined results
        if results:
            combined = ", ".join(results)
            # Simple deduplication
            if combined != self.last_result:
                self.last_result = combined
                return combined

        return None

    def _detect_qr_codes(self, image):
        """
        Detect QR codes using OpenCV wechat_qrcode.

        Args:
            image: OpenCV image

        Returns:
            list: Decoded QR code texts
        """
        try:
            texts, points = self.qr_detector.detectAndDecode(image)

            results = []
            for i, text in enumerate(texts):
                if text:
                    results.append(f"QR:{text}")

                    # TODO: Draw bounding box on image
                    # if len(points) > i:
                    #     self._draw_box(image, points[i])

            return results

        except Exception as e:
            print(f"QR detection error: {e}")
            return []

    def _detect_barcodes(self, image):
        """
        Detect barcodes using pyzbar.

        Args:
            image: OpenCV image

        Returns:
            list: Decoded barcode texts with types
        """
        try:
            barcodes = pyzbar.decode(image)

            results = []
            for barcode in barcodes:
                # Decode barcode data
                barcode_data = barcode.data.decode('utf-8')
                barcode_type = barcode.type

                results.append(f"{barcode_type}:{barcode_data}")

                # TODO: Draw bounding box
                # points = barcode.polygon
                # self._draw_polygon(image, points)

            return results

        except Exception as e:
            print(f"Barcode detection error: {e}")
            return []

    def _draw_box(self, image, points):
        """
        Draw bounding box on image.

        TODO: Implement visual annotation
        """
        pass
