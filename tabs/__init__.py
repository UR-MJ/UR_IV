# tabs/__init__.py
"""Tab 모듈"""
from .browser_tab import BrowserTab
from .settings_tab import SettingsTab
from .pnginfo_tab import PngInfoTab
from .search_tab import SearchTab
from .editor_tab import MosaicEditor
from .xyz_plot_tab import XYZPlotTab
from .event_gen_tab import EventGenTab
from .i2i_tab import Img2ImgTab
from .inpaint_tab import InpaintTab

__all__ = [
    'BrowserTab',
    'SettingsTab',
    'PngInfoTab',
    'SearchTab',
    'MosaicEditor',
    'EventGenTab',
    'XYZPlotTab',
    'Img2ImgTab',
    'InpaintTab',
]