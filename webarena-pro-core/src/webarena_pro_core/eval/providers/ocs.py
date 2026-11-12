"""Validate OCS responses before treating their data as snapshot evidence."""


def response_data(response):
    response.raise_for_status()
    payload = response.json()
    try:
        ocs = payload["ocs"]
        meta = ocs["meta"]
        data = ocs["data"]
        status = meta["status"]
        code = meta["statuscode"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed OCS response") from exc
    if status != "ok" or str(code) not in {"100", "200"}:
        raise ValueError(f"OCS request failed: status={status}, statuscode={code}")
    return data
