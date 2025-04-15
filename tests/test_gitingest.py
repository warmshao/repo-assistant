import pdb

from gitingest import ingest


def test_gitingest():
    github_url = "https://github.com/github/github-mcp-server"
    summary, tree, content = ingest(github_url)
    tree = "\n".join(tree.split("\n")[2:])
    print(tree)
    print(summary)
    pdb.set_trace()


if __name__ == '__main__':
    test_gitingest()
