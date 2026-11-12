"""Generic HTTP-based backend state evaluator for the DAG eval engine.

Verifies task completion by making API calls and checking responses.
Supports three modes:
- **Template mode**: ``"api": "template_name"`` + ``"params"`` (preferred, DRY)
- **Inline mode**: raw ``"url"``, ``"method"``, ``"headers"``, ``"body"``
- **Snapshot mode**: ``"baseline_ref": "<name>"`` — skips HTTP and runs
  checks against ``context.baselines[name]["diff"]`` (see ``snapshot.py``).
"""

from __future__ import annotations

import copy
import json
import logging
import re
import unicodedata
from calendar import monthrange
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from webarena_pro_core.eval.defaults import WEBSITE_CREDENTIALS, deployed_website_urls
from webarena_pro_core.eval.api_registry import resolve_api_template
from webarena_pro_core.eval.predicate import find_matches, match_entry
from webarena_pro_core.eval_token import EvalTokenConfigurationError, resolve_eval_token

logger = logging.getLogger(__name__)


class EvalTokenAuthenticationError(RuntimeError):
    """An eval endpoint rejected authentication, not a task assertion."""


class BackendStateRequestError(RuntimeError):
    """A backend probe failed at a resolved deployment URL."""


class BackendStateAssertionError(RuntimeError):
    """A successful resolve response definitively failed a prerequisite check."""


