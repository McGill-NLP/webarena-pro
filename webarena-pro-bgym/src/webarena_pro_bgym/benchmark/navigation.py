"""Keep task tabs on selected websites without ending recoverable episodes."""

from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError


class NavigationBoundaryError(RuntimeError):
    """The browser could not restore an authorized page safely."""


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))


class TaskNavigationGuard:
    def __init__(self, website_urls):
        self.origins = {
            (parsed.scheme, parsed.netloc)
            for url in website_urls
            if (parsed := urlsplit(url)).scheme in {"http", "https"}
        }
        self.last_urls = {}
        self.warnings = []
        self.blocked_pages = set()
        self.pending_popup_blocks = 0
        self.context = None

    def is_authorized(self, url):
        parsed = urlsplit(url)
        return (parsed.scheme, parsed.netloc) in self.origins and not parsed.username

    def is_allowed_page(self, url):
        return self.is_authorized(url) or url in {
            "about:blank", "about:newtab", "chrome://newtab/", "chrome-error://chromewebdata/",
        }

    def install(self, page):
        context = getattr(page, "context", None)
        if context is None or context is self.context:
            return
        self.context = context
        context.route("**/*", self._route)
        context.on("page", self._new_page)

    def _new_page(self, page):
        if self.pending_popup_blocks:
            self.pending_popup_blocks -= 1
            self.blocked_pages.add(page)

    def _route(self, route):
        request = route.request
        # Restrict document navigations, including redirects and popups. Fetches
        # and static resources retain the applications' existing network access.
        if request.is_navigation_request() and not self.is_authorized(request.url):
            try:
                self.blocked_pages.add(request.frame.page)
            except PlaywrightError:
                # Chromium can route a popup before creating its Frame/Page.
                self.pending_popup_blocks += 1
            self.warnings.append(
                f"Blocked navigation outside the task websites: {safe_url(request.url)}. "
                "Continue on an available task website."
            )
            route.abort("blockedbyclient")
        else:
            route.continue_()

    def remember_pages(self, pages):
        for page in pages:
            if self.is_authorized(page.url):
                self.last_urls[page] = page.url

    def contain(self, context):
        """Defense in depth for non-network URLs or navigation outside routing."""
        pages = list(context.pages)
        for page in pages:
            blocked = page in self.blocked_pages
            self.blocked_pages.discard(page)
            if self.is_allowed_page(page.url) and (not blocked or self.is_authorized(page.url)):
                continue
            blocked_url = safe_url(page.url)
            try:
                previous = self.last_urls.get(page)
                if previous is not None:
                    # A fresh GET never resubmits the failed action or a POST.
                    page.goto(previous, timeout=15000, wait_until="domcontentloaded")
                elif any(other is not page and self.is_allowed_page(other.url) for other in context.pages):
                    page.close()
                else:
                    page.goto("about:blank", timeout=15000, wait_until="domcontentloaded")
            except Exception as error:
                raise NavigationBoundaryError(
                    "Could not contain navigation outside the task websites"
                ) from error
            self.warnings.append(
                f"Blocked navigation outside the task websites: {blocked_url}. "
                "Returned to an authorized tab; the action was not replayed."
            )
        if any(not self.is_allowed_page(page.url) for page in context.pages):
            raise NavigationBoundaryError("An unauthorized tab remained after containment")

    def drain_warnings(self):
        warnings, self.warnings = self.warnings, []
        return warnings
