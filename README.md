# factql-mcp

Ask your database questions in plain English from Claude, Claude Code, Cursor, VS Code or any MCP client.

Each answer comes with the SQL that ran and the rows it returned, so you can check the number. Works with Postgres, MySQL, DuckDB, uploaded CSV and XLSX files, and PDFs.

Built for developers putting AI near real data: AI apps, agents and internal tools that can't afford a confident wrong number.

This package is FactQL's MCP server: it brings those answers into Claude Desktop, Claude Code, Cursor, or any MCP client. Learn more at [factql.ai](https://factql.ai).

## Hosted server (no install)

FactQL also runs this server for you at:

```
https://api.factql.ai/mcp
```

Add it as a remote (Streamable HTTP) MCP server in Claude (Settings → Connectors → Add custom connector; works on web, desktop and mobile), Claude Code (`claude mcp add --transport http factql https://api.factql.ai/mcp`), Cursor, VS Code, or any app that supports remote MCP. The app opens a FactQL sign-in page; click **Allow** and its questions run as you. Disconnect under Settings → Connected apps on factql.ai. Apps that can't sign in can send an API key as `Authorization: Bearer fl_live_...` instead.

Setup for each app: [docs.factql.ai/guides/mcp](https://docs.factql.ai/guides/mcp/).

The rest of this README is for running the server yourself.

<!-- mcp-name: io.github.factql/factql-mcp -->

## Get a key

Sign up free at [factql.ai/signup](https://factql.ai/signup), connect your data, and create an API key. An ask-only key is enough for this server.

## Install

```bash
uvx factql-mcp
```

or `pip install factql-mcp`.

## Configure

| Variable | Required | Default |
|---|---|---|
| `FACTQL_API_KEY` | yes | — your FactQL API key (an ask-only key is enough) |
| `FACTQL_BASE_URL` | no | `https://api.factql.ai` |
| `FACTQL_WORKSPACE_ID` | no | default workspace, for tenants that use workspaces |
| `FACTQL_END_USER_ID` | no | `mcp:<os user>` |

### Claude Desktop / Cursor (`mcpServers`)

```json
{
  "mcpServers": {
    "factql": {
      "command": "uvx",
      "args": ["factql-mcp"],
      "env": { "FACTQL_API_KEY": "fl_live_..." }
    }
  }
}
```

### Claude Code

```bash
claude mcp add factql -e FACTQL_API_KEY=fl_live_... -- uvx factql-mcp
```

## Tools

- `whoami()` — the tenant, plan, and workspaces this key can query, and `has_data`: whether anything is connected yet.
- `ask(question, workspace_id?, locale?)` — the answer, the SQL that ran, and up to 50 rows. A `needs_clarification` result means the question was too vague; ask the user and call again with the detail. A `declined` result means FactQL couldn't verify an answer and gave none rather than guess; the `reason` says why. An `error` result is a real failure, also with a `reason`. `locale` is `en-GB` or `en-US`.

When FactQL can't answer yet, `ask` returns one of these, with a `message` saying what to do next:

| `result` | `message` |
|---|---|
| `no_data` | No data is connected to this FactQL workspace yet. Add a database or upload a CSV or Excel file at https://factql.ai, then ask again. |
| `schema_not_ready` | Your data is still being prepared. Try again in a minute or two. |
| `email_unverified` | Verify your email to start asking. Check your inbox for the link from FactQL. |
| `limit_reached` | The plan-limit message from FactQL, unchanged. |

Each `ask` is stateless: the MCP client carries the conversation, so a follow-up should restate what it refers to.

## Safety

FactQL only runs read-only `SELECT` queries, under a statement timeout, and only against the tables your admin has described to it (inside a workspace, only that workspace's tables). The key's permissions decide what it can see; this server adds nothing on top.

## Development

```bash
uv run --with pytest pytest -q
```

## License

MIT

## Questions and feedback

Ask in [Discussions](https://github.com/factql/factql-mcp/discussions) or email ask@factql.ai. Bugs go in [Issues](https://github.com/factql/factql-mcp/issues).
