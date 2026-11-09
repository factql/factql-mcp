# factql-mcp

**FactQL is the harness around the model.**

Ask a question about your data. FactQL runs the query, checks the result before you see an answer, and declines instead of guessing when it can't verify.

Every answer ships with the query that ran, the rows it returned and the lineage behind it. One API call. Works with Postgres, MySQL, DuckDB, uploaded CSV and XLSX files, and PDFs with cited answers.

Built for developers putting AI near real data: AI apps, agents and internal tools that can't afford a confident wrong number.

This package is FactQL's MCP server: it brings those answers into Claude Desktop, Claude Code, Cursor, or any MCP client. Learn more at [factql.ai](https://factql.ai).

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

- `whoami()` — the tenant, plan, and workspaces this key can query.
- `ask(question, workspace_id?, locale?)` — the answer, the SQL that ran, and up to 50 rows. A `needs_clarification` result means the question was too vague; ask the user and call again with the detail. `locale` is `en-GB` or `en-US`.

Each `ask` is stateless: the MCP client carries the conversation, so a follow-up should restate what it refers to.

## Safety

FactQL only runs `SELECT` queries, under a statement timeout, and only against the tables your admin has enabled. The key's permissions decide what it can see; this server adds nothing on top.

## Development

```bash
uv run --with pytest pytest -q
```

## License

MIT
