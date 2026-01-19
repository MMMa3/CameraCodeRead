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
logger.setLevel(logging.DEBUG)  # Changed to DEBUG to capture debug messages

# Create file handler if not already exists
if not logger.handlers:
    file_handler = logging.FileHandler('camera_config.log', mode='a')  # Changed to 'a' (append) mode
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

logger.info(f"Camera config module loaded at {__name__}")


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
        logger.info("Starting to load parameters from camera...")
        success = True

        # Load exposure time
        logger.debug("Checking ExposureTime readability...")
        rel = camera.IMV_FeatureIsReadable("ExposureTime")
        if rel == True:
            ret = camera.IMV_GetDoubleFeatureValue("ExposureTime", self.exposure_time)
            logger.debug(f"Exposure time: {self.exposure_time.value}")
            if ret != IMV_OK:
                logger.error(f"Get ExposureTime failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"ExposureTime is not readable.ErrorCode: {rel}")

        # Load exposure mode
        logger.debug("Checking ExposureAuto readability...")
        rel = camera.IMV_FeatureIsReadable("ExposureAuto")
        if rel == True:
            ret = camera.IMV_GetEnumFeatureSymbol("ExposureAuto", self.exposure_mode)
            logger.debug(f"Exposure mode: {self.exposure_mode.str.decode('utf-8') if self.exposure_mode.str else 'None'}")
            if ret != IMV_OK:
                logger.error(f"Get ExposureAuto failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"ExposureAuto is not readable. ErrorCode: {rel}")

        # Load gain
        logger.debug("Checking GainRaw readability...")
        rel = camera.IMV_FeatureIsReadable("GainRaw")
        if rel == True:
            ret = camera.IMV_GetDoubleFeatureValue("GainRaw", self.raw_gain)
            logger.debug(f"Raw Gain: {self.raw_gain.value}")
            if ret != IMV_OK:
                logger.error(f"Get GainRaw failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"GainRaw is not readable. ErrorCode: {rel}")

        # Load gamma
        logger.debug("Checking Gamma readability...")
        rel = camera.IMV_FeatureIsReadable("Gamma")
        if rel == True:
            ret = camera.IMV_GetDoubleFeatureValue("Gamma", self.gamma)
            logger.debug(f"Gamma: {self.gamma.value}")
            if ret != IMV_OK:
                logger.error(f"Get Gamma failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"Gamma is not readable. ErrorCode: {rel}")

        # Load frame rate
        logger.debug("Checking AcquisitionFrameRate readability...")
        rel = camera.IMV_FeatureIsReadable("AcquisitionFrameRate")
        if rel == True:
            ret = camera.IMV_GetDoubleFeatureValue("AcquisitionFrameRate", self.frame_rate)
            logger.debug(f"Acquisition Frame Rate: {self.frame_rate.value}")
            if ret != IMV_OK:
                logger.error(f"Get AcquisitionFrameRate failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"AcquisitionFrameRate is not readable. ErrorCode: {rel}")

        # Load IP address
        logger.debug("Checking GevCurrentIPAddress readability...")
        rel = camera.IMV_FeatureIsReadable("GevCurrentIPAddress")
        if rel == True:
            ret = camera.IMV_GetStringFeatureValue("GevCurrentIPAddress", self.ip_address)
            logger.debug(f"Gev Current IP Address: {self.ip_address.str.decode('utf-8') if self.ip_address.str else 'None'}")
            if ret != IMV_OK:
                logger.error(f"Get GevCurrentIPAddress failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"GevCurrentIPAddress is not readable. ErrorCode: {rel}")

        # Load pixel format
        logger.debug("Checking PixelFormat readability...")
        rel = camera.IMV_FeatureIsReadable("PixelFormat")
        if rel == True:
            ret = camera.IMV_GetEnumFeatureSymbol("PixelFormat", self.pixel_format)
            logger.debug(f"Pixel format: {self.pixel_format.str.decode('utf-8') if self.pixel_format.str else 'None'}")
            if ret != IMV_OK:
                logger.error(f"Get PixelFormat failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"PixelFormat is not readable. ErrorCode: {rel}")

        # Load white balance auto
        logger.debug("Checking BalanceWhiteAuto readability...")
        rel = camera.IMV_FeatureIsReadable("BalanceWhiteAuto")
        if rel == True:
            ret = camera.IMV_GetEnumFeatureSymbol("BalanceWhiteAuto", self.balance_auto)
            logger.debug(f"Balance White Auto: {self.balance_auto.str.decode('utf-8') if self.balance_auto.str else 'None'}")
            if ret != IMV_OK:
                logger.error(f"Get BalanceWhiteAuto failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"BalanceWhiteAuto is not readable. ErrorCode: {rel}")

        # Load balance ratio selector
        logger.debug("Checking BalanceRatioSelector readability...")
        rel = camera.IMV_FeatureIsReadable("BalanceRatioSelector")
        if rel == True:
            ret = camera.IMV_GetEnumFeatureSymbol("BalanceRatioSelector", self.balance_ratio_selector)
            logger.debug(f"Balance Ratio Selector: {self.balance_ratio_selector.str.decode('utf-8') if self.balance_ratio_selector.str else 'None'}")
            if ret != IMV_OK:
                logger.error(f"Get BalanceRatioSelector failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"BalanceRatioSelector is not readable. ErrorCode: {rel}")

        # Load balance ratio
        logger.debug("Checking BalanceRatio readability...")
        rel = camera.IMV_FeatureIsReadable("BalanceRatio")
        if rel == True:
            ret = camera.IMV_GetDoubleFeatureValue("BalanceRatio", self.balance_ratio)
            logger.debug(f"Balance Ratio: {self.balance_ratio.value}")
            if ret != IMV_OK:
                logger.error(f"Get BalanceRatio failed! ErrorCode: {ret}")
                success = False
        else:
            logger.warning(f"BalanceRatio is not readable. ErrorCode: {rel}")

        logger.info(f"Finished loading parameters. Success: {success}")
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

        Returns:
            bool: True if parameter is writable, False otherwise
        """
        if param_name:
            ret = camera.IMV_FeatureIsWriteable(param_name)
            return ret

        return False

    def __repr__(self):
        """String representation for debugging"""
        params = self.get_dict()
        return f"CameraConfig({', '.join(f'{k}={v}' for k, v in params.items())})"
