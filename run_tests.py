"""
Runner script to launch SuperMCP QA tests in Blender background mode.
Usage: /opt/blender/blender --background --python run_tests.py
"""
import sys
import unittest
import os

# Add tests directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.test_super_mcp import TestSuperMCP

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSuperMCP)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())
