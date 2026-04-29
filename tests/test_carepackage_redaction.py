import ast
from pathlib import Path


def _cleaned_list_entries():
    source = Path("mylar/carepackage.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "cleaned_list":
                    return {
                        tuple(elt.value for elt in entry.elts)
                        for entry in node.value.elts
                        if isinstance(entry, ast.Tuple)
                    }
    raise AssertionError("carePackage.cleaned_list assignment not found")


def test_carepackage_redacts_slack_and_mattermost_webhook_urls():
    cleaned_list = _cleaned_list_entries()

    assert ("SLACK", "slack_webhook_url") in cleaned_list
    assert ("MATTERMOST", "mattermost_webhook_url") in cleaned_list
    assert ("DISCORD", "discord_webhook_url") in cleaned_list
