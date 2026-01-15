#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Code Storage Module
============================

This module stores code-information recognized by the camera to a json file
"""

import json
import os
from datetime import datetime
from threading import Lock
import logging

class CodeStorage:
    """
    CodeStorage Manager

    This class:
    - Store recognized code information to a json file
    - Thread-safe operations using a lock
    - Store timestamped entries
    - Auto-deduplicate based on code content
    """

    def __init__(self, storage_path = "recognized_codes.json") -> None:
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
        
        self.storage_path = storage_path
        self.lock = Lock()
        self.codes_cache = {}

        # Load existing codes if file exists
        self._load_from_file()

    def _load_from_file(self) -> None:
        """Load existing codes from the json file into the cache"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for entry in data.get('codes', []):
                        self.codes_cache[entry['info']] = entry
            except Exception as e:
                self.logger.error(f"Error loading codes from file: {e}")

    def _save_to_file(self) -> None:
        """Save the current codes cache to the json file"""
        try:
            data = {'codes': list(self.codes_cache.values())}
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving codes to file: {e}")

    def add_code(self, text,  code_type='Unknown') -> bool:
        """
        Add a recognized code to the storage if not already present.

        Args:
            text (str): The recognized code text.
            code_type (str): The type of the code (e.g., QR, Barcode).
        """
        with self.lock:
            is_new = text not in self.codes_cache

            if is_new:
                entry = {
                    'info': text,
                    'type': code_type,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                self.codes_cache[text] = entry
                self._save_to_file()
                self.logger.info(f"Stored new code: {entry}")
            else:
                self.logger.info(f"Duplicate code ignored: {text}")

            return is_new
        
    def get_all_codes(self):
        """
        Get all stored codes.

        Returns:
            list: List of all stored code entries.
        """
        with self.lock:
            return list(self.codes_cache.values())