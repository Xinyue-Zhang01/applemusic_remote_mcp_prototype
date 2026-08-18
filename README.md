# Apple Music Remote MCP — prototype

This replaces the earlier REST/GPT-Action bridge with a real **Streamable HTTP MCP server**.

Architecture:

```text
ChatGPT normal conversation
        |
        | MCP over HTTPS
        v
Cloudflare Quick Tunnel
        |
        v
remote_mcp.py  (localhost:8787/mcp)
        |
        | stdio MCP
        v
applemusic-mcp
        |
        v
Your Apple Music account
```

The prototype exposes only two upstream MCP tools:

- `playlist`: `list`, `folders`, `tracks`, `search`
- `library`: `search`, `browse`, `favorites`, `recently_played`, `recently_added`

All write/mutation actions are rejected server-side.

## Important: reuse your current environment

If you already installed and logged into `applemusic-mcp` for the earlier bridge, keep using that same `.venv`. Your Apple Music sign-in does not need to be repeated.

From the project folder:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If this is a new folder and the `.venv` lives in the previous bridge folder, either copy these prototype files into that previous folder, or create a fresh venv and run `applemusic-mcp login` again.

## 1. Keep the Cloudflare window running

If your existing Quick Tunnel is still running and points to:

```text
http://localhost:8787
```

do not restart it. The public URL can stay the same.

For the current test URL used while this prototype was prepared:

```text
https://virtue-daniel-wool-zum.trycloudflare.com
```

the public MCP endpoint becomes:

```text
https://virtue-daniel-wool-zum.trycloudflare.com/mcp
```

If you restart `cloudflared`, it will normally generate a different hostname. Use the new hostname in all commands below.

## 2. Stop the old REST bridge

In the PowerShell window running:

```text
uvicorn bridge:app ...
```

press:

```text
Ctrl+C
```

The Cloudflare window stays open. Only the old local REST server stops.

## 3. Start the real MCP server

Run:

```powershell
python remote_mcp.py `
  --port 8787 `
  --public-host virtue-daniel-wool-zum.trycloudflare.com
```

Use only the hostname after `--public-host` — no `https://` and no `/mcp`.

You should see:

```text
Local MCP URL:  http://127.0.0.1:8787/mcp
Public MCP URL: https://virtue-daniel-wool-zum.trycloudflare.com/mcp
Exposed tools:   playlist, library (read-only)
```

Leave this PowerShell window running.

## 4. Test MCP locally before involving ChatGPT

Open another PowerShell, activate the same venv, then:

```powershell
python test_mcp.py
```

A successful test should:

1. discover `playlist` and `library`;
2. show only the read-only action enums;
3. call `playlist(action="list")`;
4. print your real playlists.

This confirms both directions:

```text
MCP HTTP client -> remote_mcp.py -> applemusic-mcp -> Apple Music
```

## 5. Add it as a ChatGPT custom MCP app

In the "New plugin / custom MCP" dialog:

**Name**

```text
Apple Music
```

**Description**

```text
Read-only access to my personal Apple Music playlists and library.
```

**Connection**

Choose **Server URL** and enter:

```text
https://virtue-daniel-wool-zum.trycloudflare.com/mcp
```

**Authentication**

For this short prototype, choose **No authentication / None** if the dropdown offers it.

Then click **Scan Tools**.

Expected tools:

```text
playlist
library
```

Inspect their action schemas. ChatGPT should see only:

```text
playlist:
  folders
  list
  search
  tracks

library:
  browse
  favorites
  recently_added
  recently_played
  search
```

If you see `create`, `delete`, `add`, `remove`, `rename`, `rate`, etc., stop: the read-only filtering did not work as intended.

Then create/save the draft app.

## 6. Test in an ordinary chat

Select the new Apple Music app from the ChatGPT tools/apps menu, then ask:

```text
看一下我的 Brahms 歌单。
```

A good tool sequence is:

```text
playlist(action="list")
        ->
find Brahms playlist
        ->
playlist(action="tracks", ...)
```

If that works, the central prototype goal is complete: normal ChatGPT conversations can directly read your private Apple Music data through MCP.

## Security boundary of this prototype

This prototype intentionally uses a Cloudflare **Quick Tunnel with no application authentication** if you select "No authentication".

That means the random tunnel URL acts only as an obscure address, not a credential. Anyone who obtains the URL could query the exposed read-only Apple Music tools while the tunnel and local server are running.

Mitigations already present:

- server binds only to `127.0.0.1`;
- Cloudflare is the only public path;
- MCP DNS-rebinding Host/Origin checks are enabled;
- only `playlist` and `library` are exposed;
- mutation actions are blocked again at call time;
- stopping either `remote_mcp.py` or `cloudflared` immediately removes access.

Use this only for the prototype. Once the MCP path works, the next step should be OAuth, Secure MCP Tunnel, or another authenticated/stable deployment.
