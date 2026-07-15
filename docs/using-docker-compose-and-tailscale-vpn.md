# Using Docker Compose and Tailscale VPN

This is a guide on how to add a VPN to the [GAP docker compose stack](using-docker-compose.md).  

[Tailscale](https://tailscale.com/) is a VPN solution based on the [Wireguard](https://www.wireguard.com/) protocol which lets you connect all devices within your virtual private network (tailnet). The [Tailscale Docker](https://tailscale.com/kb/1282/docker) container exposes the services only via a direct VPN connection, which avoids exposing ports to the open internet to connect to your geo-activity-playground instance on-the-go. It provides a domain with a valid Let's Encrypt certificate which is only accessible via the tailnet. The configuration is based on [Docker Tailscale Guide](https://tailscale.com/blog/docker-tailscale-guide).  

The connection also requires an app on your remote device (phone). [Install Tailscale](https://tailscale.com/docs/install)  

## Tailscale Prerequisites

- Active account
- Enabled MagicDNS (in DNS section of admin console)
- Enabled HTTPS (in DNS section of admin console)
- Auth-Key
- ACL policy for tag

### Create Auth-Key and ACL policy for tag

More information on [generating auth keys](https://tailscale.com/kb/1085/auth-keys)
Navigate to [https://login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys) and generate an auth key.

Example Auth-Key configuration:
- Description: docker
- Reusable: yes
- Expiration: 7 days
- Ephemeral: No
- Tags: tag:container

In order to use the tag, it must first be defined in your [Access control policy](https://tailscale.com/kb/1018/acls) in the admin console. Set the same tag as in the Auth-Key.

```
"tagOwners": {
  "tag:container": ["autogroup:admin"],
},
```

When you apply a [tag](https://tailscale.com/kb/1068/tags#generate-an-auth-key-with-a-tag) to a device for the first time and authenticate it, the tagged device's key expiry is disabled by default.

## Compose stack with Tailscale configuration

Like in the default [docker compose install](using-docker-compose.md) the compose project requires a directory, which includes the defining `compose.yaml` file. Additionaly a config directory is created for tailscale.  
The [base directory](create-a-base-directory.md) can also be in this directory e.g., `/docker/geo-activity-playground/playground`. The location can be changed in the `compose.yaml`.  

The geo-activity-playground service will be made available by using the [Tailscale Serve](https://tailscale.com/kb/1312/serve) functionality.
It routes traffic from other devices on your Tailscale network (known as a tailnet) to a local service, in this case inside the container.
It creates a reverse proxy (for VPN-internal routing only) to the geo-activity-playground container internal port 5000 (do not change it).
`TS_CERT_DOMAIN` is composed of a subdomain (hostname set in the `compose.yaml`) and the tailnet root domain given by Tailscale, eg. `https://geo-activity-playground.tail41a3.ts.net/`.  

```bash
mkdir -p /docker/geo-activity-playground/{playground,config}
```

`/docker/geo-activity-playground/compose.yaml`

```yaml
configs:
  ts-serve:
    content: |
      {"TCP":{"443":{"HTTPS":true}},
      "Web":{"$${TS_CERT_DOMAIN}:443":
          {"Handlers":{"/":
          {"Proxy":"http://127.0.0.1:5000"}}}},
      "AllowFunnel":{"$${TS_CERT_DOMAIN}:443":false}}

services:
  geo-activity-playground-ts:
    image: tailscale/tailscale:latest
    container_name: geo-activity-playground-ts
    hostname: geo-activity-playground # set your desired name, which will be the tailscale subdomain
    environment:
      - TS_AUTHKEY=tskey-auth-yyyyyyyyyyyyyyyyyyyyyyyyyyyy # paste your created Auth-Key
      - TS_EXTRA_ARGS=--advertise-tags=tag:container # set the same tag used for the Auth-Key
      - TS_STATE_DIR=/var/lib/tailscale
      - TS_SERVE_CONFIG=/config/serve.json
    configs:
      - source: ts-serve
        target: /config/serve.json
    volumes:
      - ts-data:/var/lib/tailscale
      - ./config:/config
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - net_admin
      - sys_module
    restart: unless-stopped

  geo-activity-playground:
    image: ghcr.io/martin-ueding/geo-activity-playground:latest
    container_name: geo-activity-playground
    depends_on:
      - geo-activity-playground-ts # start container after the VPN network is active
    network_mode: service:geo-activity-playground-ts # link container network to tailscale container
    volumes:
      - /docker/geo-activity-playground/playground:/data # optional: change left side to your desired playground directory
    restart: unless-stopped

volumes:
  ts-data:
    driver: local
```

## Downloading the image and running the container

```bash
cd /docker/geo-activity-playground
docker compose up -d
```

This will start the web server and expose it via your tailnet on `https://[HOSTNAME].[YourTailnetName].ts.net/`, e.g., `https://geo-activity-playground.tail41a3.ts.net/`.
In order to access your instance via that domain, you have to install and authenticate the Tailscale client app on your device you want to open it from. [Install Tailscale](https://tailscale.com/docs/install)  

If you also want to open GAP to your local network, use the following in the Tailscale container (geo-activity-playground-ts) section:

```yaml
ports:
      - "5000:5000" # access with http://DeviceIP:5000
```

To only expose it to the machine it is running on, use `"127.0.0.1:5000:5000"` and access it with `http://127.0.0.1:5000`

Note that port 5000 may not be available on macOS because of AirPlay, so you can map to another host port e.g., `"127.0.0.1:8000:5000"`.  
Then you can open `http://127.0.0.1:8000/` in your browser.  

## Stopping the containers

You can temporarily stop the container (it restarts on reboot with the option `restart: unless-stopped`) with:
```bash
docker stop geo-activity-playground
docker stop geo-activity-playground-ts
```

and start again with:

```bash
docker start geo-activity-playground-ts
docker start geo-activity-playground
```

To permanently stop the docker compose stack, use:

```bash
cd /docker/geo-activity-playground
docker compose down
```

## Updating the image and redeploy the container

```bash
cd /docker/geo-activity-playground
docker compose pull
docker compose up -d --force-recreate
```
