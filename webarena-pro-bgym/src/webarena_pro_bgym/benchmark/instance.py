import logging
import time

import playwright.sync_api
import requests

from webarena_pro_core.autologin.sync_api import AutoLogin, LOGIN_MAX_ATTEMPTS

logger = logging.getLogger(__name__)

RESET_URL_VAR = "WEBARENA_PRO_FULL_RESET"


class WebArenaProInstance:
    """Utility class to access a WebArena Pro instance."""

    RESET_URL_VAR = RESET_URL_VAR

    def __init__(self) -> None:
        self._auto_login = AutoLogin(wait_until_ready=self._wait_until_site_ready)
        self.urls = self._auto_login.urls
        self.login_urls = self._auto_login.login_urls
        self.credentials = self._auto_login.credentials

    def full_reset(self, skip_if_not_set: bool = True):
        import os

        base_url = os.environ.get(self.RESET_URL_VAR, None)

        if not base_url:
            logger.error(
                f"Environment variable {self.RESET_URL_VAR} is missing or empty, required for a full instance reset."
            )
            if skip_if_not_set:
                logger.warning(
                    "Skipping automated reset. Make sure the instance has been manually reset."
                )
            else:
                raise RuntimeError("Could not reset instance, aborting.")
        else:
            reset_url = f"{base_url}/reset"
            status_url = f"{base_url}/status"

            logger.info(
                f"Initiating {self.__class__.__name__} instance reset on URL {reset_url}."
                " Should take between 200 - 500 seconds to restart."
            )

            response = requests.get(reset_url)
            match response.status_code:
                case 200:
                    logger.info("Reset started.")
                case 418:
                    logger.warning("Reset was already running.")
                case _:
                    raise Exception(
                        f"{self.__class__.__name__} reset request {reset_url} failed"
                        f" ({response.status_code}): {response.text}"
                    )

            retry_after = 20
            timeout = 10 * 60
            start_time = time.time()
            while True:
                response = requests.get(status_url)
                if response.status_code != 200:
                    raise Exception(
                        f"{self.__class__.__name__} status request {status_url} failed"
                        f" ({response.status_code}): {response.text}"
                    )
                if response.text == "Ready for duty!":
                    break
                time_elapsed = time.time() - start_time
                logger.info(f"Reset still running after {time_elapsed:.0f} seconds...")
                if time_elapsed > timeout:
                    raise Exception(
                        f"Reset still running after {time_elapsed} seconds (> {timeout}), aborting."
                    )
                time.sleep(retry_after)

        retries_left = 3
        while retries_left:
            retries_left -= 1
            try:
                self._check_is_reachable(timeout=60)
                break
            except Exception as e:
                if not retries_left:
                    raise
                logger.info(
                    f"Instance unresponsive after reset, retrying ({retries_left} retries left)\n{e}"
                )

    def check_status(self):
        """
        Check the status of the instance. Raises an error if the instance is not ready to be used.
        """
        self._check_is_reachable(timeout=10)

    def _check_is_reachable(self, timeout: int):
        """Test that every website is reachable."""
        for site, url in self.urls.items():
            try:
                requests.get(url, timeout=timeout)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                raise RuntimeError(
                    f'WebArena Pro site "{site}" ({url}) is not reachable. Please check the URL.'
                )

    def _wait_until_site_ready(self, site: str) -> None:
        from webarena_pro_core.state_reset import wait_until_site_ready

        wait_until_site_ready(site)

    def ui_login(
        self,
        site: str,
        page: playwright.sync_api.Page,
        username: str | None = None,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
    ) -> None:
        """Log in through the shared core auto-login implementation."""
        self._auto_login.ui_login(
            site=site,
            page=page,
            username=username,
            max_attempts=max_attempts,
        )
