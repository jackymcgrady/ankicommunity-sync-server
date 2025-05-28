#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for Phase 4: Protocol Compatibility
Tests modern Anki sync protocol compatibility (>=2.1.57)
"""

import json
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ankisyncd.sync_app import SyncCollectionHandler, SyncApp
from ankisyncd.sync import (
    SYNC_VERSION_MIN, SYNC_VERSION_MAX, 
    SYNC_VERSION_09_V2_SCHEDULER, SYNC_VERSION_10_V2_TIMEZONE, SYNC_VERSION_11_DIRECT_POST,
    is_sync_version_supported, is_multipart_version, is_zstd_version
)


class TestProtocolCompatibility(unittest.TestCase):
    """Test modern Anki sync protocol compatibility."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_col = Mock()
        self.mock_col.mod = 1234567890000
        self.mock_col.usn.return_value = 100
        self.mock_col.schedVer.return_value = 2
        self.mock_col.path = "/tmp/test.anki2"
        self.mock_col.db = Mock()
        self.mock_col.db.scalar.return_value = None  # Empty collection
        self.mock_col.media = Mock()
        self.mock_col.media.connect.return_value = None
        self.mock_col.media.lastUsn.return_value = 50
        
        self.mock_session = Mock()
        self.mock_session.name = "testuser"
        self.mock_session.skey = "testsessionkey"
        
        self.handler = SyncCollectionHandler(self.mock_col, self.mock_session)
    
    def test_sync_version_constants(self):
        """Test that sync version constants are properly defined."""
        self.assertEqual(SYNC_VERSION_MIN, 8)
        self.assertEqual(SYNC_VERSION_MAX, 11)
        self.assertEqual(SYNC_VERSION_09_V2_SCHEDULER, 9)
        self.assertEqual(SYNC_VERSION_10_V2_TIMEZONE, 10)
        self.assertEqual(SYNC_VERSION_11_DIRECT_POST, 11)
    
    def test_sync_version_validation(self):
        """Test sync version validation functions."""
        # Test supported versions
        self.assertTrue(is_sync_version_supported(8))
        self.assertTrue(is_sync_version_supported(10))
        self.assertTrue(is_sync_version_supported(11))
        
        # Test unsupported versions
        self.assertFalse(is_sync_version_supported(7))
        self.assertFalse(is_sync_version_supported(12))
        
        # Test multipart vs direct post detection
        self.assertTrue(is_multipart_version(8))
        self.assertTrue(is_multipart_version(10))
        self.assertFalse(is_multipart_version(11))
        
        # Test compression detection
        self.assertFalse(is_zstd_version(8))
        self.assertFalse(is_zstd_version(10))
        self.assertTrue(is_zstd_version(11))
    
    def test_modern_client_version_parsing(self):
        """Test parsing of modern Anki client version strings."""
        # Test modern Anki Desktop format
        self.assertFalse(self.handler._old_client("anki,2.1.66 (70506aeb),linux"))
        self.assertFalse(self.handler._old_client("anki,2.1.57 (abc123),windows"))
        
        # Test old Anki Desktop format
        self.assertTrue(self.handler._old_client("ankidesktop,2.1.56,linux"))
        self.assertTrue(self.handler._old_client("ankidesktop,2.0.52,windows"))
        
        # Test AnkiDroid
        self.assertFalse(self.handler._old_client("ankidroid,2.16.0,android"))
        self.assertTrue(self.handler._old_client("ankidroid,2.2.2,android"))
        
        # Test edge cases
        self.assertFalse(self.handler._old_client(""))
        self.assertFalse(self.handler._old_client("invalid"))
        self.assertFalse(self.handler._old_client("unknown,1.0.0,platform"))
    
    def test_meta_response_modern_format(self):
        """Test that meta response includes all modern fields."""
        # Mock scm method
        self.handler.scm = Mock(return_value=1234567890000)
        
        # Test with modern sync version
        response = self.handler.meta(v=11, cv="anki,2.1.66 (70506aeb),linux")
        
        # Verify all required fields are present
        required_fields = ["mod", "scm", "usn", "ts", "musn", "msg", "cont", "hostNum", "empty"]
        for field in required_fields:
            self.assertIn(field, response)
        
        # Verify field types and values
        self.assertIsInstance(response["mod"], int)
        self.assertIsInstance(response["scm"], int)
        self.assertIsInstance(response["usn"], int)
        self.assertIsInstance(response["ts"], int)
        self.assertIsInstance(response["musn"], int)
        self.assertIsInstance(response["msg"], str)
        self.assertIsInstance(response["cont"], bool)
        self.assertIsInstance(response["hostNum"], int)
        self.assertIsInstance(response["empty"], bool)
        
        # Verify username is included
        self.assertIn("uname", response)
        self.assertEqual(response["uname"], "testuser")
        
        # Verify continuation is allowed
        self.assertTrue(response["cont"])
        self.assertEqual(response["msg"], "")
    
    def test_meta_response_version_compatibility(self):
        """Test meta response handles different sync versions correctly."""
        self.handler.scm = Mock(return_value=1234567890000)
        
        # Test with minimum supported version
        response = self.handler.meta(v=8, cv="anki,2.1.66,linux")
        self.assertTrue(response["cont"])
        
        # Test with maximum supported version
        response = self.handler.meta(v=11, cv="anki,2.1.66,linux")
        self.assertTrue(response["cont"])
    
    def test_meta_response_scheduler_compatibility(self):
        """Test meta response handles scheduler version compatibility."""
        self.handler.scm = Mock(return_value=1234567890000)
        
        # Test V2 scheduler with old client
        response = self.handler.meta(v=8, cv="anki,2.1.66,linux")
        self.assertFalse(response["cont"])
        self.assertIn("v2 scheduler", response["msg"])
    
    def test_meta_response_unsupported_version(self):
        """Test meta response rejects unsupported sync versions."""
        from webob.exc import HTTPNotImplemented
        
        # Test version too old
        with self.assertRaises(HTTPNotImplemented):
            self.handler.meta(v=7, cv="anki,2.1.66,linux")
        
        # Test version too new
        with self.assertRaises(HTTPNotImplemented):
            self.handler.meta(v=12, cv="anki,2.1.66,linux")
    
    def test_meta_response_old_client_rejection(self):
        """Test that old clients are properly rejected."""
        from webob import Response
        
        # Test old Anki Desktop
        response = self.handler.meta(v=10, cv="ankidesktop,2.1.56,linux")
        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 501)
    
    def test_meta_response_empty_collection(self):
        """Test meta response correctly identifies empty collections."""
        self.handler.scm = Mock(return_value=1234567890000)
        self.mock_col.db.scalar.return_value = None  # No cards
        
        response = self.handler.meta(v=11, cv="anki,2.1.66,linux")
        self.assertTrue(response["empty"])
    
    def test_meta_response_non_empty_collection(self):
        """Test meta response correctly identifies non-empty collections."""
        self.handler.scm = Mock(return_value=1234567890000)
        self.mock_col.db.scalar.return_value = 1  # Has cards
        
        response = self.handler.meta(v=11, cv="anki,2.1.66,linux")
        self.assertFalse(response["empty"])
    
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_meta_response_large_collection_handling(self, mock_exists, mock_getsize):
        """Test that large collections trigger one-way sync."""
        self.handler.scm = Mock(return_value=1234567890000)
        mock_exists.return_value = True
        mock_getsize.return_value = 200 * 1024 * 1024  # 200MB (over limit)
        
        with patch('anki.utils.intTime') as mock_time:
            mock_time.return_value = 9999999999000
            response = self.handler.meta(v=11, cv="anki,2.1.66,linux")
            
            # Schema timestamp should be updated to force one-way sync
            self.assertEqual(response["scm"], 9999999999000)
    
    def test_sync_app_protocol_version_handling(self):
        """Test that SyncApp properly handles protocol version information."""
        config = {"data_root": "/tmp/test_ankisyncd"}
        app = SyncApp(config)
        
        # Mock request with version information
        mock_req = Mock()
        mock_req.params = {'v': '11', 'cv': 'anki,2.1.66,linux', 'k': 'testkey'}
        mock_req.POST = b'{"test": "data"}'
        mock_req.path = "/sync/meta"
        
        # Test that version info is properly extracted and passed
        # This would be tested in integration tests with actual requests


class TestMediaSyncProtocolCompatibility(unittest.TestCase):
    """Test media sync protocol compatibility."""
    
    def setUp(self):
        """Set up test fixtures."""
        from ankisyncd.media_manager import MediaSyncHandler, ServerMediaManager
        
        self.temp_dir = tempfile.mkdtemp()
        self.media_manager = ServerMediaManager(self.temp_dir)
        
        self.mock_session = Mock()
        self.mock_session.skey = "testsessionkey"
        
        self.handler = MediaSyncHandler(self.media_manager, self.mock_session)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_media_begin_modern_response(self):
        """Test that media begin returns modern response format."""
        response = self.handler.begin("anki,2.1.66 (70506aeb),linux")
        
        # Verify response structure
        self.assertIn("data", response)
        self.assertIn("err", response)
        self.assertEqual(response["err"], "")
        
        # Verify data fields
        data = response["data"]
        self.assertIn("usn", data)
        self.assertIn("sk", data)
        self.assertIsInstance(data["usn"], int)
        self.assertIsInstance(data["sk"], str)


if __name__ == '__main__':
    unittest.main() 