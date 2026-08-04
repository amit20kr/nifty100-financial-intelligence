import pytest
import importlib.util
import glob
import os

def test_dashboard_pages_import_cleanly():
    """
    Tests that all 8 Streamlit pages import cleanly without ModuleNotFoundError.
    This acts as a strict automated check for the path_setup.py bootstrap logic.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    pages_dir = os.path.join(project_root, 'src', 'dashboard', 'pages')
    
    page_files = glob.glob(os.path.join(pages_dir, '*.py'))
    assert len(page_files) > 0, "No page files found!"
    
    for page_path in page_files:
        if page_path.endswith('__init__.py'):
            continue
            
        module_name = os.path.basename(page_path).replace('.py', '')
        
        # We simulate the import
        spec = importlib.util.spec_from_file_location(module_name, page_path)
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            pytest.fail(f"Failed to import {module_name}: {str(e)}")
