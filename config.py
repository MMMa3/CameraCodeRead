#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration File Template
============================

Customize these settings for your application.
"""

# Camera Settings
CAMERA_TIMEOUT_MS = 1000  # Frame acquisition timeout
INTERFACE_TYPE = "all"  # "all", "usb", "gige", etc.

# Recognition Settings
RECOGNITION_INTERVAL = 3  # Process every Nth frame (1 = every frame)
ENABLE_QR_DETECTION = True
ENABLE_BARCODE_DETECTION = True

# UI Settings
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
VIDEO_DISPLAY_WIDTH = 800
VIDEO_DISPLAY_HEIGHT = 600

# TODO: Add more configuration options as needed
# - Camera parameters (exposure, gain, etc.)
# - Recognition confidence thresholds
# - Logging settings
# - Result export settings
