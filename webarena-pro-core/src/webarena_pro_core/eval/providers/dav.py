"""Extract DAV report data without accepting failed or incomplete responses."""

from xml.etree import ElementTree


def report_data(xml: str, property_name: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    if root.tag != "{DAV:}multistatus":
        raise ValueError("DAV report is not a multistatus response")

    values = []
    for response in root.findall("{DAV:}response"):
        for status in response.findall(".//{DAV:}status"):
            parts = (status.text or "").split()
            if len(parts) < 2 or not parts[1].isdigit():
                raise ValueError("DAV report contains a malformed resource status")
            if not 200 <= int(parts[1]) < 300:
                raise ValueError(f"DAV report resource failed: {status.text}")
        properties = response.findall(f".//{property_name}")
        if not properties or any(not (prop.text or "").strip() for prop in properties):
            raise ValueError(f"DAV report is missing {property_name}")
        values.extend(prop.text for prop in properties)
    return values
