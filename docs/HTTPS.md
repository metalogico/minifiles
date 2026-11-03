# HTTPS and network access

The default installation listens on `http://127.0.0.1:8090`, accessible only from the host itself. To use MiniFiles from another computer, choose one of the two setups below.

Complete the storage and credential setup in [Installation](INSTALL.md) first. Run these commands from the same installation directory.

## Use an existing reverse proxy

Set `MINIFILES_ORIGIN` in `.env` to the exact HTTPS address you will open in your browser, such as `https://files.home.arpa`. Include the port if it is not 443, and leave out any path or trailing slash.

If the proxy runs on the host, keep `MINIFILES_BIND_IP=127.0.0.1` and forward requests to `http://127.0.0.1:8090`. Preserve the Host and Origin headers. Configure the proxy for streaming request bodies and allow enough upload size and time for your files.

For example, an existing Caddy installation on the host can use:

```caddyfile
files.home.arpa {
    tls internal
    reverse_proxy 127.0.0.1:8090
}
```

Keep your existing certificate configuration if you already have one. This example uses Caddy's local certificate authority, which clients must trust.

If the proxy runs in Docker, connect it and MiniFiles to a shared Docker network through a Compose override. Use `minifiles:8000` as the upstream: the proxy container's localhost does not point to MiniFiles. You can remove the host listener with `ports: !reset []` in that override.

Apply the updated environment:

```sh
docker compose up -d --wait
```

Do not add `compose.https.yaml` when using your own proxy. Certificate management stays with that proxy.

## Use the included Caddy configuration

This setup adds the official Caddy image and replaces MiniFiles' host HTTP listener with HTTPS. It uses a local certificate authority, so each client needs to trust its certificate.

### Get the files

```sh
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/compose.https.yaml -o compose.https.yaml
mkdir -p docker tls-data
curl -fL https://raw.githubusercontent.com/metalogico/minifiles/main/docker/Caddyfile -o docker/Caddyfile
chmod 700 tls-data
```

If you already have these files from a repository download, skip the two `curl` commands. The TLS directory must be writable by the UID/GID configured in `.env`.

### Set the address

Choose a hostname that resolves to your server, or use its LAN IPv4 address. For example:

```dotenv
MINIFILES_ORIGIN=https://files.home.arpa:8090
MINIFILES_TLS_HOST=files.home.arpa
MINIFILES_BIND_IP=0.0.0.0
MINIFILES_PORT=8090
MINIFILES_TLS_PATH=./tls-data
```

Replace `files.home.arpa` with your hostname or IP in both places. `MINIFILES_TLS_HOST` has no scheme, port or path; `MINIFILES_ORIGIN` is the full browser origin, including the port. `0.0.0.0` listens on all host IPv4 interfaces; use the server's LAN address to restrict the listener to that interface.

For HTTPS on the host only, use `MINIFILES_TLS_HOST=127.0.0.1`, `MINIFILES_BIND_IP=127.0.0.1` and `MINIFILES_ORIGIN=https://127.0.0.1:8090`.

### Start Caddy

```sh
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml pull
docker compose -f compose.yaml -f compose.https.yaml up -d --wait
```

Keep both `-f` options on every later command, including `ps`, `logs`, `stop` and updates. Only Caddy's HTTPS port is published. Continue below to trust its certificate and verify the connection.

### Trust the certificate

On first start, Caddy creates its certificate authority under `MINIFILES_TLS_PATH`. With the default path, the public CA certificate is:

```text
tls-data/caddy/pki/authorities/local/root.crt
```

Copy only `root.crt` to each client and trust it as a certificate authority in the operating system or browser. Use Keychain Access on macOS, Trusted Root Certification Authorities on Windows, or your distribution's CA installation procedure on Linux. Some browsers use their own certificate store. Verify the certificate's fingerprint over a trusted connection before importing it.

Keep the rest of `tls-data` private on the server, including `root.key` and `intermediate.key`. Reuse the same directory after updates so clients continue to trust the CA.

You can check HTTPS without changing your system trust store:

```sh
curl --cacert tls-data/caddy/pki/authorities/local/root.crt https://files.home.arpa:8090/health
```

Use your configured hostname/IP and port. The response should be `{"status":"ok"}`. Once the client trusts the CA, open the same address without `/health` to sign in.

### Troubleshooting

A certificate error usually means the client does not trust the CA or the browser address does not match `MINIFILES_TLS_HOST`. An origin error at login means the address differs from `MINIFILES_ORIGIN`.

After correcting `.env`, apply it with:

```sh
docker compose -f compose.yaml -f compose.https.yaml up -d --wait
```

See [Updating](UPGRADING.md) for image updates and for moving an older HTTPS installation to the official Caddy image.
