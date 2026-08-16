"""Vercel entry point for SchoolFlow's Python API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, init_db

init_db()

# Vercel detects a BaseHTTPRequestHandler subclass named `handler`.
handler = App
