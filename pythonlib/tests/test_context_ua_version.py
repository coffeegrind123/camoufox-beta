"""NewContext() must claim the Firefox version of the browser it runs in.

Without an explicit ff_version, NewContext() passed None down and the context's
user agent kept the version of whatever corpus it was drawn from: a 152.0.4
build answered `rv:135.0 ... Firefox/135.0` in every NewContext() page, while
its launch-level pages said 152 -- the UA/engine mismatch browserscan reports
(daijro/camoufox#744). The browser knows its own version (Browser.version).
"""

import asyncio
import re

import pytest

from camoufox import async_api, sync_api

BROWSER_VERSION = "152.0.4-beta.31"


class FakeSyncBrowser:
    version = BROWSER_VERSION

    def __init__(self):
        self.options = None

    def new_context(self, **options):
        self.options = options
        return FakeContext()


class FakeAsyncBrowser(FakeSyncBrowser):
    async def new_context(self, **options):
        self.options = options
        return FakeAsyncContext()


class FakeContext:
    def add_init_script(self, script):
        pass


class FakeAsyncContext:
    async def add_init_script(self, script):
        pass


def _versions(ua):
    return re.search(r"rv:(\d+)\.0\)", ua).group(1), re.search(r"Firefox/(\d+)\.0$", ua).group(1)


@pytest.mark.parametrize("os_name", ["windows", "macos", "linux"])
def test_sync_context_claims_the_browser_version(os_name):
    browser = FakeSyncBrowser()
    sync_api.NewContext(browser, os=os_name)
    assert _versions(browser.options["user_agent"]) == ("152", "152")


@pytest.mark.parametrize("os_name", ["windows", "macos", "linux"])
def test_async_context_claims_the_browser_version(os_name):
    browser = FakeAsyncBrowser()
    asyncio.run(async_api.AsyncNewContext(browser, os=os_name))
    assert _versions(browser.options["user_agent"]) == ("152", "152")


def test_explicit_ff_version_still_wins():
    browser = FakeSyncBrowser()
    sync_api.NewContext(browser, os="windows", ff_version="150")
    assert _versions(browser.options["user_agent"]) == ("150", "150")
