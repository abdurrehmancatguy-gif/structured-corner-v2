# Moving the admin to the office PC

The admin is a program, not a page: it holds the PostgreSQL database, cuts and
resizes uploaded photographs, rewrites the content files, runs `build.py` and
commits the result. Something has to run it. Today that is the owner's MacBook,
which means the admin is only reachable while that machine is awake. This moves
it to the office PC, which never shuts down.

**The end state.** `https://bgscorner.com/admin` answers whenever the office PC
is on, from any device, for anyone on the admin's allowlist. Nothing about the
shop changes: `bgscorner.com` stays on Netlify, the Auth0 application stays as
it is, the DNS record stays as it is. The MacBook stops running anything.

Read the whole file before starting. Every command is for the office PC.

---

## What you are setting up

```
a browser, anywhere
      |  https://bgscorner.com/admin
   Netlify  (passes /admin through, it cannot run the admin itself)
      |  https://admin.bgscorner.com  (a proxy, set in _redirects)
  Cloudflare
      |  the tunnel, which presents the name bgscorner.com to the admin
  THE OFFICE PC  ->  cloudflared  ->  127.0.0.1:4310  ->  admin/server.py
                                                              |
                                                     PostgreSQL bgs_corner
                                                     the repository checkout
```

## Before you start

- Windows 10 version 2004 or later, or Windows 11.
- Administrator rights on the PC.
- The machine stays powered on. That is the whole point of moving here.
- A browser on that PC, for one Cloudflare sign-in.

The admin uses POSIX file locking, so it runs inside **WSL2** (Ubuntu on
Windows), not natively. Everything below after step 1 happens inside Ubuntu.

## Facts you will need

