#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Camera Configuration Module
============================

This module provides a centralized configuration class for managing camera parameters
across the entire project. It uses a singleton pattern to ensure consistent parameter
values across all modules.

Usage:
    from camera_config import CameraConfig

    # Get the singleton instance
    config = CameraConfig()

    # Access parameters
    print(config.exposure_time.value)
    config.exposure_time.value = 5000.0
"""

from ctypes import *
import sys
import logging

sys.path.append("C:/Program Files/HuarayTech/MV Viewer/Development/Samples/Python/IMV/MVSDK")
from IMVApi import *

# Configure module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create file handler if not already exists
if not logger.handlers:
    file_handler = logging.FileHandler('camera_config.log', mode='w')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


class CameraConfig:
    """
    Singleton class for managing camera parameters.

    This class stores all camera parameters and provides centralized access
    to them from any module in the project.
    """

    _instance = None

    def __new__(cls):
        """Implement singleton pattern"""
        if cls._instance is None:
            cls._instance = super(CameraConfig, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize camera parameters (only once due to singleton)"""
        if self._initialized:
            return

        # Create MvCamera instance for IMV_String types
        self._camera_handle = MvCamera()

        # --- Camera Parameters ---
        self.exposure_time = c_double(0)
        self.exposure_mode = IMV_String()
        self.raw_gain = c_double(0)
        self.gamma = c_double(0)
        self.frame_rate = c_double(0)
        self.ip_address = IMV_String()
        self.pixel_format = IMV_String()
        self.balance_auto = IMV_String()
        self.balance_ratio_selector = IMV_String()
        self.balance_ratio = c_double(0)

        self._initialized = True

    def load_from_camera(self, camera):
        """
        Load parameter values from a connected camera.

        Args:
            camera: MvCamera instance (already opened and connected)

        Returns:
            bool: True if all parameters loaded successfully, False otherwise
        """
        success = True

        # Load exposure time
        ret = camera.IMV_FeatureIsReadable("ExposureTime")
        if ret == IMV_OK:
            ret = camera.IMV_GetDoubleFeatureValue("ExposureTime", self.exposure_time)
            if ret != IMV_OK:
                logger.error(f"Get ExposureTime failed! ErrorCode: {ret}")
                success = False

        # Load exposure mode
        ret = camera.IMV_FeatureIsReadable("ExposureAuto")
        if ret == IMV_OK:
            ret = camera.IMV_GetEnumFeatureValue("ExposureAuto", self.exposure_mode)
            if ret != IMV_OK:
                logger.error(f"Get ExposureAuto failed! ErrorCode: {ret}")
                success = False

        # Load gain
        ret = camera.IMV_FeatureIsReadable("GainRaw")
        if ret == IMV_OK:
            ret = camera.IMV_GetDoubleFeatureValue("GainRaw", self.raw_gain)
            if ret != IMV_OK:
                logger.error(f"Get GainRaw failed! ErrorCode: {ret}")
                success = False

        # Load gamma
        ret = camera.IMV_FeatureIsReadable("Gamma")
        if ret == IMV_OK:
            ret = camera.IMV_GetDoubleFeatureValue("Gamma", self.gamma)
            if ret != IMV_OK:
                logger.error(f"Get Gamma failed! ErrorCode: {ret}")
                success = False

        # Load frame rate
        ret = camera.IMV_FeatureIsReadable("AcquisitionFrameRate")
        if ret == IMV_OK:
            ret = camera.IMV_GetDoubleFeatureValue("AcquisitionFrameRate", self.frame_rate)
            if ret != IMV_OK:
                logger.error(f"Get AcquisitionFrameRate failed! ErrorCode: {ret}")
                success = False

        # Load IP address
        ret = camera.IMV_FeatureIsReadable("GevCurrentIPAddress")
        if ret == IMV_OK:
            ret = camera.IMV_GetStringFeatureValue("GevCurrentIPAddress", self.ip_address)
            if ret != IMV_OK:
                logger.error(f"Get GevCurrentIPAddress failed! ErrorCode: {ret}")
                success = False

        # Load pixel format
        ret = camera.IMV_FeatureIsReadable("PixelFormat")
        if ret == IMV_OK:
            ret = camera.IMV_GetEnumFeatureValue("PixelFormat", self.pixel_format)
            if ret != IMV_OK:
                logger.error(f"Get PixelFormat failed! ErrorCode: {ret}")
                success = False

        # Load white balance auto
        ret = camera.IMV_FeatureIsReadable("BalanceWhiteAuto")
        if ret == IMV_OK:
            ret = camera.IMV_GetEnumFeatureValue("BalanceWhiteAuto", self.balance_auto)
            if ret != IMV_OK:
                logger.error(f"Get BalanceWhiteAuto failed! ErrorCode: {ret}")
                success = False

        # Load balance ratio selector
        ret = camera.IMV_FeatureIsReadable("BalanceRatioSelector")
        if ret == IMV_OK:
            ret = camera.IMV_GetEnumFeatureValue("BalanceRatioSelector", self.balance_ratio_selector)
            if ret != IMV_OK:
                logger.error(f"Get BalanceRatioSelector failed! ErrorCode: {ret}")
                success = False

        # Load balance ratio
        ret = camera.IMV_FeatureIsReadable("BalanceRatio")
        if ret == IMV_OK:
            ret = camera.IMV_GetDoubleFeatureValue("BalanceRatio", self.balance_ratio)
            if ret != IMV_OK:
                logger.error(f"Get BalanceRatio failed! ErrorCode: {ret}")
                success = False

        return success

    def get_dict(self):
        """
        Get all parameters as a dictionary (for display or serialization).

        Returns:
            dict: All parameter values
        """
        return {
            'exposure_time': self.exposure_time.value,
            'exposure_mode': self.exposure_mode.str.decode('utf-8') if self.exposure_mode.str else '',
            'raw_gain': self.raw_gain.value,
            'gamma': self.gamma.value,
            'frame_rate': self.frame_rate.value,
            'ip_address': self.ip_address.str.decode('utf-8') if self.ip_address.str else '',
            'pixel_format': self.pixel_format.str.decode('utf-8') if self.pixel_format.str else '',
            'balance_auto': self.balance_auto.str.decode('utf-8') if self.balance_auto.str else '',
            'balance_ratio_selector': self.balance_ratio_selector.str.decode('utf-8') if self.balance_ratio_selector.str else '',
            'balance_ratio': self.balance_ratio.value,
        }

    def get_editability(self, camera, param_name=None):
        """
        Get the editability of each parameter from the connected camera.

        Args:
            camera: MvCamera instance (already opened and connected)
            param_name: Optional parameter name to check editability for
        """
        if param_name:
            editability = camera.IMV_FeatureIsWriteable(param_name)

            return editability

    def __repr__(self):
        """String representation for debugging"""
        params = self.get_dict()
        return f"CameraConfig({', '.join(f'{k}={v}' for k, v in params.items())})"
