# Apple Music Remote MCP — Read-Only ChatGPT Prototype

A small **read-only MCP bridge** that lets ChatGPT access your personal Apple Music playlists and library from ordinary conversations.

It wraps [`applemusic-mcp`] as a local upstream server, exposes a deliberately restricted MCP interface over Streamable HTTP, and uses a Cloudflare Tunnel to make that local MCP endpoint reachable from ChatGPT.

> **Prototype status:** this project is intended for personal development and testing.
> The current Cloudflare Quick Tunnel setup is temporary and unauthenticated.

---

## What this project does

The upstream `applemusic-mcp` project supports a wide range of Apple Music operations, including both reads and writes.

This prototype intentionally exposes only a small **read-only subset**:

### `playlist`

* `list`
* `folders`
* `tracks`
* `search`

### `library`

* `search`
* `browse`
* `favorites`
* `recently_played`
* `recently_added`

Mutation actions such as creating playlists, adding tracks, deleting items, renaming playlists, rating tracks, or removing library items are not exposed.

The restriction is enforced twice:

1. the MCP tool schema shown to ChatGPT contains only the allowed read actions;
2. every actual tool call is checked again server-side before being forwarded upstream.

This means manually constructing a blocked action does not bypass the read-only boundary.

---

## Architecture

```text
ChatGPT
   |
   | MCP over HTTPS
   v
Cloudflare Tunnel
   |
   | forwards to localhost
   v
remote_mcp.py
http://127.0.0.1:8787/mcp
   |
   | local stdio MCP
   v
applemusic-mcp
   |
   v
Apple Music
```

There are therefore three relevant components:

1. **`applemusic-mcp`**
   Handles the actual Apple Music authentication and API/library access.

2. **`remote_mcp.py`**
   Acts as a read-only proxy and exposes Streamable HTTP MCP on localhost.

3. **Cloudflare Tunnel**
   Gives the local MCP server a temporary public HTTPS address that ChatGPT can reach.

Both the local MCP server and the Cloudflare Tunnel must be running for ChatGPT access to work.

---

## Project structure

```text
.
├── remote_mcp.py
├── test_mcp.py
├── requirements.txt
├── .gitignore
└── README.md
```

### `remote_mcp.py`

Main server.

It:

* launches short-lived local connections to `applemusic-mcp serve`;
* discovers the upstream MCP tools;
* exposes only `playlist` and `library`;
* rewrites their action schemas to contain only approved read operations;
* validates every tool call before forwarding it upstream;
* serves the resulting MCP interface over Streamable HTTP;
* enables MCP DNS-rebinding protection;
* binds only to `127.0.0.1`.

### `test_mcp.py`

Small MCP client used to verify the proxy before connecting it to ChatGPT.

It:

1. connects to the Streamable HTTP MCP endpoint;
2. lists the exposed tools;
3. prints the allowed action enums;
4. calls:

```text
playlist(action="list")
```

5. prints the real playlists returned by Apple Music.

---

# Requirements

The current prototype has primarily been tested on Windows.

You need:

* Python 3.10 or newer
* an Apple Music subscription
* Google Chrome on Windows/Linux
* `cloudflared`
* access to ChatGPT custom MCP apps / Developer Mode
* internet access while using Apple Music and the tunnel

Python dependencies are defined in `requirements.txt`:

```text
applemusic-mcp==0.18.5
mcp>=1.28.1,<3
uvicorn[standard]>=0.35,<1
```

The `applemusic-mcp` version is currently pinned because this proxy depends on its tool names and schemas.

---

# Installation

## 1. Clone the repository

```powershell
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
```

---

## 2. Create a virtual environment

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Then install the dependencies:

```powershell
pip install -r requirements.txt
```

---

## 3. Install the browser runtime

On Windows/Linux, install the Chromium runtime used by the Apple Music authentication flow:

```powershell
playwright install chromium
```

A normal Google Chrome installation should also be available on the system.

macOS users may use the Safari/native paths supported by `applemusic-mcp` instead.

---

# Apple Music authentication

Authentication is handled by `applemusic-mcp`, not by this proxy.

Run:

```powershell
applemusic-mcp login
```

On Windows, this should open a local browser window.

Sign into your Apple Music account there.

Then verify the stored login:

```powershell
applemusic-mcp status
```

Once login succeeds, the credentials are stored by `applemusic-mcp` locally.

They are **not stored in this Git repository** and do not need to be entered into ChatGPT.

