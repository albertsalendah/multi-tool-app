# Migration Guide

Current:
- main.py
- video_downloader/
- captcha_manager/

Target:
- app/
- tools/video_downloader/
- libraries/captcha_manager/

Migration Order:
1. Introduce new directory structure.
2. Move downloader into tools.
3. Convert captcha_manager into shared library.
4. Add Tool Registry.
5. Add Job Manager.
6. Refactor browser creation into Browser Manager.
7. Migrate tools incrementally.