| | |
|---|---|
| Repository | `https://github.com/abdurrehmancatguy-gif/structured-corner-v2` |
| Branch | `main` |
| Database | `bgs_corner`, owner role `bgs_corner`, admin role `bgs_corner_app` |
| Admin address | `https://bgscorner.com` (the admin's `base_url`) |
| Tunnel hostname | `admin.bgscorner.com` |
| Auth0 tenant | `dev-i8cqekmfe57ladb2.us.auth0.com` |
| Auth0 application | `BGS Corner admin`, Client ID `DAX1HiJN4PjATpFVMWWV3PAaRssS6WZw` |
| Allowed to sign in | `bgstechdxb@gmail.com` (add the team's addresses here) |

No secret has to travel from the MacBook. The database is rebuilt from the
content files in the repository, and the tunnel gets credentials of its own.

---

## 1. Ubuntu on Windows

In **PowerShell as administrator**:

```powershell
wsl --install
```

Reboot when it asks. On the first start Ubuntu asks for a username and a
password: that password is only for `sudo` inside Ubuntu, write it down.

Then, so services can start by themselves, in Ubuntu:

```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
```

Back in PowerShell: `wsl --shutdown`, then open Ubuntu again. `systemctl
is-system-running` should answer `running` or `degraded`, not an error.

## 2. What the admin needs

In Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql git ffmpeg curl
```

`ffmpeg` is for film uploads; without it the admin still runs and refuses
videos. Then cloudflared, from Cloudflare's own repository:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared
```

## 3. The database

```bash
sudo service postgresql start
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE bgs_corner LOGIN CREATEDB"
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE bgs_corner_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10"
sudo -u postgres createdb -O bgs_corner bgs_corner
```

`bgs_corner` owns the database and is the role migrations run as.
`bgs_corner_app` is what the admin itself runs as: it may change content and
nothing else. On Ubuntu the socket is `/var/run/postgresql`, not `/tmp`, so
every DSN below says so.

## 4. The repository and the admin's virtualenv

```bash
cd ~
git clone https://github.com/abdurrehmancatguy-gif/structured-corner-v2.git
cd structured-corner-v2
python3 -m venv admin/.venv
admin/.venv/bin/pip install -r admin/requirements.txt
```

## 5. Load the database from the content files

The repository's `flow/content/*.json` are the shop's content and they are in
step with the MacBook's database, so an empty database is loaded from them.
Nothing is copied between machines.

```bash
admin/.venv/bin/python admin/dbtool.py migrate --dsn "host=/var/run/postgresql port=5432 dbname=bgs_corner user=bgs_corner"
```

That is a dry run: it applies the migrations, loads the content, builds the
site from the database's own export and compares every generated file, then
rolls all of it back. Read what it prints. Every content file should say
`identical` (or `formatting only: the same data`), and it should end with
`DRY RUN`. If anything says `DIFFERENT` or `refused`, stop and report it
rather than forcing it.

Then the same line with `--apply`:

```bash
admin/.venv/bin/python admin/dbtool.py migrate --dsn "host=/var/run/postgresql port=5432 dbname=bgs_corner user=bgs_corner" --apply
```

It must end with `Committed.` and a `switched` line saying this checkout now
starts on the database as `bgs_corner_app`. Check it afterwards:

```bash
admin/.venv/bin/python admin/dbtool.py verify
```

The last line should be `OK: the database agrees with itself and with the
files.`

**What is not carried over:** the revision history and the audit log of edits
made on the MacBook. The content itself is identical. If that history matters,
say so before this step and it can be moved with a dump and restore instead.

## 6. Who may open the admin

`admin/local/` is outside git and holds two files. `store.json` was written by
step 5. Write the other one:

```bash
cat > admin/local/admin-auth.json <<'EOF'
{
  "domain": "dev-i8cqekmfe57ladb2.us.auth0.com",
  "client_id": "DAX1HiJN4PjATpFVMWWV3PAaRssS6WZw",
  "base_url": "https://bgscorner.com",
  "allowed": ["bgstechdxb@gmail.com"]
}
EOF
```

`allowed` is the whole gate: an address that is not on it is refused after
signing in, however valid the account. Add the team's addresses here, one
string each. Because `base_url` is a public address, the admin **requires** a
sign-in; it cannot be served open by accident, even on this machine.

## 7. Let Publish push

Publishing commits the change and pushes it to GitHub, so git on this machine
needs to be allowed to push. Make a **fine-grained personal access token** on
github.com (Settings, Developer settings, Fine-grained tokens) for this one
repository with **Contents: read and write**, then:

```bash
git config --global credential.helper store
git -C ~/structured-corner-v2 push        # asks once: username, then the token as the password
git config --global user.name "BGS Corner admin"
git config --global user.email "bgstechdxb@gmail.com"
```

Until this is done everything else works and Publish fails at the last step.

## 8. The tunnel

This machine gets its own tunnel; nothing is copied from the MacBook.

```bash
cloudflared tunnel login          # opens a browser: sign in and pick bgscorner.com
cloudflared tunnel create bgs-admin-office
```

Note the tunnel id it prints. Then the config, with that id in the credentials
line:

```bash
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<'EOF'
tunnel: bgs-admin-office
credentials-file: /home/YOUR_UBUNTU_USER/.cloudflared/THE-TUNNEL-ID.json

ingress:
  # /admin is the tool. assets/img comes with it because every photo preview in
  # the admin is an /assets/img/ URL. The shop's pages, stylesheets and films
  # stay on this machine.
  - hostname: admin.bgscorner.com
    path: ^/(admin|assets/img/)
    service: http://127.0.0.1:4310
    originRequest:
      # Netlify passes bgscorner.com/admin through to this tunnel and sends its
      # own Host. The admin answers to bgscorner.com, which is also the address
      # its cookie and its Auth0 callback belong to, so present that name.
      httpHostHeader: bgscorner.com
  - hostname: admin.bgscorner.com
    service: http_status:404
  - service: http_status:404
EOF
```

Then point the address at this tunnel instead of the MacBook's. This rewrites
the existing DNS record, which is the moment the switch happens:

```bash
cloudflared tunnel route dns --overwrite-dns bgs-admin-office admin.bgscorner.com
```

## 9. Start both with the machine

Two systemd units inside Ubuntu, and one Windows task that starts Ubuntu at
boot so systemd runs with nobody logged in.

```bash
sudo tee /etc/systemd/system/bgs-admin.service >/dev/null <<'EOF'
[Unit]
Description=BGS Corner admin
After=postgresql.service
Wants=postgresql.service

[Service]
User=YOUR_UBUNTU_USER
WorkingDirectory=/home/YOUR_UBUNTU_USER/structured-corner-v2
ExecStart=/home/YOUR_UBUNTU_USER/structured-corner-v2/admin/.venv/bin/python admin/server.py 4310
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/bgs-tunnel.service >/dev/null <<'EOF'
[Unit]
Description=Cloudflare tunnel for the BGS Corner admin
After=network-online.target bgs-admin.service
Wants=network-online.target

[Service]
User=YOUR_UBUNTU_USER
ExecStart=/usr/bin/cloudflared tunnel run bgs-admin-office
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now postgresql bgs-admin bgs-tunnel
systemctl status bgs-admin bgs-tunnel --no-pager
```

Then in **PowerShell as administrator**, so Ubuntu itself starts at boot:

```powershell
schtasks /create /tn "WSL BGS admin" /tr "wsl.exe -d Ubuntu -e /bin/true" /sc onstart /ru SYSTEM /rl HIGHEST /f
```

Reboot the PC and check it comes back by itself. If the task turns out not to
start WSL on this machine, the fallback is to run cloudflared as a native
Windows service instead (`cloudflared service install` in PowerShell, with the
same config placed at `C:\Windows\System32\config\systemprofile\.cloudflared\`)
and leave only the admin inside WSL.

## 10. Check it

From any device, not on the office network:

1. `https://bgscorner.com/admin` shows the Auth0 login. (If Netlify has not yet
   published the deploy that carries the `/admin` rule, `https://admin.bgscorner.com/admin/`
   does the same job.)
2. Signing in with an allowed address opens the admin; the store line in the
   admin's own output says `PostgreSQL bgs_corner as bgs_corner_app`.
3. An address that is not on the list is refused after signing in.
4. Change something small, save it, and check the preview.
5. Press **Publish**: it commits, pushes, and Netlify builds. (Auto publishing
   is currently off on that Netlify site, so the deploy waits for a click.)
6. Reboot the PC. Wait two minutes. Repeat step 1 without touching anything.

Only when step 6 passes is the move finished. Then the MacBook's own admin and
tunnel are stopped, and the old tunnel `bgs-admin` can be deleted from
Cloudflare.

## Rules for this machine

- This checkout and this database are the shop's records. Do not edit
  `flow/content/*.json` by hand: the admin refuses to save over a file changed
  outside it, and says so.
- Only one admin may run against the database at a time. That is enforced, but
  do not start a second copy expecting it to work.
- `admin/local/` never goes into git and must not be copied anywhere public.
- The PostgreSQL server here holds only `bgs_corner`. Leave any other database
  on any other machine alone.
- If the admin refuses to start, read the line it prints: it says which of the
  database, the migrations or the sign-in settings is the reason.