Normally, you only need to sign in once. Restarting this project or recreating the Cloudflare Tunnel does not by itself require another Apple Music login.

---

# Test the MCP server locally

Before involving ChatGPT or Cloudflare, verify that the local MCP proxy works.

## Terminal 1 — start the server

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run:

```powershell
python remote_mcp.py
```

The default endpoint is:

```text
http://127.0.0.1:8787/mcp
```

You should see output similar to:

```text
Apple Music Remote MCP prototype
--------------------------------
Local MCP URL:  http://127.0.0.1:8787/mcp
Public host:     not configured
Exposed tools:   playlist, library (read-only)
```

Leave this terminal running.

---

## Terminal 2 — run the MCP test client

Activate the same virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run:

```powershell
python test_mcp.py
```

Expected tool discovery:

```text
Discovered MCP tools:
  - playlist: ['folders', 'list', 'search', 'tracks']
  - library: ['browse', 'favorites', 'recently_added', 'recently_played', 'search']
```

The script will then call:

```text
playlist(action='list')
```

and should print your actual Apple Music playlists.

If that succeeds, the complete local path works:

```text
test_mcp.py
    ->
remote_mcp.py
    ->
applemusic-mcp
    ->
Apple Music
```

Stop `remote_mcp.py` with:

```text
Ctrl+C
```

before starting the public configuration below.

---

# Expose the MCP server with Cloudflare

ChatGPT cannot directly connect to:

```text
localhost
```

For this prototype, a Cloudflare Quick Tunnel provides a temporary public HTTPS endpoint.

## Terminal 1 — start Cloudflare

Run:

```powershell
cloudflared tunnel --url http://localhost:8787
```

Cloudflare will print a URL similar to:

```text
https://random-words.trycloudflare.com
```

The hostname in this example is:

```text
random-words.trycloudflare.com
```

Keep this terminal running.

### Important

A Quick Tunnel URL is temporary.

If you stop and restart `cloudflared`, you will normally receive a **different hostname**.

Whenever that happens, you must:

1. use the new hostname when starting `remote_mcp.py`;
2. update the MCP Server URL in ChatGPT.

---

# Start the server for public access

## Terminal 2 — start `remote_mcp.py`

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Take the hostname generated by Cloudflare and run:

```powershell
python remote_mcp.py `
  --port 8787 `
  --public-host random-words.trycloudflare.com
```

Replace:

```text
random-words.trycloudflare.com
```

with your actual current Cloudflare hostname.

Do **not** include:

```text
https://
```

and do **not** include:

```text
/mcp
```

after `--public-host`.

Correct:

```powershell
--public-host random-words.trycloudflare.com
```

Incorrect:

```powershell
--public-host https://random-words.trycloudflare.com/mcp
```

The server should now print:

```text
Local MCP URL:  http://127.0.0.1:8787/mcp
Public MCP URL: https://random-words.trycloudflare.com/mcp
Exposed tools:   playlist, library (read-only)
```

Keep this terminal running as well.

---

# Test the public endpoint

Before configuring ChatGPT, you can optionally test the complete public route.

Open another terminal, activate the virtual environment, and run:

```powershell
python test_mcp.py https://random-words.trycloudflare.com/mcp
```

Replace the URL with your actual tunnel URL.

If this returns your playlists, the following full path is working:

```text
MCP client
    ->
Cloudflare
    ->
remote_mcp.py
    ->
applemusic-mcp
    ->
Apple Music
```

---

# Connect it to ChatGPT

Enable Developer Mode / custom MCP app creation in ChatGPT if it is not already enabled.

Create a new custom MCP app.

Suggested configuration:

### Name

```text
Apple Music Library
```

### Description

```text
Read-only access to my personal Apple Music playlists and library.
```

### Server URL

```text
https://random-words.trycloudflare.com/mcp
```

Use your own current Cloudflare hostname.

### Authentication

For this prototype:

```text
None / No authentication
```

Then select:

```text
Scan Tools
```

ChatGPT should discover exactly two tools:

```text
playlist
library
```

---

## Verify the exposed actions

Inspect the discovered tool schemas.

ChatGPT should see:

```text
playlist:
  folders
  list
  search
  tracks
```

and:

```text
library:
  browse
  favorites
  recently_added
  recently_played
  search
```

If mutation actions such as the following appear:

```text
add
create
delete
move
remove
rename
rate
```

do not continue using that configuration until the proxy is checked.

The intended prototype is read-only.

---

# Using it in ChatGPT

