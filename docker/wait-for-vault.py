#!/usr/bin/env python3
"""Entrypoint wrapper: block until Vault reports unsealed, then exec the real command.

Uses Vault's unauthenticated /v1/sys/seal-status HTTP endpoint (no vault CLI in
this image, no token needed). Skipped entirely when VAULT_ADDR isn't set, since
Vault is optional for this app (see CLAUDE.md "Vault secrets").
"""
import logging
import os
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("wait_for_vault")

VAULT_ADDR = os.environ.get("VAULT_ADDR")
POLL_INTERVAL_SECONDS = 5


def wait_for_unsealed():
    url = f"{VAULT_ADDR.rstrip('/')}/v1/sys/seal-status"
    logger.info(f"Esperando a que Vault ({VAULT_ADDR}) este unsealed...")
    while True:
        try:
            resp = requests.get(url, timeout=5)
            if resp.ok and resp.json().get("sealed") is False:
                logger.info("Vault unsealed, arrancando app...")
                return
        except requests.RequestException as exc:
            logger.warning(f"Vault no disponible todavia ({exc}), reintentando...")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    if VAULT_ADDR:
        wait_for_unsealed()
    else:
        logger.info("VAULT_ADDR no definido, omitiendo espera a Vault.")
    os.execvp(sys.argv[1], sys.argv[1:])
