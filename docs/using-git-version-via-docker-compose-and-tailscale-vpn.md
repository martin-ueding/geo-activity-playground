# Using Git Version via Docker Compose and Tailscale VPN

[Docker](https://www.docker.com/) is a software that allows you to run Linux programs in a container.
[Docker Compose](https://docs.docker.com/compose/) is a tool for defining multi-container Docker environments in a single YAML configuration file and deploy it with a single command.

[Tailscale](https://tailscale.com/) is a VPN solution based on the [Wireguard](https://www.wireguard.com/) protocol which lets you connect all devices within your virtual private network (tailnet). The [Tailscale Docker](https://tailscale.com/kb/1282/docker) container exposes the services only via a direct VPN connection, which avoids exposing ports to the open internet to connect to your geo-activity-playground instance on-the-go. It provides a domain with a valid Let's Encrypt certificate which is only accessible via the tailnet.
The configuration is based on [Docker Tailscale Guide](https://tailscale.com/blog/docker-tailscale-guide).

This how-to will give you an example `compose.yml` that can build the geo-activity-playground docker image from Github and start this project within a Docker container and connecting it via Tailscale.

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

## Preparing Tailscale configuration

The geo-activity-playground service will be made available by using the [Tailscale Serve](https://tailscale.com/kb/1312/serve) functionality.
It routes traffic from other devices on your Tailscale network (known as a tailnet) to a local service, in this case inside the container.
It creates a reverse proxy to the geo-activity-playground container internal port 5000 (do not change it).
`TS_CERT_DOMAIN` is comprised of a subdomain (hostname set in the `compose.yml`) and the tailnet root domain.

```bash
mkdir -p /docker/geo-activity-playground/{ts-state,ts-config}
cd /docker/geo-activity-playground/ts-config
nano geo-activity-playground.json
```

```json
{
  "TCP": {
    "443": {
      "HTTPS": true
    }
  },
  "Web": {
    "${TS_CERT_DOMAIN}:443": {
      "Handlers": {
        "/": {
          "Proxy": "http://127.0.0.1:5000"
        }
      }
    }
  }
}
```

## Compose configuration with Tailscale network

With these steps the playground folder (which contains the activities) will be located in the docker project folder. The location can be changed in the `compose.yml`.

```bash
mkdir -p /docker/geo-activity-playground/playground/Activities
cd /docker/geo-activity-playground
nano compose.yml
```

```yml
services:
  ts-geo-activity-playground:
    image: tailscale/tailscale:latest
    container_name: ts-geo-activity-playground
    hostname: geo-activity-playground # set your desired name, which will be the tailscale subdomain
    environment:
      - TS_AUTHKEY=tskey-auth-yyyyyyyyyyyyyyyyyyyyyyyyyyyy # paste your created Auth-Key
      - TS_EXTRA_ARGS=--advertise-tags=tag:container # set the same tag as in the Auth-Key
      - TS_SERVE_CONFIG=/config/geo-activity-playground.json
      - TS_STATE_DIR=/var/lib/tailscale
    volumes:
      - /docker/geo-activity-playground/ts-state:/var/lib/tailscale
      - /docker/geo-activity-playground/ts-config:/config
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - net_admin
      - sys_module
    restart: unless-stopped
  geo-activity:
    build:
      context: https://github.com/martin-ueding/geo-activity-playground.git
      # this sets the build context to the DOCKERFILE located in the Github repository
    container_name: geo-activity-playground
    depends_on:
      - ts-geo-activity-playground # start container after the VPN network is active
    network_mode: service:ts-geo-activity-playground # link container network to tailscale container
    volumes:
      - /docker/geo-activity-playground/playground:/data # optional: change left side to your desired playground directory
    restart: unless-stopped
```

If you want to build the release version of geo-activity-playground from Github instead, you can adjust the build context and add the release tag.
`context: https://github.com/martin-ueding/geo-activity-playground.git#0.29.1`

## Building image and running container

You need to set up your files according to one of the presented methods, like activity files or the Strava API. Consult the other pages in the sidebar for the details.

Once you have your playground directory, you can build the image and start the container.

```bash
docker compose build
docker compose up -d
```

This will start the webserver and expose it via your tailnet on `https://[HOSTNAME].[YourTailnetName].ts.net/`, eg. `https://geo-activity-playground.tail41a3.ts.net/`.
In order to access your instance via that domain, you have to install and authenticate the Tailscale client app on your device you want to open it from.

## Updating the image

If using the tagged release version of geo-activity-playground, update the tag to the latest one first.

```
docker compose down
docker compose build
docker compose up -d --force-recreate
```