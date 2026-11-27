"""Format evidence from a Windows Firewall packet log for Notepad."""

from datetime import datetime, timezone
from ipaddress import ip_address


def format_drop_report(log_path, rules, selected_rule=None):
    blocked_ips = {rule["ip"] for rule in rules}
    if selected_rule is not None:
        blocked_ips = {selected_rule["ip"]}
        started = selected_rule["createdAt"] // 1000
        ended_ms = selected_rule.get("unblockedAt")
        if ended_ms is None and not selected_rule["enabled"]:
            ended_ms = selected_rule["expiresAt"]
        ended = ended_ms // 1000 if ended_ms is not None else None
    columns = ("Time", "Source IP", "Destination IP", "Port", "Protocol", "Action")
    required = (
        "date",
        "time",
        "src-ip",
        "dst-ip",
        "dst-port",
        "protocol",
        "action",
        "path",
    )
    with log_path.open("rb") as stream:
        fields = []
        utc = False
        for line in (
            stream.read(4096).decode("utf-8-sig", errors="replace").splitlines()
        ):
            if line.strip().lower() == "#time format: utc":
                utc = True
            if line.startswith("#Fields:"):
                fields = line.partition(":")[2].split()
                break
            if line.strip() and not line.startswith("#"):
                break
        if not all(field in fields for field in required):
            raise ValueError("The Windows Firewall log format could not be read.")
        end = stream.seek(0, 2)
        tail_limit = 1024 * 1024
        start = max(0, end - tail_limit)
        stream.seek(start)
        tail = stream.read(tail_limit)
        if start:
            tail = tail.partition(b"\n")[2]
        recent_lines = tail.decode("utf-8-sig", errors="replace").splitlines()[-4000:]

    rows = []
    for line in reversed(recent_lines):
        values = line.split()
        if len(values) != len(fields) or line.lstrip().startswith("#"):
            continue
        row = dict(zip(fields, values))
        if row["action"] != "DROP" or row["path"] != "RECEIVE":
            continue
        try:
            source = ip_address(row["src-ip"])
        except ValueError:
            continue
        source = str(getattr(source, "ipv4_mapped", None) or source)
        if source not in blocked_ips:
            continue
        log_time = row["date"] + " " + row["time"]
        if selected_rule is not None:
            try:
                timestamp = datetime.fromisoformat(log_time)
                if utc:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                log_second = timestamp.timestamp()
            except (ValueError, OverflowError, OSError):
                continue
            if log_second < started or (ended is not None and log_second > ended):
                continue
        rows.append(
            (
                log_time,
                source,
                row["dst-ip"],
                row["dst-port"],
                row["protocol"],
                row["action"],
            )
        )
        if len(rows) == 100:
            break

    widths = [max(map(len, column)) for column in zip(columns, *rows)]
    divider = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    lines = [divider]
    for row in (columns, *rows):
        lines.append(
            "| "
            + " | ".join(value.ljust(width) for value, width in zip(row, widths))
            + " |"
        )
        lines.append(divider)
    if not rows:
        if selected_rule is not None:
            lines.append(
                f"No incoming DROP records for {selected_rule['ip']} during this rule's time window in the recent log."
            )
        else:
            lines.append(
                "No incoming DROP records for IPs in the Flowwatch Blocklist in the recent log."
            )
    return "\n".join(lines) + "\n"
