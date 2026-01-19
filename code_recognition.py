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
import logging
import warnings

try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False

# Configure module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create file handler if not already exists
if not logger.handlers:
    file_handler = logging.FileHandler('code_recognition.log', mode='a')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

if not PYZBAR_AVAILABLE:
    logger.warning("pyzbar not available. Barcode detection disabled.")


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
        """
        # Initialize QR code detector
        try:
            self.qr_detector = cv2.wechat_qrcode_WeChatQRCode(
                "detect.prototxt", "detect.caffemodel",
                "sr.prototxt", "sr.caffemodel"
            )
            self.qr_available = True
        except Exception as e:
            self.qr_available = False
            logger.warning(f"OpenCV wechat_qrcode not available. QR detection disabled: {e}")

        self.last_result = None  # For deduplication

# Deprecated method:
#     def detect_codes(self, image):
#         """
#         Detect QR codes and barcodes in image.

#         Args:
#             image: OpenCV image (numpy array, BGR format)

#         Returns:
#             str: Decoded text (comma-separated if multiple codes)
#             None: If no codes detected

#         """
#         results = []

#         # Detect QR codes
#         if self.qr_available:
#             qr_results = self._detect_qr_codes(image)
#             results.extend(qr_results)

#         # Detect barcodes
#         if PYZBAR_AVAILABLE:
#             barcode_results = self._detect_barcodes(image)
#             results.extend(barcode_results)

#         # Return combined results
#         if results:
#             combined = ", ".join(results)
#             # Simple deduplication
#             if combined != self.last_result:
#                 self.last_result = combined
#                 logging.getLogger(__name__).info(f"Detected codes: {combined}")
#                 return combined

#         return None

    def detect_codes_with_positions(self, image):
        """
        Detect QR codes and barcodes in image with position information.

        Args:
            image: OpenCV image (numpy array, BGR format)

        Returns:
            tuple: (decoded_text, detections_list)
                decoded_text: str or None
                detections_list: [{'type': str, 'text': str, 'points': np.array}, ...]
        """
        detections = []
        texts = []

        # Detect QR codes with positions
        if self.qr_available:
            qr_detections, qr_texts = self._detect_qr_codes_with_positions(image)
            detections.extend(qr_detections)
            texts.extend(qr_texts)

        # Detect barcodes with positions
        if PYZBAR_AVAILABLE:
            barcode_detections, barcode_texts = self._detect_barcodes_with_positions(image)
            detections.extend(barcode_detections)
            texts.extend(barcode_texts)

        # Return combined results
        if texts:
            combined_text = ", ".join(texts)
            # Simple deduplication
            if combined_text != self.last_result:
                self.last_result = combined_text
                logging.getLogger(__name__).info(f"Detected codes: {combined_text}")
                return combined_text, detections
            else:
                # Same result, but still return detections for display
                return None, detections

        return None, []

# Deprecated method:
#     def _detect_qr_codes(self, image):
#         """
#         Detect QR codes using OpenCV wechat_qrcode.

#         Args:
#             image: OpenCV image

#         Returns:
#             list: Decoded QR code texts
#         """
#         try:
#             texts, points = self.qr_detector.detectAndDecode(image)

#             results = []
#             for i, text in enumerate(texts):
#                 if text:
#                     results.append(f"QR:{text}")

#             return results

#         except Exception as e:
#             logging.getLogger(__name__).exception(f"QR detection error: {e}")
#             return []

    def _detect_qr_codes_with_positions(self, image):
        """
        Detect QR codes using OpenCV wechat_qrcode with position information.

        Args:
            image: OpenCV image

        Returns:
            tuple: (detections_list, texts_list)
                detections: [{'type': 'QR', 'text': str, 'points': np.array}, ...]
                texts: [str, ...]
        """
        try:
            texts, points = self.qr_detector.detectAndDecode(image)

            detections = []
            text_results = []

            for i, text in enumerate(texts):
                if text and i < len(points):
                    detections.append({
                        'type': 'QR',
                        'points': points[i].astype(np.int32)
                    })
                    text_results.append(f"QR:{text}")

            return detections, text_results

        except Exception as e:
            logging.getLogger(__name__).exception(f"QR detection error: {e}")
            return [], []

# Depreceted method:
#     def _detect_barcodes(self, image):
#         """
#         Detect barcodes using pyzbar.

#         Args:
#             image: OpenCV image

#         Returns:
#             list: Decoded barcode texts with types
#         """
#         try:
#             barcodes = pyzbar.decode(image)

#             results = []
#             for barcode in barcodes:
#                 # Decode barcode data
#                 barcode_data = barcode.data.decode('utf-8')
#                 barcode_type = barcode.type

#                 if barcode_type != "QRCODE":  # Avoid duplicates with QR detection
#                     results.append(f"{barcode_type}:{barcode_data}")

#             return results

#         except Exception as e:
#             logging.getLogger(__name__).exception(f"Barcode detection error: {e}")
#             return []

    def _detect_barcodes_with_positions(self, image):
        """
        Detect barcodes using pyzbar with position information.

        Args:
            image: OpenCV image

        Returns:
            tuple: (detections_list, texts_list)
                detections: [{'type': str, 'text': str, 'points': np.array}, ...]
                texts: [str, ...]
        """
        try:
            barcodes = pyzbar.decode(image)

            detections = []
            text_results = []

            for barcode in barcodes:
                # Decode barcode data
                barcode_data = barcode.data.decode('utf-8')
                barcode_type = barcode.type

                if barcode_type != "QRCODE":  # Avoid duplicates with QR detection
                    # Get polygon points
                    points = np.array([(p.x, p.y) for p in barcode.polygon], dtype=np.int32)

                    detections.append({
                        'type': barcode_type,
                        'points': points
                    })
                    text_results.append(f"{barcode_type}:{barcode_data}")

            return detections, text_results

        except Exception as e:
            logging.getLogger(__name__).exception(f"Barcode detection error: {e}")
            return [], []
