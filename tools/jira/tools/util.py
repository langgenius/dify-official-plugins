def simplify_issue(issue: dict) -> dict:
    """
    Simplifies the issue dictionary to include only relevant fields.

    Args:
        issue (dict): The original issue dictionary from Jira.

    Returns:
        dict: A simplified version of the issue.
    """
    return {
        "key": issue["key"],
        "summary": issue["fields"]["summary"],
        "status": issue["fields"]["status"]["name"],
        "description": issue["fields"]["description"],
        "created": issue["fields"]["created"],
        "updated": issue["fields"]["updated"],
        "priority": issue["fields"]["priority"]["name"],
        "issue_type": issue["fields"]["issuetype"]["name"],
    }
