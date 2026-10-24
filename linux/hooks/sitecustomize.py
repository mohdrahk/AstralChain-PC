# Loaded by the native_trace child Python of linux/build.py (PYTHONPATH). nvn_build makes the vulkan-1 import
# library from C:/Windows/System32/vulkan-1.dll's exports; on Linux the list comes from linux/vulkan-1.def,
# taken from a Windows build (Wine's vulkan-1.dll lacks 5 of the loader's 265 exports).
import os

if os.environ.get('AC_LINUX_BUILD'):
    from pathlib import Path
    import astral_chain.nvn_build as nvn_build
    nvn_build.VULKAN_DLL = Path(os.environ['AC_LINUX_BUILD'])/'linux'/'vulkan-1.def'
    names = [line.strip() for line in nvn_build.VULKAN_DLL.read_text().splitlines()[2:] if line.strip()]
    nvn_build._pe_exports = lambda path: names