Once the custom app has been created, enable or select it in an ordinary ChatGPT conversation.

You can then use natural-language requests.

For example:

```text
Show me my Apple Music playlists.
```

```text
Look at my Mahler playlist.
```

```text
What tracks are in my Bruckner playlist?
```

```text
What have I listened to recently?
```

```text
Show me my recently added music.
```

```text
Search my library for Beethoven.
```

```text
Show my favorite tracks.
```

ChatGPT decides which MCP action to call from the available read-only interface.

For example, asking for a specific playlist will commonly result in:

```text
playlist(action="list")
        |
        v
identify playlist
        |
        v
playlist(action="tracks", playlist="...")
```

---

# Available operations

## Playlist operations

### List playlists

```text
playlist(action="list")
```

Returns playlists available in the user's Apple Music account/library.

---

### List playlist folders

```text
playlist(action="folders")
```

Folder support depends on the underlying platform and Apple Music environment.

---

### Read tracks from a playlist

```text
playlist(
    action="tracks",
    playlist="Gustav Mahler"
)
```

---

### Search inside a playlist

```text
playlist(
    action="search",
    playlist="Gustav Mahler",
    query="Symphony No. 7"
)
```

Note that `playlist.search` searches **tracks inside a selected playlist**.

To find a playlist by name, list the playlists first rather than using `playlist.search`.

---

# Library operations

## Search the local/personal library

```text
library(
    action="search",
    query="Mahler"
)
```

---

## Browse the library

```text
library(action="browse")
```

Optional parameters can be forwarded to the underlying `applemusic-mcp` implementation.

---

## Recently played

```text
library(action="recently_played")
```

This returns Apple Music's available recently-played data.

It should not be assumed to be a real-time playback log. Apple Music's server-side history may lag behind what was played most recently in the Music app.

---

## Recently added

```text
library(action="recently_added")
```

Returns recently added library content.

---

## Favorites

```text
library(action="favorites")
```

Availability may depend on the platform and Apple Music backend used by `applemusic-mcp`.

---

# Running the prototype later

After the initial installation and Apple Music login, a normal future session requires only the runtime components.

You will usually need three terminals.

## Terminal 1 — Cloudflare

```powershell
cloudflared tunnel --url http://localhost:8787
```

Copy the newly generated hostname.

---

## Terminal 2 — MCP server

```powershell
.\.venv\Scripts\Activate.ps1

python remote_mcp.py `
  --port 8787 `
  --public-host YOUR-CURRENT-HOST.trycloudflare.com
```

---

## Terminal 3 — optional testing

```powershell
.\.venv\Scripts\Activate.ps1

python test_mcp.py
```

or:

```powershell
python test_mcp.py https://YOUR-CURRENT-HOST.trycloudflare.com/mcp
```

Then update the ChatGPT custom app's Server URL if the Quick Tunnel hostname changed.

---

# When is the server available?

The integration works only while both of these processes are running:

```text
remote_mcp.py
cloudflared
```

If `remote_mcp.py` stops:

```text
ChatGPT
   ->
Cloudflare
   -X-> local MCP server
```

If `cloudflared` stops:

```text
ChatGPT
   -X-> public MCP endpoint
```

If the computer itself is shut down or disconnected from the internet, the local Apple Music MCP endpoint is also unavailable.

This is expected for the current local prototype.

---

# Security model

## Read-only boundary

This proxy intentionally exposes only personal-data read operations.

The permitted actions are hard-coded in:

```python
READ_ONLY_ACTIONS
```

in `remote_mcp.py`.

Tool schemas are filtered before being sent to the client, and calls are independently validated at execution time.

---

## Local binding

The HTTP MCP server binds to:

```text
127.0.0.1
```

rather than directly exposing a network interface.

External access is provided through Cloudflare Tunnel.

---

## DNS-rebinding protection

MCP transport security is enabled through:

```text
TransportSecuritySettings
```

Only localhost plus the public hostname supplied with:

```text
--public-host
```

are allowed.

This is also why a newly generated Cloudflare hostname must be passed to `remote_mcp.py` after restarting the tunnel.

---

## No application authentication

The current Quick Tunnel configuration does **not** add authentication in front of the MCP endpoint.

The random Cloudflare hostname therefore acts as an address, not as a secret credential.

Anyone who obtains that URL while both the tunnel and local MCP server are running could potentially invoke the exposed read-only Apple Music tools.

The read-only restriction significantly limits what the endpoint can do, but it does not make the personal library data public-safe.

