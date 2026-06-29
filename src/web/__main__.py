"""Run the web app locally: ``python -m src.web``.

Binds to 0.0.0.0 so you can open it from your phone on the same WiFi
(http://<your-computer-ip>:8000). Set PORT to change the port.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.web.app:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
