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
from collections import OrderedDict
import logging

class CodeStorage:
    """
    CodeStorage Manager

    This class:
    - Store recognized code information to a json file
    - Thread-safe operations using a lock
    - Store timestamped entries
    - Auto-deduplicate based on code content
    - Memory protection with cache size limits
    """

    def __init__(self, storage_path="recognized_codes.json", max_cache_size=10000, max_file_size_mb=100) -> None:
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
        self.max_cache_size = max_cache_size  # Maximum number of entries in cache
        self.max_file_size_mb = max_file_size_mb  # Maximum JSON file size in MB
        self.codes_cache = OrderedDict()  # Use OrderedDict to track insertion order

        # Load existing codes if file exists
        self._load_from_file()

    def _load_from_file(self) -> None:
        """Load existing codes from the json file into the cache"""
        if os.path.exists(self.storage_path):
            try:
                # Check file size before loading
                file_size = os.path.getsize(self.storage_path)
                file_size_mb = file_size / (1024 * 1024)

                if file_size_mb > self.max_file_size_mb:
                    self.logger.warning(
                        f"JSON file is too large ({file_size_mb:.2f}MB), "
                        f"only loading the most recent {self.max_cache_size} entries"
                    )
                    self._load_partial()
                    return

                # Normal loading if file size is acceptable
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    codes_list = data.get('codes', [])

                    # If total entries exceed max_cache_size, only load the most recent ones
                    if len(codes_list) > self.max_cache_size:
                        self.logger.warning(
                            f"File contains {len(codes_list)} entries, "
                            f"only loading the most recent {self.max_cache_size}"
                        )
                        codes_list.sort(key=lambda x: x['timestamp'], reverse=True)
                        codes_list = codes_list[:self.max_cache_size]

                    for entry in codes_list:
                        self.codes_cache[entry['info']] = entry

                    self.logger.info(f"Loaded {len(self.codes_cache)} entries from file")
            except Exception as e:
                self.logger.error(f"Error loading codes from file: {e}")

    def _load_partial(self) -> None:
        """Load only the most recent entries from a large JSON file"""
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                codes_list = data.get('codes', [])

                # Sort by timestamp and take the most recent entries
                codes_list.sort(key=lambda x: x['timestamp'], reverse=True)
                recent_codes = codes_list[:self.max_cache_size]

                for entry in recent_codes: # Check duplicates in most recent entries than all
                    self.codes_cache[entry['info']] = entry

                self.logger.info(f"Loaded the most recent {len(recent_codes)} entries")
        except Exception as e:
            self.logger.error(f"Error loading partial codes: {e}")

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

        Returns:
            bool: True if the code was newly added, False if it was a duplicate.
        """
        with self.lock:
            is_new = text not in self.codes_cache

            if is_new:
                # Check if cache is full
                if len(self.codes_cache) >= self.max_cache_size:
                    # Remove the oldest entry (FIFO strategy)
                    oldest_key = next(iter(self.codes_cache))
                    del self.codes_cache[oldest_key]
                    self.logger.info(f"Cache full, removed oldest entry: {oldest_key[:50]}...")

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