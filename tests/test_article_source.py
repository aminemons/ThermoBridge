"""Catch syntax corruption independently of optional document dependencies."""
import ast
from pathlib import Path


def test_article_generator_is_valid_python():
    root = Path(__file__).resolve().parents[1]
    ast.parse((root / 'scripts/build_article.py').read_text(encoding='utf-8'))