Do not treat the current setup as a production deployment.

---

## Credentials

Your Apple Music login is managed locally by `applemusic-mcp`.

Do not commit authentication data, browser profiles, tokens, `.env` files, or virtual environments to Git.

The included `.gitignore` excludes:

```text
.venv/
__pycache__/
*.pyc
.env
```

---

# Troubleshooting

## `applemusic-mcp` is not recognized

Make sure the project's virtual environment is active:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then verify:

```powershell
applemusic-mcp status
```

If the command still does not exist:

```powershell
pip install -r requirements.txt
```

---

## Apple Music login does not open correctly

On Windows/Linux, verify that the browser runtime was installed:

```powershell
playwright install chromium
```

Then try:

```powershell
applemusic-mcp login
```

again.

---

## `test_mcp.py` cannot connect locally

Check that:

```powershell
python remote_mcp.py
```

is still running.

The default test endpoint is:

```text
http://127.0.0.1:8787/mcp
```

---

## ChatGPT cannot connect

Verify all of the following:

1. `cloudflared` is still running;
2. `remote_mcp.py` is still running;
3. both use port `8787`;
4. the ChatGPT Server URL ends in `/mcp`;
5. `--public-host` contains only the hostname;
6. the hostname in ChatGPT matches the current Quick Tunnel hostname.

---

## The tunnel was restarted and ChatGPT stopped working

Quick Tunnel hostnames are temporary.

Restart `remote_mcp.py` with the new hostname:

```powershell
python remote_mcp.py `
  --port 8787 `
  --public-host NEW-HOST.trycloudflare.com
```

Then update the custom MCP app to:

```text
https://NEW-HOST.trycloudflare.com/mcp
```

and rescan or reconnect the app as necessary.

---

## Local testing works but the public endpoint fails

A common cause is a mismatch between the current Cloudflare hostname and the value supplied through:

```text
--public-host
```

Because the server enables Host/Origin validation, an old tunnel hostname will be rejected.

---

## ChatGPT sees unexpected write actions

Stop using the endpoint and inspect:

```python
READ_ONLY_ACTIONS
```

in `remote_mcp.py`.

The intended tool schemas contain only:

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

---

## `recently_played` looks outdated

This action reflects the history returned by Apple Music / the underlying `applemusic-mcp` backend.

It can lag behind actual recent listening activity and should not be treated as a precise real-time activity log.

---

# Custom upstream command

By default, the proxy starts the upstream server with:

```text
applemusic-mcp serve
```

The executable can be overridden through the environment variable:

```text
APPLE_MUSIC_MCP_COMMAND
```

For example, this can be useful if `applemusic-mcp` is installed in a non-standard environment.

Most users do not need to change this.

---

# Current limitations

This is intentionally a small prototype.

It currently:

* supports reading only;
* exposes only two upstream tools;
* depends on a locally running computer;
* depends on a running Cloudflare Tunnel;
* uses a temporary public hostname;
* has no application-level authentication;
* does not expose playback control;
* does not expose Apple Music catalog/discovery tools;
* does not expose queue management;
* does not expose any playlist or library mutations.

These are design choices rather than missing protections.

The primary goal is to test a narrow flow:

```text
ordinary ChatGPT conversation
        ->
custom remote MCP
        ->
private Apple Music data
```

while keeping the accessible surface as small and reversible as possible.

---

# Possible next steps

A more permanent version could replace the Quick Tunnel with a stable authenticated deployment, for example:

* a persistent Cloudflare Tunnel with a stable hostname;
* an authenticated MCP endpoint;
* OAuth or another access-control layer;
* a continuously running host/server;
* more granular permission policies;
* optional additional read-only tools.

Write access should only be added deliberately and with additional confirmation and authorization safeguards.

---

# Upstream project

This prototype is a small remote read-only wrapper around the open-source:

```text
applemusic-mcp
```

project by `epheterson`.

The upstream project provides the Apple Music integration itself; this repository mainly adds:

* a restricted tool surface;
* server-side read-only enforcement;
* Streamable HTTP exposure;
* Cloudflare-compatible Host/Origin configuration;
* a simple MCP test client;
* a ChatGPT-oriented deployment path.

This project is not affiliated with or endorsed by Apple.

---

## Prototype goal

If you can open an ordinary ChatGPT conversation and ask:

```text
Show me my Apple Music playlists.
```

and ChatGPT returns the real contents of your private Apple Music library through the custom MCP app, the prototype has succeeded.
