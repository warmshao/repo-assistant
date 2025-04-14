from gitingest import ingest


def test_gitingest():
    github_url = "https://github.com/github/github-mcp-server"
    summary, tree, content = ingest(github_url)

    print(tree)
    print(summary)


if __name__ == '__main__':
    test_gitingest()
