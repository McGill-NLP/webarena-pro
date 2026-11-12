"""Rule-based evaluators for checking task success."""

import logging
import re
from typing import TYPE_CHECKING

import requests

from metabase_agent.config import MetabaseConfig
from metabase_agent.evaluation.base import EvaluationResult

if TYPE_CHECKING:
    from metabase_agent.agent.models import Observation
    from metabase_agent.logging.traces import StepTrace
    from metabase_agent.tasks.models import TaskSpec

# Load Metabase config
_mb_config = MetabaseConfig()
METABASE_URL = _mb_config.url
METABASE_USER = _mb_config.username
METABASE_PASS = _mb_config.password


def _get_metabase_token() -> str | None:
    """Authenticate with Metabase and return a session token."""
    try:
        resp = requests.post(
            f"{METABASE_URL}/api/session",
            json={"username": METABASE_USER, "password": METABASE_PASS},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception:
        return None
 
 
def _metabase_get(path: str) -> dict | list | None:
    """Make an authenticated GET request to the Metabase API."""
    token = _get_metabase_token()
    if not token:
        return None
    try:
        resp = requests.get(
            f"{METABASE_URL}{path}",
            headers={"X-Metabase-Session": token},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


class RuleBasedEvaluator:
    """Evaluator that checks success criteria using simple rules.

        Supported criteria
    ------------------
    Observation-based (fast, no API call):
      - url_contains: <substring>
      - url_matches: <regex>
      - title_contains: <substring>         # browser tab title
      - text_contains: <substring>          # visible page text
 
    Metabase API-based (reliable, requires credentials):
      - saved_question_exists               # any question was saved this run
      - question_name_contains: <substring> # question name matches (API)
      - dashboard_exists                    # any dashboard was created this run
      - dashboard_name_contains: <substring>
      - dashboard_card_count: <n>           # dashboard has at least N cards
      - subscription_exists                 # a pulse/subscription was created
      - alert_exists                        # a question alert was created
      - collection_permission_set           # a collection permission was changed
 
    Download / export:
      - file_downloaded                     # any file was downloaded
      - file_extension: <ext>               # downloaded file has extension (csv, pdf, json…)
 
    UI state (observation heuristics):
      - visualization_type: <type>          # bar, pie, line, table, map…
      - has_variable_filter                 # SQL query uses {{variable}} syntax
      - page_contains_chart                 # a chart element is visible
 
    SQL queries:
      - sql_query_executed                  # SQL query ran without errors
      - query_result_has_rows               # query returned at least one row
 
    Dashboard modifications:
      - dashboard_bookmarked                # dashboard is in bookmarks
      - item_deleted: <type>                # question or dashboard was deleted
      - dashboard_updated                   # dashboard was modified (heuristic)
 
    Data cleanup:
      - data_cleanup_complete               # cleanup task markers present
 
    Instructions/summarization:
      - response_contains: <substring>      # agent's response contains text
      - response_contains_any: [val1, val2] # agent's response contains any of these values
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def evaluate(
        self,
        task: "TaskSpec",
        traces: list["StepTrace"],
        final_observation: "Observation",
    ) -> EvaluationResult:
        """Evaluate the task using rule-based criteria."""
        if not task.success_criteria:
            return EvaluationResult.failed("No success criteria defined")

        passed_criteria: list[str] = []
        failed_criteria: list[str] = []

        for criterion in task.success_criteria:
            criterion_str = str(criterion) if isinstance(criterion, dict) else criterion
            if self._check_criterion(criterion, final_observation, traces):
                passed_criteria.append(criterion_str)
            else:
                failed_criteria.append(criterion_str)

        if failed_criteria:
            return EvaluationResult.failed(
                f"Failed criteria: {', '.join(failed_criteria)}",
                score=len(passed_criteria) / len(task.success_criteria),
            )

        return EvaluationResult.passed(
            f"All criteria passed: {', '.join(passed_criteria)}",
            score=1.0,
        )

    # ------------------------------------------------------------------
    # Criterion dispatcher
    # ------------------------------------------------------------------
 
    def _check_criterion(
        self,
        criterion: str | dict,
        observation: "Observation",
        traces: list["StepTrace"],
    ) -> bool:
        """Check a single criterion.
        
        Criterion can be:
        - A string like "saved_question_exists" or "title_contains: Canada"
        - A dict like {"title_contains": "Canada"} (from YAML parsing)
        """
        if isinstance(criterion, dict):
            if len(criterion) != 1:
                self.logger.warning(f"Invalid dict criterion format: {criterion}")
                return False
            key = list(criterion.keys())[0]
            value = str(criterion[key])
        elif ":" in criterion:
            key, value = criterion.split(":", 1)
            key = key.strip()
            value = value.strip()
        else:
            key = criterion.strip()
            value = ""

        # ---- observation-based ----
        if key == "url_contains":
            return value.lower() in observation.url.lower()

        elif key == "url_matches":
            return bool(re.search(value, observation.url))

        elif key == "title_contains":
            return value.lower() in observation.title.lower()

        elif key == "text_contains":
            return value.lower() in observation.text_content.lower()

        # ---- Metabase API-based ----
        elif key == "saved_question_exists":
            return self._check_question_saved_api(observation)
 
        elif key == "question_name_contains":
            return self._check_question_name(value)
 
        elif key == "dashboard_exists":
            return self._check_dashboard_exists(observation)
 
        elif key == "dashboard_name_contains":
            return self._check_dashboard_name(value)
 
        elif key == "dashboard_card_count":
            return self._check_dashboard_card_count(observation, int(value))
 
        elif key == "subscription_exists":
            return self._check_subscription_exists()
 
        elif key == "alert_exists":
            return self._check_alert_exists()
 
        elif key == "collection_permission_set":
            return self._check_collection_permission(observation)
 
        # ---- downloads ----
        elif key == "file_downloaded":
            return self._check_file_downloaded(traces)
 
        elif key == "file_extension":
            return self._check_file_extension(traces, value)
 
        # ---- UI state ----
        elif key == "visualization_type":
            return self._check_visualization_type(observation, value)
 
        elif key == "has_variable_filter":
            return self._check_variable_filter(observation, traces)
 
        elif key == "page_contains_chart":
            return self._check_page_contains_chart(observation)

        # ---- SQL queries ----
        elif key == "sql_query_executed":
            return self._check_sql_query_executed(observation, traces)

        elif key == "query_result_has_rows":
            return self._check_query_result_has_rows(observation)

        # ---- Dashboard modifications ----
        elif key == "dashboard_bookmarked":
            return self._check_dashboard_bookmarked(observation)

        elif key == "item_deleted":
            return self._check_item_deleted(value, traces)

        elif key == "dashboard_updated":
            return self._check_dashboard_updated(observation, traces)

        # ---- Data cleanup ----
        elif key == "data_cleanup_complete":
            return self._check_data_cleanup_complete(observation, traces)

        # ---- Instructions/summarization ----
        elif key == "response_contains":
            return self._check_response_contains(value, traces)

        elif key == "response_contains_any":
            return self._check_response_contains_any(criterion, traces)

        elif key == "agent_answered":
            return self._check_agent_answered(value, traces)

        else:
            self.logger.warning(f"Unknown criterion: {key}")
            return False
 
    # ------------------------------------------------------------------
    # Metabase API checks
    # ------------------------------------------------------------------
 
    def _check_question_saved_api(self, observation: "Observation") -> bool:
        """
        Primary: verify via API that a card exists whose URL matches the
        current page (/question/123).
        Fallback: heuristic on observation text if API is unavailable.
        """
        # Try to extract question ID from URL first
        match = re.search(r"/question/(\d+)", observation.url)
        if match:
            question_id = match.group(1)
            data = _metabase_get(f"/api/card/{question_id}")
            if data and "id" in data:
                return True
 
        # Fallback: check if any card was recently created
        data = _metabase_get("/api/card?f=all&limit=5")
        if data:
            cards = data if isinstance(data, list) else data.get("data", [])
            if cards:
                return True
 
        # Last resort heuristic
        return any([
            "saved" in observation.text_content.lower(),
            "/question/" in observation.url,
        ])
 
    def _check_question_name(self, substring: str) -> bool:
        """Check that a recently saved question's name contains the substring."""
        data = _metabase_get("/api/card?f=all&limit=10")
        if not data:
            return False
        cards = data if isinstance(data, list) else data.get("data", [])
        return any(substring.lower() in (c.get("name") or "").lower() for c in cards)
 
    def _check_dashboard_exists(self, observation: "Observation") -> bool:
        """Check via API that a dashboard exists at the current URL."""
        match = re.search(r"/dashboard/(\d+)", observation.url)
        if match:
            dash_id = match.group(1)
            data = _metabase_get(f"/api/dashboard/{dash_id}")
            if data and "id" in data:
                return True
 
        # Fallback: check recent dashboards
        data = _metabase_get("/api/dashboard?limit=5")
        if data:
            dashboards = data if isinstance(data, list) else data.get("data", [])
            return bool(dashboards)
 
        return "/dashboard/" in observation.url
 
    def _check_dashboard_name(self, substring: str) -> bool:
        """Check that a dashboard with a matching name exists."""
        data = _metabase_get("/api/dashboard?limit=20")
        if not data:
            return False
        dashboards = data if isinstance(data, list) else data.get("data", [])
        return any(substring.lower() in (d.get("name") or "").lower() for d in dashboards)
 
    def _check_dashboard_card_count(
        self, observation: "Observation", min_cards: int
    ) -> bool:
        """Check that the current dashboard has at least min_cards cards."""
        match = re.search(r"/dashboard/(\d+)", observation.url)
        if not match:
            return False
        dash_id = match.group(1)
        data = _metabase_get(f"/api/dashboard/{dash_id}")
        if not data:
            return False
        cards = data.get("dashcards") or data.get("ordered_cards") or []
        return len(cards) >= min_cards
 
    def _check_subscription_exists(self) -> bool:
        """Check that at least one pulse/subscription exists."""
        data = _metabase_get("/api/pulse")
        if not data:
            return False
        pulses = data if isinstance(data, list) else data.get("data", [])
        return bool(pulses)
 
    def _check_alert_exists(self) -> bool:
        """Check that at least one question alert exists."""
        data = _metabase_get("/api/alert")
        if not data:
            return False
        alerts = data if isinstance(data, list) else data.get("data", [])
        return bool(alerts)
 
    def _check_collection_permission(self, observation: "Observation") -> bool:
        """
        Heuristic: agent landed on a permissions page and no error is shown.
        For a robust check, diff /api/collection/graph before and after.
        """
        on_permissions_page = "permissions" in observation.url.lower()
        no_error = "error" not in observation.text_content.lower()
        return on_permissions_page and no_error
 
    # ------------------------------------------------------------------
    # Download checks
    # ------------------------------------------------------------------
 
    def _check_file_downloaded(self, traces: list["StepTrace"]) -> bool:
        """
        Check traces for a network response with a Content-Disposition header
        or a Metabase export URL pattern.
        """
        export_url_patterns = [
            r"/api/card/\d+/query/csv",
            r"/api/card/\d+/query/json",
            r"/api/card/\d+/query/xlsx",
            r"/api/dashboard/\d+/export",
        ]
        for trace in traces:
            for event in getattr(trace, "network_events", []):
                url = getattr(event, "url", "")
                for pattern in export_url_patterns:
                    if re.search(pattern, url):
                        return True
                headers = getattr(event, "response_headers", {})
                if "content-disposition" in {k.lower() for k in headers}:
                    return True
        return False
 
    def _check_file_extension(self, traces: list["StepTrace"], extension: str) -> bool:
        """Check that a downloaded file matches the expected extension."""
        ext = extension.lower().lstrip(".")
        export_url_patterns = {
            "csv": r"/query/csv",
            "json": r"/query/json",
            "xlsx": r"/query/xlsx",
            "pdf": r"/export|/pdf",
        }
        pattern = export_url_patterns.get(ext, rf"\.{ext}")
        for trace in traces:
            for event in getattr(trace, "network_events", []):
                url = getattr(event, "url", "")
                if re.search(pattern, url):
                    return True
        return False
 
    # ------------------------------------------------------------------
    # UI state checks
    # ------------------------------------------------------------------
 
    def _check_visualization_type(
        self, observation: "Observation", viz_type: str
    ) -> bool:
        """
        Checks the page text/HTML for indicators that the correct
        visualization type is active.
        """
        viz_indicators: dict[str, list[str]] = {
            "bar":   ["bar chart", "bar graph", "type/bar"],
            "line":  ["line chart", "line graph", "type/line"],
            "pie":   ["pie chart", "type/pie"],
            "table": ["table", "type/table"],
            "map":   ["map", "type/map", "pin map"],
            "area":  ["area chart", "type/area"],
            "scalar":["scalar", "type/scalar", "single number"],
            "row":   ["row chart", "type/row"],
        }
        indicators = viz_indicators.get(viz_type.lower(), [viz_type.lower()])
        text = observation.text_content.lower()
        html = getattr(observation, "html_content", "").lower()
        return any(ind in text or ind in html for ind in indicators)
 
    def _check_variable_filter(
        self, observation: "Observation", traces: list["StepTrace"]
    ) -> bool:
        """
        Check that a SQL question with {{variable}} filters is active.
        Looks for the filter widget UI elements in page text/HTML.
        """
        filter_indicators = [
            "filter widget",
            "variable",
            "required widget",
            "{{",          # still in editor view
            "text filter",
            "number filter",
            "date filter",
        ]
        text = (observation.text_content + getattr(observation, "html_content", "")).lower()
        return any(ind in text for ind in filter_indicators)
 
    def _check_page_contains_chart(self, observation: "Observation") -> bool:
        """Check that a rendered chart is visible on the page."""
        chart_indicators = [
            "echarts",
            "svg",
            "<canvas",
            "highcharts",
            "chart-container",
            "dc-chart",
        ]
        html = getattr(observation, "html_content", "").lower()
        return any(ind in html for ind in chart_indicators)

    # ------------------------------------------------------------------
    # SQL query checks
    # ------------------------------------------------------------------

    def _check_sql_query_executed(
        self, observation: "Observation", traces: list["StepTrace"]
    ) -> bool:
        """
        Check that a SQL query was executed successfully.
        Looks for query results or the native query editor state.
        """
        success_indicators = [
            "rows",
            "result",
            "showing",
            "row",
        ]
        error_indicators = [
            "error",
            "syntax error",
            "failed",
            "invalid",
        ]
        text = observation.text_content.lower()
        has_success = any(ind in text for ind in success_indicators)
        has_error = any(ind in text for ind in error_indicators)

        if has_error and not has_success:
            return False

        on_question_page = "/question" in observation.url
        return has_success or on_question_page

    def _check_query_result_has_rows(self, observation: "Observation") -> bool:
        """Check that the query result contains at least one row."""
        text = observation.text_content.lower()
        if "no results" in text or "0 rows" in text:
            return False
        row_indicators = [
            r"\d+ rows?",
            "showing",
            "result",
        ]
        return any(re.search(ind, text) for ind in row_indicators)

    # ------------------------------------------------------------------
    # Dashboard modification checks
    # ------------------------------------------------------------------

    def _check_dashboard_bookmarked(self, observation: "Observation") -> bool:
        """
        Check if the current dashboard is bookmarked.
        Uses API to verify bookmark status.
        """
        match = re.search(r"/dashboard/(\d+)", observation.url)
        if not match:
            return False
        dash_id = match.group(1)

        data = _metabase_get(f"/api/dashboard/{dash_id}")
        if data:
            return data.get("is_bookmarked", False) or data.get("bookmark", False)

        bookmark_indicators = ["bookmarked", "remove from bookmarks", "unbookmark"]
        text = observation.text_content.lower()
        return any(ind in text for ind in bookmark_indicators)

    def _check_item_deleted(self, item_type: str, traces: list["StepTrace"]) -> bool:
        """
        Check if an item (question or dashboard) was deleted.
        Looks for deletion confirmation in traces or observation.
        """
        item_type = item_type.lower() if item_type else "item"
        delete_indicators = [
            "deleted",
            "moved to trash",
            "removed",
            f"{item_type} deleted",
        ]

        for trace in traces:
            action_str = str(getattr(trace, "action", "")).lower()
            if "delete" in action_str:
                return True
            for event in getattr(trace, "network_events", []):
                method = getattr(event, "method", "")
                if method.upper() == "DELETE":
                    return True

        return False

    def _check_dashboard_updated(
        self, observation: "Observation", traces: list["StepTrace"]
    ) -> bool:
        """
        Check if a dashboard was modified (cards added/removed, layout changed).
        Heuristic based on PUT/POST requests to dashboard API.
        """
        update_patterns = [
            r"PUT.*/api/dashboard/\d+",
            r"POST.*/api/dashboard/\d+/cards",
        ]

        for trace in traces:
            for event in getattr(trace, "network_events", []):
                method = getattr(event, "method", "").upper()
                url = getattr(event, "url", "")
                for pattern in update_patterns:
                    if re.search(pattern, f"{method} {url}"):
                        return True

        save_indicators = ["saved", "updated", "changes saved"]
        text = observation.text_content.lower()
        return any(ind in text for ind in save_indicators)

    # ------------------------------------------------------------------
    # Data cleanup checks
    # ------------------------------------------------------------------

    def _check_data_cleanup_complete(
        self, observation: "Observation", traces: list["StepTrace"]
    ) -> bool:
        """
        Check if a data cleanup task was completed.
        Looks for deletion/archival actions or cleanup confirmation.
        """
        cleanup_indicators = [
            "deleted",
            "archived",
            "cleaned",
            "removed",
            "moved to trash",
        ]
        text = observation.text_content.lower()
        if any(ind in text for ind in cleanup_indicators):
            return True

        delete_count = 0
        for trace in traces:
            for event in getattr(trace, "network_events", []):
                method = getattr(event, "method", "")
                if method.upper() == "DELETE":
                    delete_count += 1

        return delete_count > 0

    # ------------------------------------------------------------------
    # Instructions/summarization checks
    # ------------------------------------------------------------------

    def _check_response_contains(
        self, substring: str, traces: list["StepTrace"]
    ) -> bool:
        """
        Check if the agent's response contains the specified text.
        Used for tasks where the agent must report/answer something.
        
        Checks multiple sources for the answer:
        1. answer() action value (primary - the dedicated answer action)
        2. done() action reasoning (legacy fallback)
        3. Any explicit "answer:" or "result:" patterns in reasoning
        4. Numeric answers with flexible matching (handles formatting)
        """
        substring_lower = substring.lower().strip()
        
        # Try to find numeric value if substring is a number
        is_numeric = False
        numeric_value = None
        try:
            numeric_value = float(substring.replace(",", "").replace("$", ""))
            is_numeric = True
        except ValueError:
            pass
        
        for trace in traces:
            if not trace.action:
                continue
            
            # Check answer() action - the primary way to report answers
            if trace.action.action_type == "answer":
                answer_value = trace.action.value or ""
                answer_lower = answer_value.lower()
                
                # Direct substring match
                if substring_lower in answer_lower:
                    return True
                
                # Numeric match
                if is_numeric:
                    try:
                        answer_num = float(answer_value.replace(",", "").replace("$", ""))
                        if abs(answer_num - numeric_value) < 0.01:
                            return True
                    except ValueError:
                        pass
                    # Also check if number appears in the answer
                    num_str = str(int(numeric_value)) if numeric_value == int(numeric_value) else str(numeric_value)
                    if re.search(rf"\b{re.escape(num_str)}\b", answer_value):
                        return True
                continue
            
            # Check done() action reasoning (legacy/fallback)
            if trace.action.action_type != "done":
                continue
                
            reasoning = trace.action.reasoning or ""
            reasoning_lower = reasoning.lower()
            
            # Direct substring match
            if substring_lower in reasoning_lower:
                return True
            
            # Check answer field if present (some agents use this)
            answer_field = getattr(trace.action, "answer", None)
            if answer_field and substring_lower in str(answer_field).lower():
                return True
            
            # Look for explicit answer patterns like "Answer: X" or "The answer is X"
            answer_patterns = [
                r"answer[:\s]+(.+?)(?:\.|$|\n)",
                r"result[:\s]+(.+?)(?:\.|$|\n)",
                r"the (?:answer|result|total|count|number) is[:\s]*(.+?)(?:\.|$|\n)",
                r"there (?:are|is)[:\s]*(\d+)",
                r"found[:\s]*(\d+)",
                r"shows[:\s]*(\d+)",
            ]
            
            for pattern in answer_patterns:
                match = re.search(pattern, reasoning_lower, re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip()
                    if substring_lower in extracted:
                        return True
                    # For numeric comparisons, try flexible matching
                    if is_numeric:
                        try:
                            extracted_num = float(extracted.replace(",", "").replace("$", ""))
                            if abs(extracted_num - numeric_value) < 0.01:
                                return True
                        except ValueError:
                            pass
            
            # For numeric answers, also check if the number appears in the reasoning
            if is_numeric:
                # Match the number with optional formatting (commas, decimals)
                num_str = str(int(numeric_value)) if numeric_value == int(numeric_value) else str(numeric_value)
                # Check for the number with word boundaries
                if re.search(rf"\b{re.escape(num_str)}\b", reasoning):
                    return True
                # Also check formatted versions (e.g., "1,234" for 1234)
                if numeric_value >= 1000:
                    formatted = f"{int(numeric_value):,}"
                    if formatted in reasoning:
                        return True
                        
        return False

    def _check_response_contains_any(
        self, criterion: str | dict, traces: list["StepTrace"]
    ) -> bool:
        """
        Check if the agent's response contains ANY of the specified values.
        Used when multiple answers are acceptable (e.g., tied results).
        
        Accepts criterion in these formats:
        - dict: {"response_contains_any": [val1, val2, ...]}
        - dict: {"response_contains_any": "val1, val2, ..."}  (comma-separated string)
        """
        # Extract the list of acceptable values
        if isinstance(criterion, dict):
            values = criterion.get("response_contains_any", [])
            if isinstance(values, str):
                # Handle comma-separated string
                values = [v.strip() for v in values.split(",")]
        else:
            # Shouldn't happen, but handle string case
            values = [v.strip() for v in str(criterion).split(",")]
        
        if not values:
            self.logger.warning("response_contains_any: no values provided")
            return False
        
        # Check each acceptable value
        for value in values:
            if self._check_response_contains(str(value), traces):
                return True
        
        return False

    def _check_agent_answered(self, expected_value: str, traces: list["StepTrace"]) -> bool:
        """
        Check if the agent provided an answer using the answer() action.
        
        Args:
            expected_value: Either "true" (just check agent answered something),
                          or a specific value to match against the answer.
            traces: List of step traces from the run.
        
        Returns:
            True if the agent answered (and matches expected value if specified).
        """
        expected_lower = expected_value.lower().strip()
        
        # Check if we just need to verify the agent answered (any value)
        check_any_answer = expected_lower in ("true", "yes", "1", "")
        
        # Try to parse expected as a number for flexible numeric matching
        expected_numeric = None
        if not check_any_answer:
            try:
                expected_numeric = float(expected_value.replace(",", "").replace("$", ""))
            except ValueError:
                pass
        
        for trace in traces:
            if not trace.action:
                continue
            
            # Only check answer() actions
            if trace.action.action_type != "answer":
                continue
            
            answer_value = trace.action.value or ""
            
            # If we just need to check that the agent answered something
            if check_any_answer:
                return bool(answer_value.strip())
            
            # Check for exact match (case-insensitive)
            if expected_lower == answer_value.lower().strip():
                return True
            
            # Check for substring match
            if expected_lower in answer_value.lower():
                return True
            
            # Numeric matching with tolerance
            if expected_numeric is not None:
                try:
                    answer_numeric = float(answer_value.replace(",", "").replace("$", ""))
                    if abs(answer_numeric - expected_numeric) < 0.01:
                        return True
                except ValueError:
                    pass
        
        return False