class BackendStateEvaluator:
    """Evaluate a backend state check via HTTP request + response assertions.

    Implements the NodeEvaluator interface (duck typing to avoid circular import
    with dag.py which registers this class).
    """

    def __init__(self) -> None:
        # Cache of bearer tokens keyed by (login_url, user) so token-auth sites
        # (e.g. mattermost) only log in once per evaluator instance.
        self._token_cache: dict[tuple[str, str], str] = {}

    def evaluate(self, eval_config: dict, context):
        from webarena_pro_core.eval.dag import NodeResult

        try:
            # Snapshot mode — consume a pre-computed diff from context.baselines
            baseline_ref = eval_config.get("baseline_ref")
            if baseline_ref is not None:
                return self._evaluate_snapshot(eval_config, context, baseline_ref)

            # HTTP mode. Optional `resolve` pre-requests look up ids/values
            # by name and bind them as params for the main request — lets
            # ID-based APIs (e.g. mattermost) be checked without hardcoding ids.
            bound = self._run_resolves(eval_config, context)
            missing = [name for name, value in bound.items() if value is None]
            if missing:
                # A lookup found nothing (e.g. the album/ticket the check is
                # about does not exist yet). Sending the main request with a
                # literal "None" in the URL would just produce a 4xx/5xx and
                # the same FAIL — skip it and say why.
                return NodeResult(
                    passed=False,
                    reason="resolve bound nothing for "
                    + ", ".join(f"{{{m}}}" for m in missing)
                    + " — target object not found; request skipped",
                )
            request_spec = self._resolve_request(eval_config, context, extra_params=bound)
            method = request_spec.get("method", "GET")
            url = self._resolve_url(request_spec.get("url", ""), context)
            response = self._fetch_response(request_spec, context, eval_config.get("pagination"))
            checks = eval_config.get("checks", [])
            # An error document is not the requested dataset. In particular,
            # absence/count==0 assertions must never pass on an auth error.
            # A matching explicit status check can intentionally inspect a
            # non-2xx response (for example, a deleted resource's 404).
            status_error = self._unexpected_http_status(response, checks)
            if status_error:
                # An explicit status assertion makes a missing/gone resource
                # definitive (for example file_exists expects 200, gets 404).
                # Authentication and server errors still cannot prove absence.
                missing_resource = response.status_code in {404, 410} and any(
                    check.get("type") == "status_code" for check in checks
                )
                return NodeResult(
                    passed=False,
                    reason=f"{method} {url} → {response.status_code}; {status_error}",
                    inconclusive=not missing_resource,
                )
            reasons: list[str] = []
            for check in checks:
                ok, reason = self._run_check(check, response, context, bound)
                reasons.append(f"{check.get('type', '?')}={'ok' if ok else 'FAIL'}: {reason}")
                if not ok:
                    return NodeResult(
                        passed=False,
                        reason=f"{method} {url} → {response.status_code}; {'; '.join(reasons)}",
                    )
            return NodeResult(
                passed=True,
                reason=f"{method} {url} → {response.status_code}; {'; '.join(reasons) or 'no checks'}",
            )
        except BackendStateAssertionError as error:
            return NodeResult(passed=False, reason=str(error))
        except (EvalTokenConfigurationError, EvalTokenAuthenticationError) as error:
            logger.warning("backend_state probe inconclusive: %s", error)
            return NodeResult(passed=False, reason=str(error), inconclusive=True)
        except Exception as e:
            logger.exception("backend_state evaluation failed")
            # The probe itself failed (network error, auth, malformed template).
            # That is not evidence the task failed — mark inconclusive so a
            # tiered resolver escalates instead of hard-failing the rubric.
            return NodeResult(
                passed=False,
                reason=f"exception: {type(e).__name__}: {e}",
                inconclusive=True,
            )

    # ------------------------------------------------------------------
    # Snapshot mode
    # ------------------------------------------------------------------

    def _evaluate_snapshot(
        self, eval_config: dict, context, baseline_ref: str
    ):
        from webarena_pro_core.eval.dag import NodeResult

        baselines = getattr(context, "baselines", None) or {}
        if baseline_ref not in baselines:
            return NodeResult(
                passed=False,
                reason=(
                    f"unknown baseline_ref '{baseline_ref}'; "
                    f"available={list(baselines.keys())}"
                ),
                inconclusive=True,
            )

        bundle = baselines[baseline_ref]
        if bundle.get("error") is not None:
            return NodeResult(
                passed=False,
                reason=f"baseline '{baseline_ref}': {bundle['error']}",
                inconclusive=True,
            )
        diff = bundle.get("diff")
        current = bundle.get("current")
        baseline = bundle.get("baseline")
        if diff is None:
            return NodeResult(
                passed=False,
                reason=f"baseline '{baseline_ref}' has no diff",
                inconclusive=True,
            )

        diff_summary = (
            f"+{len(getattr(diff, 'added', []))} -{len(getattr(diff, 'removed', []))} "
            f"~{len(getattr(diff, 'changed', []))}"
        )

        checks = eval_config.get("checks", [])
        reasons: list[str] = []
        for check in checks:
            ok, reason = self._run_snapshot_check(check, diff, current, baseline)
            reasons.append(f"{check.get('type','?')}={'ok' if ok else 'FAIL'}: {reason}")
            if not ok:
                return NodeResult(
                    passed=False,
                    reason=f"baseline='{baseline_ref}' diff={diff_summary}; {'; '.join(reasons)}",
                )
        return NodeResult(
            passed=True,
            reason=f"baseline='{baseline_ref}' diff={diff_summary}; {'; '.join(reasons) or 'no checks'}",
        )

    def _run_snapshot_check(self, check: dict, diff, current, baseline) -> tuple[bool, str]:
        check_type = check.get("type", "")
        reason = ""
        try:
            match check_type:
                case "snapshot_diff_empty":
                    result = diff.is_empty()
                    reason = (
                        "diff is empty" if result
                        else f"diff not empty (+{len(diff.added)} -{len(diff.removed)} ~{len(diff.changed)})"
                    )
                case "snapshot_diff_added":
                    predicate = check.get("predicate", {})
                    entries = diff.added_entries()
                    min_count = check.get("min_count", 1)
                    matches = find_matches(entries, predicate)
                    result = len(matches) >= min_count
                    reason = (
                        f"{len(matches)}/{min_count} added matched predicate "
                        f"(total added={len(entries)})"
                    )
                case "snapshot_diff_removed":
                    predicate = check.get("predicate", {})
                    entries = diff.removed_entries()
                    min_count = check.get("min_count", 1)
                    matches = find_matches(entries, predicate)
                    result = len(matches) >= min_count
                    reason = (
                        f"{len(matches)}/{min_count} removed matched predicate "
                        f"(total removed={len(entries)})"
                    )
                case "snapshot_diff_count":
                    dim = check.get("dimension", "added")
                    count = len(getattr(diff, dim, []))
                    operator = check.get("operator", "gte")
                    expected = check["value"]
                    result = _compare(count, operator, expected)
                    reason = f"count({dim})={count} {operator} {expected}"
                case "snapshot_diff_moved":
                    if baseline is None or current is None:
                        result = False
                        reason = "no baseline/current snapshot to compare"
                    else:
                        removed_etags = {
                            baseline.entries[eid].get("etag")
                            for eid in diff.removed
                            if baseline.entries[eid].get("type") != "dir"
                        }
                        added_etags = {
                            current.entries[eid].get("etag")
                            for eid in diff.added
                            if current.entries[eid].get("type") != "dir"
                        }
                        removed_etags.discard(None)
                        added_etags.discard(None)
                        missing = removed_etags - added_etags
                        result = not missing
                        reason = (
                            f"all {len(removed_etags)} removed etags reappeared"
                            if result else f"missing etags: {sorted(missing)[:5]}"
                        )
                case "snapshot_entry_attr":
                    scope = check.get("scope", "added")
                    predicate = check.get("predicate", {})
                    if scope == "added":
                        entries = diff.added_entries()
                    elif scope == "current":
                        entries = current.entries if current else {}
                    elif scope == "baseline":
                        entries = baseline.entries if baseline else {}
                    else:
                        entries = {}
                    result = any(
                        match_entry(eid, attrs, predicate)
                        for eid, attrs in entries.items()
                    )
                    reason = (
                        f"found matching entry in scope={scope} ({len(entries)} entries)"
                        if result
                        else f"no entry matched in scope={scope} ({len(entries)} entries)"
                    )
                case _:
                    logger.warning("Unknown snapshot check type: '%s'", check_type)
                    return False, f"unknown snapshot check type '{check_type}'"
        except Exception as e:
            logger.exception("snapshot check '%s' errored", check_type)
            return False, f"exception: {type(e).__name__}: {e}"

        logger.info(
            "snapshot_check %s: %s — %s",
            check_type,
            "PASS" if result else "FAIL",
            reason,
        )
        return result, reason

    # ------------------------------------------------------------------
    # Request resolution
    # ------------------------------------------------------------------

    def _resolve_request(
        self, eval_config: dict, context: object, extra_params: dict | None = None
    ) -> dict:
        """Build a request spec from template or inline config.

        ``extra_params`` (values bound by `resolve` pre-requests) are merged
        into the template params so ``{team_id}``-style placeholders resolve.

        ``site`` (optional) overrides which site's templates/credentials to use
        — needed for cross-site tasks, where the outcome lives on a site other
        than the task's primary (e.g. a nextcloud task whose result is a
        mattermost DM). Defaults to the task's first site.
        """
        site = eval_config.get("site") or self._get_site(context)
        api_name = eval_config.get("api")
        if api_name is not None:
            params = {**eval_config.get("params", {}), **(extra_params or {})}
            spec = resolve_api_template(site, api_name, params)
        else:
            spec = dict(eval_config)
        # Pin auth to the resolved site so bearer/basic auth uses its creds.
        spec.setdefault("auth_site", site)
        return spec

    def _fetch_response(self, request_spec: dict, context: object, pagination: dict | None):
        """Optionally collect a bounded, page-numbered JSON collection before checking it.

        Unavailable or incomplete pages are inconclusive, including when an earlier
        page matched. Existing requests are unchanged unless pagination is configured.
        """
        if pagination is None:
            return self._send(request_spec, context)
        if request_spec.get("method", "GET") != "GET":
            raise ValueError("pagination requires GET")
        path = pagination["path"]
        size = pagination.get("page_size", 200)
        limit = pagination.get("max_pages", 100)
        if not isinstance(path, str) or not path or any(not part for part in path.split(".")):
            raise ValueError("pagination path must be a nonempty dotted JSON path")
        if type(size) is not int or size <= 0 or type(limit) is not int or limit <= 0:
            raise ValueError("pagination page_size and max_pages must be positive integers")
        page_param = pagination.get("page_param", "page")
        size_param = pagination.get("page_size_param", "per_page")
        url = urlsplit(request_spec["url"])
        query = [(key, value) for key, value in parse_qsl(url.query, keep_blank_values=True)
                 if key not in {page_param, size_param}]
        merged = None
        for page in range(limit):
            page_url = urlunsplit(url._replace(query=urlencode(query + [(page_param, page), (size_param, size)])))
            response = self._send({**request_spec, "url": page_url}, context)
            if not 200 <= response.status_code < 300:
                raise BackendStateRequestError(
                    f"GET {self._resolve_url(page_url, context)} → {response.status_code}; incomplete pagination"
                )
            data = response.json()
            entries = self._json_path(data, path)
            count = self._json_path(data, pagination.get("count_path", path))
            if not isinstance(entries, (dict, list)) or not isinstance(count, (dict, list)):
                raise ValueError("pagination requires JSON collections at path and count_path")
            if merged is None:
                merged = copy.copy(entries)
            elif type(entries) is not type(merged):
                raise ValueError("paginated collection changed type")
            elif isinstance(merged, dict):
                merged.update(entries)
            else:
                merged.extend(entries)
            if len(count) < size:
                parent = data
                parts = path.split(".")
                for part in parts[:-1]:
                    parent = parent[part]
                parent[parts[-1]] = merged
                result = copy.copy(response)
                result._content = json.dumps(data).encode("utf-8")
                result.encoding = "utf-8"
                return result
        raise ValueError("collection exceeds evidence pagination limit")

    def _send(self, request_spec: dict, context: object) -> requests.Response:
        """Resolve URL + auth (basic or bearer) for a spec and send it."""
        url = self._resolve_url(request_spec.get("url", ""), context)
        method = request_spec.get("method", "GET")
        try:
            return self._send_to_url(request_spec, context, url)
        except (EvalTokenConfigurationError, EvalTokenAuthenticationError) as error:
            # Keep actionable auth/config diagnostics and the exact target in
            # the tiered fallback trail, including failed resolve pre-requests.
            raise type(error)(f"{error} Request: {method} {url}.") from error
        except Exception as error:
            raise BackendStateRequestError(
                f"{method} {url}: {type(error).__name__}: {error}"
            ) from error

    def _send_to_url(
        self, request_spec: dict, context: object, url: str
    ) -> requests.Response:
        auth = self._resolve_auth(request_spec, context)
        headers = dict(request_spec.get("headers", {}))
        if request_spec.get("auth_mode") == "bearer_login":
            token = self._resolve_bearer_token(request_spec, context)
            cookie_name = request_spec.get("token_cookie")
            auth_header = request_spec.get("auth_header")
            if cookie_name:
                # Cookie-session APIs (e.g. penpot's auth-token) — send the
                # login-issued cookie back instead of an Authorization header.
                headers["Cookie"] = f"{cookie_name}={token}"
            elif auth_header:
                # APIs with a custom session header (e.g. metabase's
                # X-Metabase-Session) — raw token, no Bearer prefix.
                headers[auth_header] = token
            else:
                headers["Authorization"] = f"Bearer {token}"
            auth = None
        elif request_spec.get("auth_mode") == "eval_token":
            # Token-gated read-only eval endpoint (the no-API sites). The shared
            # Use the same persistent/explicit token as container provisioning.
            headers["X-Eval-Token"] = resolve_eval_token()
        response = self._make_request(
            request_spec.get("method", "GET"), url, auth, headers, request_spec.get("body")
        )
        if request_spec.get("auth_mode") == "bearer_login" and response.status_code == 401:
            # Resets can invalidate a cached session without changing its URL.
            # Refresh exactly once; a second rejection remains inconclusive.
            login_url = self._resolve_url(request_spec["login_url"], context)
            self._token_cache.pop((login_url, request_spec.get("auth_user")), None)
            token = self._resolve_bearer_token(request_spec, context)
            if request_spec.get("token_cookie"):
                headers["Cookie"] = f"{request_spec['token_cookie']}={token}"
            elif request_spec.get("auth_header"):
                headers[request_spec["auth_header"]] = token
            else:
                headers["Authorization"] = f"Bearer {token}"
            response = self._make_request(
                request_spec.get("method", "GET"), url, auth, headers, request_spec.get("body")
            )
        if request_spec.get("auth_mode") == "eval_token" and response.status_code in {401, 403}:
            site = request_spec.get("auth_site") or self._get_site(context)
            raise EvalTokenAuthenticationError(
                f"eval_token_authentication_failed: site={site}, HTTP {response.status_code}. "
                "The endpoint rejected X-Eval-Token; ensure the container and evaluator "
                "share WP_EVAL_TOKEN or WP_EVAL_TOKEN_FILE, then restart the affected "
                f"site with `webarena-pro env start {site}`. This probe is inconclusive."
            )
        return response

    def _run_resolves(self, eval_config: dict, context: object) -> dict:
        """Run optional `resolve` pre-requests, binding extracted values.

        Each step: ``{"api"/"url": ..., "extract": "<dotted.json.path>",
        "bind": "<param_name>"}``. Later steps and the main request can use
        previously-bound params. Optional ``checks`` assert prerequisites on
        successful lookup responses. Omit both ``extract`` and ``bind`` for a
        session-state prerequisite whose successful response has no data.
        """
        bound: dict = {}
        parent_site = eval_config.get("site")
        for step in eval_config.get("resolve", []):
            if parent_site and "site" not in step:
                # Cross-site checks: lookups default to the same site as the
                # main request (e.g. a mattermost DM check inside a task whose
                # primary site is acidwave).
                step = {"site": parent_site, **step}
            spec = self._resolve_request(step, context, extra_params=bound)
            resp = self._send(spec, context)
            # A failed lookup is unavailable evidence, not a missing object.
            # Resolve steps extract data; they cannot opt into error bodies.
            if not 200 <= resp.status_code < 300:
                url = self._resolve_url(spec.get("url", ""), context)
                raise BackendStateRequestError(
                    f"{spec.get('method', 'GET')} {url} → {resp.status_code}; "
                    "resolve requires a successful 2xx response"
                )
            # Validate lookup JSON before assertions; malformed evidence must
            # remain inconclusive rather than becoming a prerequisite failure.
            if step.get("checks") or "extract" in step or "bind" in step:
                data = resp.json()
            for check in step.get("checks", []):
                ok, reason = self._run_check(check, resp, context, bound)
                if not ok:
                    raise BackendStateAssertionError(f"resolve prerequisite failed: {reason}")
            # Some prerequisites only establish session state and return 204
            # (Immich unlock). Omit both extract/bind for those requests.
            if "extract" not in step and "bind" not in step:
                continue
            if "extract" not in step or "bind" not in step:
                raise ValueError("resolve must specify both extract and bind, or neither")
            # A malformed lookup document is unavailable evidence as well.
            bound[step["bind"]] = self._json_path(data, step["extract"])
        return bound

    @staticmethod
    def _json_path(data, path: str):
        """Navigate a dotted path (dict keys / list indices) into JSON.

        A ``field=value`` step selects the first dict in a list whose field
        stringifies to the value (e.g. ``albumName=260427.id`` on the immich
        albums array), for APIs with no get-by-name endpoint.
        """
        cur = data
        # A leading "/" switches the separator to "/" so field=value selectors
        # can carry dots (e.g. "/display_name=admin, emma.davis/id").
        sep = "/" if path.startswith("/") else "."
        for key in path.strip(sep).split(sep):
            if isinstance(cur, list) and key.isdigit():
                idx = int(key)
                cur = cur[idx] if 0 <= idx < len(cur) else None
            elif isinstance(cur, list) and "=" in key:
                field, _, want = key.partition("=")
                cur = next(
                    (x for x in cur if isinstance(x, dict) and str(x.get(field)) == want),
                    None,
                )
            elif isinstance(cur, dict):
                cur = cur.get(key)
            else:
                return None
            if cur is None:
                return None
        return cur

    def _resolve_url(self, url: str, context: object) -> str:
        """Resolve placeholders against the active runtime slot at request time.

        Sequential prewarming changes WP_*_URL after this module is imported.
        The import-time defaults can point at a stopped/resetting standby slot.
        """
        for site, site_url in deployed_website_urls().items():
            placeholder = f"__{site.upper()}__"
            url = url.replace(placeholder, site_url)
        return url

    @staticmethod
    def _resolve_regex_urls(pattern: str) -> str:
        """Escape deployment URL placeholders before matching a response regex.

        Resolve at evaluation time so worker/prewarm URL changes are honored.
        Unknown or empty placeholders are configuration errors, never evidence
        that a task passed or failed.
        """
        if "__" not in pattern:
            return pattern
        urls = {f"__{site.upper()}__": url for site, url in deployed_website_urls().items()}

        def replace(match: re.Match) -> str:
            placeholder = match.group(0)
            url = urls.get(placeholder)
            if not url:
                raise ValueError(f"unknown or unconfigured website URL placeholder: {placeholder}")
            return re.escape(url.rstrip("/"))

        return re.sub(r"__[A-Z][A-Z0-9_-]*__", replace, pattern)

    def _resolve_auth(
        self, request_spec: dict, context: object
    ) -> tuple[str, str] | None:
        """Resolve HTTP Basic Auth credentials."""
        # Inline auth dict takes priority
        inline_auth = request_spec.get("auth")
        if isinstance(inline_auth, dict):
            return (inline_auth["username"], inline_auth["password"])

        auth_user = request_spec.get("auth_user")
        if auth_user is None:
            return None

        site = request_spec.get("auth_site") or self._get_site(context)
        site_creds = WEBSITE_CREDENTIALS.get(site, [])
        for cred in site_creds:
            if cred.get("username") == auth_user:
                return (cred["username"], cred["password"])

        logger.warning(
            "No credentials found for user '%s' on site '%s'", auth_user, site
        )
        return None

    def _resolve_bearer_token(self, request_spec: dict, context: object) -> str:
        """Log in to a token-issuing API and return a session token.

        Request spec keys:
          ``login_url``      — endpoint to POST credentials to (``__SITE__`` ok)
          ``token_header``   — response header carrying the token (default "Token")
          ``login_user_key`` — payload key for the username (default "login_id";
                               e.g. immich expects "email", frappe "usr")
          ``login_password_key`` — payload key for the password (default
                               "password"; frappe expects "pwd")
          ``token_json``     — dotted JSON path to the token in the response
                               body, for APIs that return it there instead of
                               in a header (e.g. immich's "accessToken")
          ``token_cookie``   — cookie name carrying the session token (e.g.
                               penpot's "auth-token"); it is extracted from the
                               login response and sent back as a Cookie header
          ``auth_user``      — username (creds resolved via WEBSITE_CREDENTIALS)
        Tokens are cached per (login_url, user) on the evaluator instance.
        """
        login_url = self._resolve_url(request_spec["login_url"], context)
        auth_user = request_spec.get("auth_user")
        site = request_spec.get("auth_site") or self._get_site(context)
        cred = next(
            (c for c in WEBSITE_CREDENTIALS.get(site, []) if c.get("username") == auth_user),
            None,
        )
        if cred is None:
            raise ValueError(f"No credentials for user '{auth_user}' on site '{site}'")

        cache_key = (login_url, auth_user)
        if cache_key in self._token_cache:
            return self._token_cache[cache_key]

        token_header = request_spec.get("token_header", "Token")
        user_key = request_spec.get("login_user_key", "login_id")
        password_key = request_spec.get("login_password_key", "password")
        resp = requests.post(
            login_url,
            json={user_key: cred["username"], password_key: cred["password"]},
            timeout=60,
            allow_redirects=False,
        )
        if not 200 <= resp.status_code < 300:
            raise BackendStateRequestError(
                f"login POST {login_url} → {resp.status_code}; "
                "authentication requires a successful 2xx response"
            )
        token_json = request_spec.get("token_json")
        token_cookie = request_spec.get("token_cookie")
        if token_cookie:
            token = resp.cookies.get(token_cookie)
        elif token_json:
            try:
                token = self._json_path(resp.json(), token_json)
            except Exception:
                token = None
        else:
            token = resp.headers.get(token_header)
        if not token:
            source = (
                f"'{token_cookie}' cookie" if token_cookie
                else f"'{token_json}' in body" if token_json
                else f"'{token_header}' header"
            )
            raise ValueError(
                f"login POST {login_url} returned no token at {source} "
                f"(status {resp.status_code})"
            )
        self._token_cache[cache_key] = token
        return token

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _make_request(
        self,
        method: str,
        url: str,
        auth: tuple[str, str] | None,
        headers: dict,
        body: str | None,
    ) -> requests.Response:
        safe_headers = {
            key: "<redacted>" if key.lower() in {
                "x-eval-token", "authorization", "cookie", "x-metabase-session"
            } else value
            for key, value in headers.items()
        }
        logger.debug(">> %s %s auth=%s headers=%s body=%s",
                      method, url, auth and auth[0], safe_headers, body[:200] if body else None)
        resp = requests.request(
            method=method,
            url=url,
            auth=auth,
            headers=headers,
            data=body.encode("utf-8") if body else None,
            timeout=60,
            # A redirect to a login/error page must not become a successful
            # empty dataset, or hide an explicitly expected redirect status.
            allow_redirects=False,
        )
        logger.debug("<< %s %s (%.1fkB)", resp.status_code, resp.reason, len(resp.content) / 1024)
        logger.debug("   body: %.500s", resp.text)
        return resp

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _run_check(
        self,
        check: dict,
        response: requests.Response,
        context: object | None = None,
        resolved: dict | None = None,
    ) -> tuple[bool, str]:
        check_type = check.get("type", "")
        match check_type:
            case "status_code":
                expected = check["expected"]
                actual = response.status_code
                ok = (actual in expected) if isinstance(expected, list) else (actual == expected)
                reason = f"got {actual}, expected {expected}"
            case "body_contains":
                value = check["value"]
                ok = value in response.text
                reason = f"{'found' if ok else 'missing'} {value!r} in body"
            case "body_not_contains":
                value = check["value"]
                ok = value not in response.text
                reason = f"{'absent' if ok else 'found (should be absent)'} {value!r}"
            case "body_regex":
                pattern = self._resolve_regex_urls(check["pattern"])
                ok = re.search(pattern, response.text) is not None
                reason = f"regex {pattern!r}: {'matched' if ok else 'no match'} in body"
            case "body_date_equals_task_start":
                raw_start = getattr(context, "task_start_date", None)
                if isinstance(raw_start, str):
                    start_date = date.fromisoformat(raw_start)
                elif isinstance(raw_start, date) and not isinstance(raw_start, datetime):
                    start_date = raw_start
                else:
                    # Missing execution metadata cannot be replaced by grading day.
                    # Raising makes this probe inconclusive for a tiered fallback.
                    raise ValueError("body_date_equals_task_start requires task_start_date")
                values = [m.group("date") for m in re.finditer(check["pattern"], response.text)]
                expected = start_date.strftime(check["format"])
                ok = bool(values) and all(value == expected for value in values)
                reason = f"date values={values!r}, expected execution date {expected!r}"
            case "body_not_regex":
                pattern = self._resolve_regex_urls(check["pattern"])
                ok = re.search(pattern, response.text) is None
                reason = f"regex {pattern!r}: {'absent as expected' if ok else 'matched (should be absent)'}"
            case "count_occurrences":
                pattern = check["pattern"]
                operator = check.get("operator", "gte")
                expected = check["value"]
                count = len(re.findall(re.escape(pattern), response.text))
                ok = _compare(count, operator, expected)
                reason = f"count({pattern!r})={count} {operator} {expected}"
            case "json_array_match":
                data = self._json_path(response.json(), check["path"])
                if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                    raise ValueError("json_array_match expects an array of objects")
                predicate = check["predicate"]
                if not predicate:
                    raise ValueError("json_array_match requires a non-empty predicate")
                ok = any(match_entry(str(i), row, predicate) for i, row in enumerate(data))
                reason = "one array entry matched all conditions" if ok else "no matching array entry"
            case "caldav_event":
                from webarena_pro_core.eval.caldav_state import matches_calendar_event

                ok, reason = matches_calendar_event(response.text, check["predicate"])
            case "carddav_contact":
                from webarena_pro_core.eval.nextcloud_contacts import check_contact

                ok, reason = check_contact(check, response.text)
            case "json_predicate":
                from webarena_pro_core.eval.json_predicate import check_json_predicate

                ok, reason = check_json_predicate(check, response.json(), context, resolved or {})
            case "json_path":
                ok, reason = self._check_json_path_verbose(check, response)
            case "json_collection_contains":
                ok, reason = self._check_json_collection_contains(check, response, context, resolved or {})
            case "json_array_date_relative":
                ok, reason = self._check_json_array_date_relative(
                    check, response, context
                )
            case _:
                logger.warning("Unknown check type: '%s'", check_type)
                return False, f"unknown check type '{check_type}'"
        logger.info(
            "http_check %s: %s — %s",
            check_type,
            "PASS" if ok else "FAIL",
            reason,
        )
        return ok, reason

    def _check_json_collection_contains(self, check, response, context, resolved):
        """Match one record, optionally scoped to the current execution.

        ``match`` fields use equality or ``{"resolved": "binding_name"}``.
        All normalized phrases/link requirements apply to the same text field
        of the same record. Malformed evidence raises, making the probe inconclusive.
        """
        from webarena_pro_core.eval.judge_cache import input_digest

        entries = self._json_path(response.json(), check["path"])
        if not isinstance(entries, (dict, list)):
            raise ValueError("json_collection_contains path must resolve to an object or array")
        fields = {}
        for field, expected in check.get("match", {}).items():
            if isinstance(expected, dict) and set(expected) == {"resolved"}:
                expected = resolved[expected["resolved"]]
            fields[field] = expected
        since_field = check.get("created_since_task_start")
        if since_field:
            started = getattr(context, "task_start_time_ms", None)
            if type(started) is not int or started < 0:
                raise ValueError("task_start_time_ms is required to exclude pre-existing records")
        text_check = check.get("text", {})
        phrases = text_check.get("contains_all", [])
        if not isinstance(phrases, list) or any(not isinstance(phrase, str) or not _normalized_words(phrase) for phrase in phrases):
            raise ValueError("contains_all requires nonempty text phrases")
        phrases = [_normalized_words(phrase) for phrase in phrases]
        targets = [self._resolve_link_target(url) for url in text_check.get("link_targets_any", [])]
        if "contains_all" in text_check and not phrases:
            raise ValueError("contains_all requires at least one phrase")
        if "link_targets_any" in text_check and not targets:
            raise ValueError("link_targets_any requires at least one URL")
        candidates, matched = [], []
        records = entries.items() if isinstance(entries, dict) else enumerate(entries)
        for key, entry in records:
            if not isinstance(entry, dict):
                raise ValueError("collection record is not an object")
            if any(entry.get(field) != expected for field, expected in fields.items()):
                continue
            if since_field:
                created = entry.get(since_field)
                if type(created) is not int:
                    raise ValueError("record lacks a valid creation timestamp")
                if created < started:
                    continue
            candidates.append(entry)
            if text_check:
                message = entry.get(text_check["field"])
                if not isinstance(message, str):
                    raise ValueError("record lacks a valid text field")
                words = " " + _normalized_words(message) + " "
                if not all(" " + phrase + " " in words for phrase in phrases):
                    continue
                if targets and not _has_link_target(message, targets, text_check.get("ignore_query_fragment", False)):
                    continue
            matched.append(str(entry.get("id", key)))
        return bool(matched), (
            f"matched_ids={sorted(matched)}; evidence_sha256={input_digest(candidates)}"
        )

    @staticmethod
    def _resolve_link_target(value):
        urls = {f"__{site.upper()}__": url for site, url in deployed_website_urls().items()}

        def replace(match):
            url = urls.get(match.group(0))
            if not url:
                raise ValueError(f"unknown or unconfigured website URL placeholder: {match.group(0)}")
            return url.rstrip("/")

        value = re.sub(r"__[A-Z][A-Z0-9_-]*__", replace, value)
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username is not None:
            raise ValueError("link target must be an absolute HTTP(S) URL without credentials")
        return parsed

    def _check_json_array_date_relative(
        self,
        check: dict,
        response: requests.Response,
        context: object | None,
    ) -> tuple[bool, str]:
        """Find a JSON object and compare its date to task start + N months.

        Example check::

            {
              "type": "json_array_date_relative",
              "path": "jobs",
              "match": {
                "title": {"regex": "(?i)^product design$"},
                "employer": "Acme Analytics",
                "is_active": true
              },
              "date_field": "deadline",
              "months": 2
            }

        Direct match values use equality. ``{"regex": ...}`` uses ``re.search``.
        Month arithmetic uses calendar months and clamps month-end dates (for
        example, January 31 + one month becomes February 28/29).
        """
        try:
            data = response.json()
        except Exception as e:
            return False, f"response is not JSON ({type(e).__name__})"

        path = check.get("path", "")
        entries = self._json_path(data, path) if path else data
        if not isinstance(entries, list):
            return False, f"path {path!r} did not resolve to a JSON array"

        match_spec = check.get("match", {})
        if not isinstance(match_spec, dict):
            return False, "match must be an object"

        def matches(entry: object) -> bool:
            if not isinstance(entry, dict):
                return False
            for field, expected in match_spec.items():
                actual = entry.get(field)
                if isinstance(expected, dict) and "regex" in expected:
                    if re.search(str(expected["regex"]), str(actual or "")) is None:
                        return False
                elif actual != expected:
                    return False
            return True

        matched_entries = [entry for entry in entries if matches(entry)]
        if not matched_entries:
            return False, f"no object at {path!r} matched {match_spec!r}"

        raw_start = getattr(context, "task_start_date", None)
        if isinstance(raw_start, str):
            try:
                start_date = date.fromisoformat(raw_start)
            except ValueError:
                return False, f"invalid task_start_date {raw_start!r}"
        elif isinstance(raw_start, date):
            start_date = raw_start
        else:
            # Direct/dry-run callers that predate EvalContext.task_start_date
            # still get execution-day semantics.
            start_date = date.today()

        try:
            months = int(check["months"])
        except (KeyError, TypeError, ValueError):
            return False, "months must be an integer"

        expected_date = _add_calendar_months(start_date, months)
        date_field = str(check.get("date_field") or "")
        actual_values = [entry.get(date_field) for entry in matched_entries]
        ok = expected_date.isoformat() in actual_values
        reason = (
            f"{len(matched_entries)} object(s) matched; {date_field} values="
            f"{actual_values!r}, expected {expected_date.isoformat()} "
            f"({start_date.isoformat()} + {months} calendar month(s))"
        )
        return ok, reason

    @staticmethod
    def _unexpected_http_status(response: requests.Response, checks: list[dict]) -> str | None:
        if 200 <= response.status_code < 300:
            return None
        status_checks = [check for check in checks if check.get("type") == "status_code"]
        if any(BackendStateEvaluator._check_status_code(check, response) for check in status_checks):
            return None
        expectations = "; ".join(
            f"got {response.status_code}, expected {check['expected']}" for check in status_checks
        )
        return (
            "unexpected HTTP response; content checks skipped (requires 2xx or "
            "an explicitly matching status_code assertion)"
            + (f"; {expectations}" if expectations else "")
        )

    @staticmethod
    def _check_status_code(check: dict, response: requests.Response) -> bool:
        expected = check["expected"]
        if isinstance(expected, list):
            return response.status_code in expected
        return response.status_code == expected

    @staticmethod
    def _check_body_contains(check: dict, response: requests.Response) -> bool:
        value = check["value"]
        return value in response.text

    @staticmethod
    def _check_body_not_contains(check: dict, response: requests.Response) -> bool:
        value = check["value"]
        return value not in response.text

    @staticmethod
    def _check_count_occurrences(check: dict, response: requests.Response) -> bool:
        pattern = check["pattern"]
        operator = check.get("operator", "gte")
        expected = check["value"]
        count = len(re.findall(re.escape(pattern), response.text))
        match operator:
            case "gte":
                return count >= expected
            case "lte":
                return count <= expected
            case "eq":
                return count == expected
            case _:
                logger.warning("Unknown count operator: '%s'", operator)
                return False

    @staticmethod
    def _check_json_path_verbose(check: dict, response: requests.Response) -> tuple[bool, str]:
        path = check["path"]
        if not isinstance(path, str) or not path or any(not key for key in path.split(".")):
            raise ValueError(f"invalid JSON path {path!r}: expected nonempty dotted segments")
        operator = check.get("operator", "equals")
        expected = check.get("value")
        try:
            data = response.json()
        except ValueError as e:
            return False, f"response is not JSON ({type(e).__name__})"

        walked = []
        for key in path.split("."):
            walked.append(key)
            if isinstance(data, dict):
                data = data.get(key)
            elif isinstance(data, list):
                if re.fullmatch(r"[0-9]+", key) is None:
                    raise ValueError(
                        f"invalid JSON path {path!r}: list index {key!r} at "
                        f"{'.'.join(walked)!r} must be a nonnegative integer"
                    )
                index = int(key)
                if index >= len(data):
                    missing = f"path {'.'.join(walked)} missing (index {index}, list length {len(data)})"
                    return operator == "not_exists", missing + (
                        "; absent as expected" if operator == "not_exists" else ""
                    )
                data = data[index]
            else:
                return False, f"path {'.'.join(walked)} not navigable on {type(data).__name__}"
            if data is None:
                if operator == "not_exists":
                    return True, f"path {'.'.join(walked)} absent as expected"
                return False, f"path {'.'.join(walked)} missing"

        preview = repr(data)
        if len(preview) > 80:
            preview = preview[:77] + "..."

        match operator:
            case "equals":
                return data == expected, f"{path}={preview}, expected {expected!r}"
            case "contains":
                if not isinstance(data, (str, list)):
                    return False, f"{path}={preview} not str/list, can't 'contains'"
                return expected in data, f"{path} {'contains' if expected in data else 'missing'} {expected!r}"
            case "exists":
                return True, f"{path}={preview} exists"
            case "not_exists":
                return False, f"{path}={preview} exists (should not)"
            case "length_gte":
                if not hasattr(data, "__len__"):
                    return False, f"{path}={preview} has no length"
                n = len(data)
                return n >= expected, f"len({path})={n}, need >= {expected}"
            case _:
                return False, f"unknown operator {operator!r}"

    @staticmethod
    def _check_json_path(check: dict, response: requests.Response) -> bool:
        """Compatibility wrapper using the same traversal and diagnostics."""
        return BackendStateEvaluator._check_json_path_verbose(check, response)[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_site(context: object) -> str:
        task_config = context.task_config or {}
        sites = task_config.get("sites", [])
        if sites:
            return sites[0]
        return task_config.get("website", "")


def _message_links(message):
    """Read Markdown destinations and bare URLs, excluding labels/code/images."""
    from markdown_it import MarkdownIt

    for block in MarkdownIt("commonmark").parse(message):
        depth = 0
        for token in block.children or []:
            if token.type == "link_open":
                depth += 1
                yield token.attrGet("href") or ""
            elif token.type == "link_close":
                depth -= 1
            elif token.type == "text" and not depth:
                for url in re.findall(r'(?<![A-Za-z0-9:/?&=._%+\-])https?://[^\s<>"“”]+', token.content):
                    yield url.rstrip(".,;:!?)]}")


def _has_link_target(message, targets, ignore_query_fragment):
    for url in _message_links(message):
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue  # A malformed URL must not hide a separate valid link.
        if parsed.username is not None or parsed.password is not None:
            continue
        for target in targets:
            if (parsed.scheme == target.scheme and parsed.netloc.lower() == target.netloc.lower()
                    and parsed.path == target.path
                    and (ignore_query_fragment or (parsed.query, parsed.fragment) == (target.query, target.fragment))):
                return True
    return False


def _normalized_words(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def _compare(actual: int, operator: str, expected: int) -> bool:
    match operator:
        case "gte":
            return actual >= expected
        case "lte":
            return actual <= expected
        case "eq":
            return actual == expected
        case "lt":
            return actual < expected
        case "gt":
            return actual > expected
        case _:
            return False


def _add_calendar_months(value: date, months: int) -> date:
    """Return ``value`` shifted by calendar months, clamping month-end days."""
    month_index = value.year * 12 + (value.month - 1) + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)
