def json2table(json_data: list) -> str:
    """
    util to convert JSON data to a Markdown table.
    """
    if not json_data:
        return "No data available"

    headers = json_data[0].keys()

    rows = []
    for item in json_data:
        row = [str(item.get(header, "")) for header in headers]
        rows.append(row)

    markdown_table = []

    markdown_table.append(" | ".join(headers))

    markdown_table.append(" | ".join(["---"] * len(headers)))

    for row in rows:
        markdown_table.append(" | ".join(row))

    return "\n".join(markdown_table)
