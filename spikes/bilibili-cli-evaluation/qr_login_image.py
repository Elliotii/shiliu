"""Generate a visible Bilibili login QR image, then wait for confirmation.

This helper keeps bilibili-cli's official QrCodeLogin flow intact while saving
the QR code as a PNG that Codex can display in the conversation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import qrcode
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents

from bili_cli.auth import save_credential


QR_PATH = Path(__file__).with_name("artifacts") / "bilibili-login-qr.png"


async def main() -> None:
    login = QrCodeLogin()
    await login.generate_qrcode()

    qr_link = getattr(login, "_QrCodeLogin__qr_link", None)
    if not qr_link:
        raise RuntimeError("QrCodeLogin did not expose a QR link")

    QR_PATH.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(qr_link).save(QR_PATH)
    print(f"QR_READY={QR_PATH.resolve()}", flush=True)

    while True:
        state = await login.check_state()
        if state == QrCodeLoginEvents.DONE:
            save_credential(login.get_credential())
            print("LOGIN_SUCCESS", flush=True)
            return
        if state == QrCodeLoginEvents.TIMEOUT:
            raise RuntimeError("二维码已过期，请重新生成")
        if state == QrCodeLoginEvents.CONF:
            print("QR_SCANNED_WAITING_CONFIRMATION", flush=True)
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
