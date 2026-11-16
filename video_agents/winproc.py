"""Запуск внешних программ без чёрных окон консоли (важно, когда работает окно программы без консоли)."""

import os
import subprocess

NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
